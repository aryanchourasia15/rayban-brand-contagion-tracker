import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
import tempfile

from scripts.benchmark_contagion import load_sets, summarize
from src.analysis.engine import load_prompt, PROMPT_VERSION, classify_record
from src.analysis.schema import LABELS, TOPICS
from src.analysis.storage import init_analysis_db, get_history
from src.data.db import insert_record


class TestContagionPromptVersions(unittest.TestCase):
    def test_original_reference_labels_and_twenty_cases_are_fixed(self):
        regression, _ = load_sets()
        self.assertEqual(regression['sha256'], '0c7a0e8ee49ad6f2fa89cb58d12230ae3b3acee41d4f63d142e8797b7b5788c4')
        original = json.loads((Path(__file__).parent / 'fixtures' / 'synthetic_contagion.json').read_text(encoding='utf-8'))
        self.assertEqual(regression['examples'][:10], original['examples'])

    def test_heldout_disjoint_and_references_have_valid_contract_fields(self):
        regression, heldout = load_sets()
        self.assertEqual(len({c['text'] for c in regression['examples'] + heldout['examples']}), 40)
        for case in heldout['examples']:
            with self.subTest(case=case['case']):
                labels = case['labels']
                for field, choices in LABELS.items():
                    self.assertIn(labels[field], choices)
                self.assertTrue(labels['topic'] and all(t in TOPICS for t in labels['topic']))
                self.assertTrue(all(q in case['text'] for q in labels['evidence_quotes']))
                self.assertNotIn(case['text'], load_prompt(PROMPT_VERSION))

    def test_prompts_are_versioned_sequential_and_reject_unknown_paths(self):
        old = load_prompt('brand-contagion-1.0.0')
        new = load_prompt(PROMPT_VERSION)
        self.assertNotEqual(old, new)
        for step in ('STEP A', 'STEP B', 'STEP C', 'STEP D', 'STEP E'):
            self.assertIn(step, new)
        self.assertIn('Respect negation', new)
        self.assertIn('JSON SCHEMA:', new)
        with self.assertRaises(ValueError):
            load_prompt('../unknown')

    def test_selected_prompt_and_audit_version_match(self):
        regression, _ = load_sets()
        case = regression['examples'][0]
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'test.db'
            init_analysis_db(db)
            record_id = insert_record(dict(source='Imported', source_type='customer_discussion',
                collection_method='CSV import', text=case['text'], is_synthetic=True), db_path=db)
            client = MagicMock()
            client.inspect.return_value = dict(model_name='test', model_version='test', runtime_version='test')
            client.generate.return_value = json.dumps(case['labels'])
            with patch('src.analysis.engine.OllamaClient', return_value=client):
                for version in ('brand-contagion-1.0.0', PROMPT_VERSION):
                    classify_record(record_id, 'test', db_path=db, prompt_version=version)
                    self.assertEqual(client.generate.call_args.args[0], load_prompt(version))
            self.assertEqual([a['prompt_version'] for a in get_history(record_id, db)['attempts']],
                             ['brand-contagion-1.0.0', PROMPT_VERSION])

    def test_benchmark_reports_failures_without_treating_them_as_negative_predictions(self):
        case = load_sets()[0]['examples'][0]
        result = summarize([dict(case='invalid', reference=case['labels'], status='failed', seconds=1,
                                 label_fields_evaluable=False)])
        self.assertEqual(result['n'], 1)
        self.assertEqual(result['evaluable'], 0)
        self.assertEqual(result['accepted'], 0)
        self.assertIsNone(result['raw_metrics']['explicit_spillover']['accuracy'])
