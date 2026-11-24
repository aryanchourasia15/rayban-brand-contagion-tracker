"""Public media coding remains traceable, provisional and independent of simulations."""
import copy
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from src.analysis.simulation import fingerprint
from src.ui.media_evidence import CHOICES, DATA_DIR, load_media_rows
from src.ui.media_insights import (load_media_snapshot, filter_media_records, media_totals,
                                   validate_snapshot, RECORD_FIELDS)
from src.ui.synthetic_reactions import load_public_sources


class TestMediaSnapshot(unittest.TestCase):
    def setUp(self):
        self.report = load_media_snapshot()
        self.manifest = load_public_sources()

    def test_all_source_links_and_original_coding_are_preserved_without_private_fields(self):
        rows = self.report['records']
        self.assertEqual({r['record_id'] for r in rows}, {s['source_id'] for s in self.manifest['sources']})
        self.assertEqual(len(rows), 32)
        self.assertTrue(all(set(r)==RECORD_FIELDS for r in rows))
        self.assertTrue(all(r['review_status']=='pending_human_review' for r in rows))
        self.assertEqual(media_totals(rows, reviewed=True)['denominator'], 0)
        if (DATA_DIR/'articles.csv').exists():
            original = {r['record_id']:r for r in load_media_rows()}
            for row in rows:
                self.assertEqual(row, {key:original[row['record_id']][key] for key in RECORD_FIELDS})

    def test_exact_group_denominators_and_distinct_naming_and_attribution(self):
        rows = self.report['records']
        totals = media_totals(rows)
        self.assertEqual((totals['denominator'], totals['privacy_related_yes'], totals['both_brands_named']), (32,14,30))
        self.assertEqual([totals['responsibility_attributed_'+v] for v in ('Meta','Ray-Ban','both','unclear')], [7,0,0,25])
        expected = [('independent_media',13,11,5,2), ('company_statements',17,1,0,0), ('official_regulatory',2,2,2,0)]
        for category, n, privacy, meta, traditional in expected:
            selected = filter_media_records(rows, categories=[category])
            result = media_totals(selected)
            self.assertEqual((result['denominator'], result['privacy_related_yes'], result['responsibility_attributed_Meta'],
                              result['wider_brand_association_explicit']), (n,privacy,meta,traditional))
        direct = [r for r in rows if r['wider_brand_association']=='explicit']
        self.assertEqual({r['association_direction'] for r in direct},
                         {'positive_traditional_brand_comparison', 'traditional_style_continuity'})

    def test_unknown_private_fields_and_broken_provenance_are_rejected(self):
        for key, value in [('reviewer_name','not-a-real-reviewer'), ('text','private full text')]:
            report = copy.deepcopy(self.report)
            report['records'][0][key] = value
            report['records_sha256'] = fingerprint(report['records'])
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_snapshot(report,self.manifest)
        for key in ('source_csv_sha256','source_manifest_sha256','records_sha256'):
            report = copy.deepcopy(self.report); report[key] = 'changed'
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_snapshot(report,self.manifest)
        report = copy.deepcopy(self.report)
        report['records'][0]['record_id'] = 'unlinked'
        report['records_sha256'] = fingerprint(report['records'])
        with self.assertRaises(ValueError):validate_snapshot(report,self.manifest)

    def test_only_resolved_included_labels_enter_reviewed_results(self):
        # Test-only review states in memory; no study ledger or snapshot is changed.
        rows = copy.deepcopy(self.report['records'][:4])
        for row, state in zip(rows, ('human_review_recorded','uncertain_pending_review','excluded_by_reviewer','pending_human_review')):
            row['review_status'] = state
            row.update({'reviewed_'+k:v for k,v in ((k,row[k]) for k in CHOICES)})
            row['reviewed_source_category'] = 'company_statements'
            row['reviewed_privacy_related'] = 'unclear'
        before = copy.deepcopy(rows)
        selected = filter_media_records(rows, categories=['company_statements'], reviewed=True)
        self.assertEqual(len(selected),1)
        self.assertEqual(media_totals(selected, reviewed=True)['denominator'],1)
        self.assertEqual(media_totals(selected, reviewed=True)['privacy_related_yes'],0)
        self.assertEqual(filter_media_records(rows,categories=['independent_media'], reviewed=True),[])
        self.assertEqual(rows,before)
        self.assertEqual(media_totals([], reviewed=True)['denominator'],0)


class TestMediaInsightsUI(unittest.TestCase):
    def test_category_filters_empty_reviewed_basis_and_public_only_reads(self):
        with patch('sqlite3.connect', side_effect=AssertionError('No database')), \
                patch('requests.Session.request', side_effect=AssertionError('No network')), \
                patch('src.ui.media_evidence.load_media_rows', side_effect=AssertionError('No private corpus at runtime')):
            app = AppTest.from_string('from src.ui.media_insights import render_media_insights\nrender_media_insights()', default_timeout=30).run()
            self.assertEqual(list(app.exception),[])
            metrics = {m.label:m.value for m in app.metric}
            self.assertEqual(metrics['Privacy-related coverage'],'14/32')
            self.assertEqual(metrics['Direct traditional-brand references'],'2/32')
            self.assertTrue(any('0/32 resolved human reviews' in w.value for w in app.warning))
            app.multiselect(key='media_insights_categories').set_value(['independent_media']).run()
            self.assertEqual(next(m.value for m in app.metric if m.label=='Privacy-related coverage'),'11/13')
            app.multiselect(key='media_insights_categories').set_value(['official_regulatory']).run()
            self.assertEqual(next(m.value for m in app.metric if m.label=='Ray-Ban named'),'0/2')
            app.radio(key='media_insights_basis').set_value('Human-reviewed coding only').run()
            self.assertEqual(list(app.exception),[])
            self.assertEqual(len(app.metric),0)
            self.assertEqual(len(app.dataframe),0)
            self.assertTrue(any('No included human-reviewed records' in i.value for i in app.info))


if __name__=='__main__':unittest.main()
