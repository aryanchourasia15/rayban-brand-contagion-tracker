"""Human-review saves use isolated dataset copies, never the real review ledger."""
import csv
from concurrent.futures import ThreadPoolExecutor
import io
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src.ui import media_evidence as media


@unittest.skipUnless((media.DATA_DIR / 'human_review_template.csv').exists(),
                     'Private local media corpus is not shipped with source code.')
class TestMediaReviewWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        for name in ('articles.csv', 'dataset_quality.json', 'human_review_template.csv'):
            shutil.copyfile(media.DATA_DIR / name, self.directory / name)
        self.ledger = self.directory / 'media_review_events.csv'
        with self.ledger.open('w', encoding='utf-8-sig', newline='') as handle:
            csv.DictWriter(handle, fieldnames=media.REVIEW_FIELDS).writeheader()
        self.mode = patch.dict(os.environ, {'RAYBAN_APP_MODE': 'local'})
        self.mode.start()
        self.addCleanup(self.mode.stop)
        self.rows = media.load_media_rows(self.directory)

    def event(self, row=None, decision='confirm', **changes):
        row = row or self.rows[0]
        labels = {field: row[field] for field in media.CHOICES}
        labels.update(changes)
        return media.make_review_event(row, labels, 'unit-test-only', 'Test justification, not a real review.',
                                       'Test evidence, not a real review.', decision)

    def save(self, event, previous=''):
        return media.append_review_event(event, expected_latest_event_id=previous, directory=self.directory)

    def test_append_and_reclassification_preserve_all_original_bytes_and_events(self):
        original = (self.directory / 'articles.csv').read_bytes()
        prefix = self.ledger.read_bytes()
        first = self.event()
        self.assertTrue(self.save(first))
        self.assertTrue(self.ledger.read_bytes().startswith(prefix))
        prefix = self.ledger.read_bytes()
        row = media.load_media_rows(self.directory)[0]
        second = self.event(row, 'correct', privacy_related='unclear', source_category='official_regulatory')
        self.assertTrue(self.save(second, first['review_event_id']))
        self.assertTrue(self.ledger.read_bytes().startswith(prefix))
        self.assertEqual((self.directory / 'articles.csv').read_bytes(), original)
        self.assertEqual(media.read_csv(self.ledger), [first, second])
        current = media.load_media_rows(self.directory)
        self.assertEqual(current[0]['original_coding_json'], self.rows[0]['original_coding_json'])
        self.assertEqual(current[0]['privacy_related'], self.rows[0]['privacy_related'])
        self.assertEqual(current[0]['reviewed_privacy_related'], 'unclear')
        self.assertEqual([item['denominator'] for item in media.summarize_groups(current, reviewed=True)], [0, 0, 1])
        self.assertEqual(media.review_progress(current)['disagreements'], 1)

    def test_uncertain_stays_pending_until_explicit_resolution(self):
        first = self.event(decision='uncertain')
        self.save(first)
        current = media.load_media_rows(self.directory)
        progress = media.review_progress(current)
        self.assertEqual((progress['reviewed'], progress['pending'], progress['uncertain']), (0, 32, 1))
        self.assertEqual(sum(item['denominator'] for item in media.summarize_groups(current, reviewed=True)), 0)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(media.completed_review_csv(current).decode('utf-8-sig'))))), 0)
        self.save(self.event(current[0]), first['review_event_id'])
        progress = media.review_progress(media.load_media_rows(self.directory))
        self.assertEqual((progress['reviewed'], progress['pending'], progress['uncertain']), (1, 31, 0))
        self.assertEqual(len(media.read_csv(self.ledger)), 2)

    def test_exclusion_is_completed_but_never_an_analysis_denominator(self):
        self.save(self.event(decision='exclude'))
        current = media.load_media_rows(self.directory)
        self.assertEqual(media.review_progress(current)['reviewed'], 1)
        self.assertEqual(media.review_progress(current)['disagreements'], 1)
        self.assertEqual(sum(item['denominator'] for item in media.summarize_groups(current, reviewed=True)), 0)
        exported = list(csv.DictReader(io.StringIO(media.completed_review_csv(current).decode('utf-8-sig'))))
        self.assertEqual(exported[0]['reviewer_decision'], 'exclude')

    def test_stale_forms_and_reused_ids_cannot_overwrite_history(self):
        first, stale = self.event(), self.event(decision='correct', privacy_related='unclear')
        self.save(first)
        before = self.ledger.read_bytes()
        self.assertFalse(self.save(first))
        with self.assertRaises(media.ReviewConflictError):
            self.save(stale)
        altered = dict(first, reviewer_notes='Different payload')
        with self.assertRaises(media.ReviewConflictError):
            self.save(altered, first['review_event_id'])
        self.assertEqual(self.ledger.read_bytes(), before)

    def test_concurrent_article_saves_are_both_preserved(self):
        events = [self.event(self.rows[0]), self.event(self.rows[1])]
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(self.save, events)), [True, True])
        self.assertEqual(len(media.read_csv(self.ledger)), 2)
        self.assertEqual(media.review_progress(media.load_media_rows(self.directory))['reviewed'], 2)

    def test_invalid_or_missing_fields_never_append(self):
        before = self.ledger.read_bytes()
        for field, value in [('reviewer_code', ''), ('reviewer_notes', ''), ('supporting_evidence', ''),
                             ('privacy_related', 'invalid'), ('meta_mentioned', None),
                             ('source_fingerprint', 'changed'), ('reviewed_at', '2026-11-17')]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.save(dict(self.event(), **{field: value}))
        with self.assertRaises(ValueError):
            self.event(privacy_related='unclear')  # Confirm cannot silently correct.
        self.assertEqual(self.ledger.read_bytes(), before)

    def test_demo_mode_blocks_saves_before_creating_any_lock(self):
        with patch.dict(os.environ, {'RAYBAN_APP_MODE': 'demo'}), self.assertRaises(PermissionError):
            self.save(self.event())
        self.assertFalse((self.directory / '.media_review_events.lock').exists())
        self.assertEqual(media.read_csv(self.ledger), [])

    def test_mismatched_template_and_malformed_ledger_fail_closed(self):
        template = self.directory / 'human_review_template.csv'
        original = template.read_bytes()
        template.write_bytes(original.replace(self.rows[0]['source_fingerprint'].encode(), b'invalid'))
        with self.assertRaises(ValueError):
            self.save(self.event())
        self.assertEqual(media.read_csv(self.ledger), [])
        template.write_bytes(original)
        self.ledger.write_text('wrong,header\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.save(self.event())
        self.assertEqual(self.ledger.read_text(encoding='utf-8'), 'wrong,header\n')

    def test_export_uses_actual_latest_labels_and_escapes_only_download(self):
        event = self.event(decision='correct', privacy_related='unclear')
        event['reviewer_code'] = '=unit-test-only'
        self.save(event)
        rows = media.load_media_rows(self.directory)
        exported = list(csv.DictReader(io.StringIO(media.completed_review_csv(rows).decode('utf-8-sig'))))
        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0]['privacy_related'], 'unclear')
        self.assertEqual(exported[0]['reviewer_name'], "'=unit-test-only")
        self.assertEqual(exported[0]['reviewed_at'], event['reviewed_at'])
        self.assertEqual(media.read_csv(self.ledger)[0]['reviewer_code'], '=unit-test-only')

    def render(self, script='render_real_media(allow_review=True)'):
        return AppTest.from_string('from src.ui.media_evidence import render_real_media\n' + script,
                                   default_timeout=30).run()

    def test_local_form_explicit_save_and_refresh_never_auto_approve(self):
        with patch.object(media, 'DATA_DIR', self.directory), \
                patch('requests.Session.request', side_effect=AssertionError('No network')), \
                patch('sqlite3.connect', side_effect=AssertionError('No customer database')):
            app = self.render()
            self.assertEqual(list(app.exception), [])
            self.assertIsNone(app.radio[0].value)
            self.assertEqual(media.read_csv(self.ledger), [])
            app.text_input(key='media_reviewer_name').set_value('unit-test-only').run()
            app.radio[0].set_value('Correct classifications').run()
            next(item for item in app.selectbox if item.label == 'Media privacy related').set_value('unclear')
            next(item for item in app.text_area if item.label == 'Short review justification').set_value('Test correction only.')
            next(item for item in app.checkbox if item.label.startswith('I reviewed')).check()
            next(item for item in app.button if item.label == 'Save media review').click().run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(len(media.read_csv(self.ledger)), 1)
            self.assertEqual(media.read_csv(self.ledger)[0]['privacy_related'], 'unclear')
            self.assertEqual(next(item.value for item in app.metric if item.label == 'Reviewed / total'), '1/32')
            self.assertEqual(next(item.value for item in app.metric if item.label == 'Pending'), '31')
            app.run()
            self.assertEqual(len(media.read_csv(self.ledger)), 1)
            self.assertIsNone(app.radio[0].value)  # Next article requires a new deliberate decision.

    def test_unchecked_evidence_attestation_rejects_ui_save(self):
        with patch.object(media, 'DATA_DIR', self.directory):
            app = self.render()
            app.radio[0].set_value('Confirm proposed labels').run()
            next(item for item in app.button if item.label == 'Save media review').click().run()
            self.assertEqual(list(app.exception), [])
            self.assertTrue(any('source-evidence check' in item.value for item in app.error))
            self.assertEqual(media.read_csv(self.ledger), [])

    def test_demo_and_cloud_remain_read_only_even_with_local_environment(self):
        with patch.object(media, 'DATA_DIR', self.directory):
            for script, mode in [('render_real_media(allow_review=True)', 'demo'), ('render_real_media()', 'local')]:
                with self.subTest(script=script), patch.dict(os.environ, {'RAYBAN_APP_MODE': mode}):
                    app = self.render(script)
                    self.assertEqual(list(app.exception), [])
                    self.assertEqual(len(app.text_input), 0)
                    self.assertEqual(len(app.get('download_button')), 0)
            app = AppTest.from_file(str(media.ROOT / 'cloud_app.py'), default_timeout=30).run()
            self.assertEqual(list(app.exception), [])
            self.assertFalse(any(item.label == 'Save media review' for item in app.button))
            self.assertEqual(media.read_csv(self.ledger), [])

    def test_local_app_navigation_reaches_real_review_form_without_inference(self):
        with patch.object(media, 'DATA_DIR', self.directory), \
                patch('src.data.db.DB_PATH', self.directory / 'isolated-test.db'), \
                patch('requests.Session.request', side_effect=AssertionError('No live collection or inference')):
            app = AppTest.from_file(str(media.ROOT / 'app.py'), default_timeout=30).run()
            self.assertEqual(list(app.exception), [])
            app.switch_page('pages/2_Brand_Contagion_Analysis.py').run()
            self.assertEqual(list(app.exception), [])
            self.assertTrue(any(item.label == 'Save media review' for item in app.button))
            self.assertEqual(next(item.value for item in app.metric if item.label == 'Reviewed / total'), '0/32')
            self.assertEqual(media.read_csv(self.ledger), [])


if __name__ == '__main__':
    unittest.main()
