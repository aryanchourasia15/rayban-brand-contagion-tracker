"""Real-media source/review separation; test review events never enter research files."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src.ui.media_evidence import (DATA_DIR, ROOT, CHOICES, load_media_rows, prepare_rows,
                                   read_csv, summarize_groups, apply_review_events)
from src.ui.contagion_data import demo_discussions


class TestMediaEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DATA_DIR / 'articles.csv').exists():
            raise unittest.SkipTest('Private local media corpus is intentionally not shipped with source code.')

    def setUp(self):
        # Tests start with proposals, independently of genuine reviews saved later.
        self.rows = prepare_rows(read_csv(DATA_DIR / 'articles.csv'),
                                 json.loads((DATA_DIR / 'dataset_quality.json').read_text(encoding='utf-8')))

    def event(self, row, *, event_id='test-event-1', decision='confirm', **labels):
        # Fabricated reviewer metadata is confined to this unit-test object.
        return dict(review_event_id=event_id, record_id=row['record_id'],
                    source_fingerprint=row['source_fingerprint'], reviewed_at='2026-11-16T12:00:00Z',
                    reviewer_code='unit-test-only-not-a-real-review', reviewer_decision=decision,
                    **({field: row[field] for field in CHOICES} | labels),
                    supporting_evidence='Unit-test evidence; not a research review.', reviewer_notes='Mock review for implementation testing only.')

    def test_original_coding_is_preserved_and_no_human_validation_is_invented(self):
        original = read_csv(DATA_DIR / 'articles.csv')
        self.assertEqual(len(self.rows), 32)
        for proposed, raw in zip(self.rows, original):
            self.assertEqual(json.loads(proposed['original_coding_json']), raw)
            self.assertEqual(proposed['record_id'], raw['source_id'])
            self.assertEqual(proposed['original_url'], raw['url'])
            self.assertEqual(proposed['review_status'], 'pending_human_review')
            self.assertEqual(proposed['reviewer_decision'], '')
        self.assertEqual(sum(r['denominator'] for r in summarize_groups(self.rows, reviewed=True)), 0)

    def test_exact_group_counts_and_categorical_denominators(self):
        summaries = summarize_groups(self.rows)
        self.assertEqual([r['denominator'] for r in summaries], [13, 17, 2])
        self.assertEqual([r['privacy_related_yes'] for r in summaries], [11, 1, 2])
        self.assertEqual([r['ray_ban_mentioned_yes'] for r in summaries], [13, 17, 0])
        self.assertEqual([r['responsibility_attributed_Meta'] for r in summaries], [5, 0, 2])
        self.assertEqual([r['wider_brand_association_explicit'] for r in summaries], [2, 0, 0])
        for row in summaries:
            for field, choices in CHOICES.items():
                if field != 'source_category':
                    self.assertEqual(sum(row[field + '_' + choice] for choice in choices), row['denominator'])
        self.assertEqual(sum(bool(r['ambiguity_flags']) for r in self.rows), 16)

    def test_brand_names_and_positive_references_are_not_adverse_spillover(self):
        direct = [r for r in self.rows if r['wider_brand_association'] == 'explicit']
        self.assertEqual({r['publisher'] for r in direct}, {'Stuff', 'WIRED'})
        self.assertTrue(all(r['association_direction'] in ('positive_traditional_brand_comparison', 'traditional_style_continuity') for r in direct))
        self.assertTrue(all(r['review_status'] == 'pending_human_review' for r in direct))
        named_only = [r for r in self.rows if r['ray_ban_mentioned'] == 'yes' and r['wider_brand_association'] == 'none']
        self.assertGreater(len(named_only), 0)

    def test_external_actors_contract_actions_and_inquiries_are_not_shared_guilt(self):
        for row in self.rows:
            flags = row['ambiguity_flags']
            if 'external_actor' in flags or 'commercial_action' in flags:
                self.assertEqual(row['responsibility_attributed'], 'unclear')
            if 'Meta_and_Sama' in flags:
                self.assertEqual(row['responsibility_attributed'], 'Meta')
            if row['source_category'] == 'official_regulatory':
                self.assertIn('inquiry_target_is_not_established_liability', flags)

    def test_review_corrections_preserve_original_and_previous_events(self):
        first = self.event(self.rows[0])
        second = self.event(self.rows[0], event_id='test-event-2', decision='correct', privacy_related='unclear')
        second['reviewed_at'] = '2026-11-16T13:00:00Z'
        events = [first, second]
        before = copy.deepcopy(events)
        reviewed = apply_review_events(self.rows, events)
        self.assertEqual(events, before)
        self.assertEqual(self.rows[0]['review_status'], 'pending_human_review')
        self.assertEqual(reviewed[0]['privacy_related'], 'yes')
        self.assertEqual(reviewed[0]['reviewed_privacy_related'], 'unclear')
        self.assertEqual(reviewed[0]['original_coding_json'], self.rows[0]['original_coding_json'])
        summary = summarize_groups(reviewed, reviewed=True)[0]
        self.assertEqual(summary['denominator'], 1)
        self.assertEqual(summary['privacy_related_unclear'], 1)

    def test_invalid_stale_or_mislabelled_reviews_are_rejected(self):
        for field, value in [('source_fingerprint', 'wrong'), ('reviewer_code', ''),
                             ('supporting_evidence', ''), ('reviewed_at', '2026-11-16T12:00:00'),
                             ('responsibility_attributed', 'Meta and Sama'), ('record_id', 'unknown')]:
            with self.subTest(field=field):
                event = self.event(self.rows[0])
                event[field] = value
                with self.assertRaises(ValueError):
                    apply_review_events(self.rows, [event])
        event = self.event(self.rows[0], privacy_related='no')
        with self.assertRaises(ValueError):
            apply_review_events(self.rows, [event])
        event = self.event(self.rows[0])
        with self.assertRaises(ValueError):
            apply_review_events(self.rows, [event, event])

    def test_excluded_reviews_never_enter_human_reviewed_denominators(self):
        reviewed = apply_review_events(self.rows, [self.event(self.rows[0], decision='exclude')])
        self.assertEqual(reviewed[0]['review_status'], 'excluded_by_reviewer')
        self.assertEqual(sum(r['denominator'] for r in summarize_groups(reviewed, reviewed=True)), 0)
        self.assertEqual(sum(r['denominator'] for r in summarize_groups(reviewed)), 32)

    def test_exclusion_is_still_counted_as_review_coverage_on_screen(self):
        reviewed = apply_review_events(self.rows, [self.event(self.rows[0], decision='exclude')])
        with patch('src.ui.media_evidence.load_media_rows', return_value=reviewed):
            app = AppTest.from_string('from src.ui.media_evidence import render_real_media\nrender_real_media()', default_timeout=30).run()
        self.assertEqual(list(app.exception), [])
        self.assertTrue(any('1/32' in item.value and '0 included, 1 excluded' in item.value for item in app.warning))

    def test_source_changes_and_customer_rows_are_blocked(self):
        articles = read_csv(DATA_DIR / 'articles.csv')
        quality = json.loads((DATA_DIR / 'dataset_quality.json').read_text(encoding='utf-8'))
        articles[0]['source_type'] = 'customer_discussion'
        with self.assertRaises(ValueError):
            prepare_rows(articles, quality)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'articles.csv').write_text('changed content', encoding='utf-8')
            (folder / 'dataset_quality.json').write_text(json.dumps(quality), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_media_rows(folder)

    def test_exported_summary_tables_match_live_calculations(self):
        stored = json.loads((DATA_DIR / 'media_summary_tables.json').read_text(encoding='utf-8'))
        self.assertEqual(stored['provisional'], summarize_groups(self.rows))
        self.assertEqual(stored['human_reviewed'], summarize_groups(self.rows, reviewed=True))
        self.assertEqual(stored['source_csv_sha256'], hashlib.sha256((DATA_DIR / 'articles.csv').read_bytes()).hexdigest())


class TestMediaDashboard(unittest.TestCase):
    def test_missing_local_corpus_has_no_synthetic_substitution(self):
        with tempfile.TemporaryDirectory() as directory, patch('src.ui.media_evidence.DATA_DIR', Path(directory)):
            app = AppTest.from_string('from src.ui.media_evidence import render_real_media\nrender_real_media()', default_timeout=30).run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(len(app.dataframe), 0)
            self.assertTrue(any('No synthetic replacement' in item.value for item in app.info))

    @unittest.skipUnless((DATA_DIR / 'articles.csv').exists(), 'Local media dataset is not distributed with code.')
    def test_media_is_separate_from_customer_metrics_and_needs_no_inference(self):
        rows = prepare_rows(read_csv(DATA_DIR / 'articles.csv'),
                            json.loads((DATA_DIR / 'dataset_quality.json').read_text(encoding='utf-8')))
        with patch('sqlite3.connect', side_effect=AssertionError('No SQLite access')), \
                patch('requests.Session.request', side_effect=AssertionError('No network or inference')), \
                patch('src.ui.media_evidence.load_media_rows', return_value=rows):
            app = AppTest.from_file(str(ROOT / 'cloud_app.py'), default_timeout=30).run()
            self.assertEqual(list(app.exception), [])
            self.assertIn('Real Media Evidence', [tab.label for tab in app.tabs])
            self.assertEqual(next(metric.value for metric in app.metric if metric.label == 'Genuine source references'), '32')
            self.assertEqual(next(metric.value for metric in app.metric if metric.label == 'Demo examples'), str(len(demo_discussions())))
            tables = [item.value for item in app.dataframe if 'denominator' in item.value.columns and 'basis' in item.value.columns]
            self.assertEqual(len(tables), 0)  # Public metadata never loads private review/proposal tables.
