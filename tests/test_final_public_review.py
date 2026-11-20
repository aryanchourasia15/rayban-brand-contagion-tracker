"""Final publication boundaries, 50-case review traceability and versioned evidence."""
import hashlib
import json
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path

from streamlit.testing.v1 import AppTest
from src.analysis.schema import validate_labels
from src.ui.synthetic_reactions import ROOT, PUBLIC_RELEASE, load_simulation, load_review_proposals


class TestFinalReview(unittest.TestCase):
    def test_stratified_proposals_preserve_sources_and_are_not_human_labels(self):
        report=load_review_proposals()
        self.assertEqual(report['summary']['strata'], {'all_designed_explicit':30,'product_or_Meta_criticism':10,'implicit_or_brand_protection':10})
        designed=[r for r in report['records'] if r['stratum']=='all_designed_explicit']
        self.assertEqual({r['synthetic_id'] for r in designed}, {f'SIM-{i:04}' for i in range(61,91)})
        self.assertEqual(report['summary']['designed_explicit_proposals'], {'explicit':12,'implicit':10,'none':6,'unclear':2})
        for row in report['records']:
            self.assertIn('pending independent human',row['review_status'])
            self.assertTrue(all(q in row['text'] for q in row['evidence_quotes']))
            self.assertIn(row['historical_status'],('success','failed'))

    def test_history_counts_and_all_rejected_outputs_are_preserved(self):
        dataset,output,sources=load_simulation()
        self.assertEqual((len(dataset['records']),len(sources['sources'])),(260,32))
        self.assertEqual((output['summary']['accepted'],output['summary']['rejected']),(220,40))
        failed=[r for r in output['results'] if r['status']=='failed']
        self.assertTrue(all(r['raw_output'] and r['validation']!='passed' for r in failed))
        self.assertEqual(sum(r['parsed_output']['spillover']=='explicit' for r in output['results'] if r['status']=='success'),0)

    def test_evidence_upgrade_is_opt_in_and_handles_actual_direct_core_language(self):
        proposals={r['synthetic_id']:r for r in load_review_proposals()['records']}
        for key in ('SIM-0068','SIM-0080'):
            row=proposals[key]
            labels=dict(row['proposed_labels'],confidence=.7,rationale=row['proposal_rationale'],evidence_quotes=row['evidence_quotes'])
            with self.subTest(key=key):
                with self.assertRaises(ValueError):validate_labels(labels,row['text'])
                self.assertEqual(validate_labels(labels,row['text'],evidence_version='context-evidence-2.0')['spillover'],'explicit')

    def test_new_guard_keeps_product_defence_negation_and_quote_checks(self):
        examples=["I won't buy Ray-Ban Meta because of privacy but I still trust traditional Ray-Ban.",
                  "I don't trust Meta because of privacy but I still trust ordinary Ray-Ban.",
                  "I do not distrust traditional Ray-Ban because of Meta privacy concerns.",
                  "Meta has privacy problems and I love traditional Ray-Ban."]
        for text in examples:
            labels=dict(sentiment='mixed',target='both',responsibility='unclear',spillover='explicit',
                        purchase_intent='unclear',topic=['privacy'],confidence=.7,rationale='Test only.',evidence_quotes=[text])
            with self.subTest(text=text),self.assertRaises(ValueError):
                validate_labels(labels,text,evidence_version='context-evidence-2.0')
        labels['evidence_quotes']=['invented quote']
        with self.assertRaises(ValueError):validate_labels(labels,examples[-1],evidence_version='context-evidence-2.0')

    def test_historical_assets_unchanged_when_local_audit_snapshot_is_available(self):
        snapshot=ROOT/'benchmarks/finalization_original_hashes.json'
        if not snapshot.exists():self.skipTest('Private development hash snapshot intentionally not shipped.')
        for filename,digest in json.loads(snapshot.read_text(encoding='utf-8')).items():
            self.assertEqual(hashlib.sha256((ROOT/filename).read_bytes()).hexdigest(),digest,filename)

    def test_review_hashes_survive_windows_to_cloud_line_endings(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'demo').mkdir()
            for filename in ('grounded_scenarios.json','simulation_classifications.json','classification_review_proposals.json'):
                content=(ROOT/'demo'/filename).read_text(encoding='utf-8').replace('\r\n','\n')
                (root/'demo'/filename).write_bytes(content.encode('utf-8'))
            with patch('src.ui.synthetic_reactions.ROOT',root):
                self.assertEqual(load_review_proposals()['summary']['n'],50)


class TestFinalPublicPage(unittest.TestCase):
    def test_public_overview_voice_filters_review_and_sources_are_offline(self):
        with patch('sqlite3.connect',side_effect=AssertionError('No database in cloud')), \
                patch('requests.Session.request',side_effect=AssertionError('No network in cloud')):
            app=AppTest.from_file(str(ROOT/'cloud_app.py'),default_timeout=30).run()
            self.assertEqual(list(app.exception),[])
            values={item.label:item.value for item in app.metric}
            for label,value in [('Simulated customer reactions','260'),('Contextual news sources','32'),
                                ('Accepted model classifications','220'),('Rejected model classifications','40')]:
                self.assertEqual(values[label],value)
            self.assertTrue(any(PUBLIC_RELEASE in c.value for c in app.caption))
            self.assertIn('Customer voice',[t.label for t in app.tabs])
            app.selectbox(key='public_voice_status').select('Rejected predictions').run()
            self.assertEqual(list(app.exception),[])
            self.assertTrue(any('Showing 40/260' in item.value for item in app.markdown))
            app.multiselect(key='public_voice_years').set_value([2026]).run()
            app.multiselect(key='public_voice_responsibilities').set_value(['Meta']).run()
            self.assertEqual(list(app.exception),[])
            app.radio(key='public_voice_basis').set_value('Accepted local AI predictions').run()
            self.assertEqual(list(app.exception),[])
            self.assertTrue(any('No scenarios match' in item.value for item in app.info))
            self.assertFalse(any(b.label=='Save media review' for b in app.button))


if __name__=='__main__':unittest.main()
