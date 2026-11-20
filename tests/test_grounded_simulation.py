"""Synthetic artefact integrity and offline public-demo interaction checks."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from streamlit.testing.v1 import AppTest

from src.analysis.simulation import (NOTICE, fingerprint, validate_sources, validate_scenarios,
    scenario_distributions, filter_scenarios, evaluate_simulation, diversity_report, display_basis, generation_content_issues)
from src.analysis.schema import validate_labels
from src.analysis.ollama_client import LocalModelError
from src.ui.synthetic_reactions import ROOT, load_public_sources, load_simulation
from scripts.build_grounded_demo import make_plan
from scripts import build_grounded_demo as builder
from src.data.importers.file_importer import validate_and_transform_rows


class TestGroundedSimulation(unittest.TestCase):
    def setUp(self):
        self.sources = load_public_sources()['sources']
        self.events = json.loads((ROOT / 'demo/research_timeline.json').read_text(encoding='utf-8'))['events']
        self.tasks = make_plan(self.sources, self.events)
        self.report = dict(is_synthetic=True, notice=NOTICE, source_manifest_sha256=fingerprint(self.sources), records=[])
        for task in self.tasks:
            self.report['records'].append(dict(task, text='A unit test example only with sufficient words ' + task['synthetic_id'],
                is_synthetic=True, source_kind='AI-generated simulation', generation_prompt_version='grounded-reactions-1.0.0',
                generation_model_version='unit-test-model-only'))

    def test_plan_has_exact_quotas_all_sources_and_no_anticipatory_dates(self):
        quality = validate_scenarios(self.report, self.sources, self.events)
        self.assertEqual(quality['n'], 260)
        self.assertEqual(quality['source_coverage'], 32)
        self.assertEqual(set(quality['years']), {'2023', '2024', '2025', '2026'})
        self.assertEqual([self.tasks.count(task) for task in self.tasks], [1] * 260)
        dist = scenario_distributions(self.report['records'])
        self.assertEqual(dist['spillover']['explicit'], 30)
        self.assertEqual(dist['spillover']['implicit'], 30)
        self.assertEqual(sum(dist['sentiment'].values()), 260)

    def test_wrong_dates_unmarked_synthetic_texts_and_duplicates_are_rejected(self):
        cases = [('is_synthetic', False), ('simulated_publication_date', '2023-01-01'),
                 ('simulated_publication_year', 2022), ('text', 'Follow @inventedcustomer for customer reactions'),
                 ('related_article_ids', ['unknown-article'])]
        for field, value in cases:
            report = copy.deepcopy(self.report)
            report['records'][0][field] = value
            with self.subTest(field=field), self.assertRaises((ValueError, KeyError)):
                validate_scenarios(report, self.sources, self.events)
        report = copy.deepcopy(self.report)
        report['records'][1]['text'] = report['records'][0]['text'].upper()
        with self.assertRaises(ValueError):
            validate_scenarios(report, self.sources, self.events)

    def test_public_manifest_rejects_private_fields_and_untraceable_urls(self):
        for field, value in [('reviewer_name', 'private'), ('url', 'https://user:password@example.org/article')]:
            sources = copy.deepcopy(self.sources)
            sources[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_sources(sources)
        self.assertFalse(any('text' in source or 'supporting_evidence' in source for source in self.sources))

    def test_source_manifest_matches_original_metadata_when_available(self):
        path = ROOT / 'data/research_news_2023_2026/articles.csv'
        if not path.exists():
            self.skipTest('Private original corpus is intentionally absent in public deployments.')
        import csv
        import hashlib
        with path.open(encoding='utf-8-sig', newline='') as handle:
            original = {r['source_id']: r for r in csv.DictReader(handle)}
        self.assertEqual(load_public_sources()['source_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        for source in self.sources:
            for key in ('title', 'url', 'publisher', 'published_at', 'event_topic'):
                self.assertEqual(source[key], original[source['source_id']][key])

    def test_filters_are_combined_and_never_change_the_underlying_dataset(self):
        records = self.report['records']
        before = copy.deepcopy(records)
        selected = filter_scenarios(records, years=[2026], sentiments=['negative'], responsibilities=['Meta'], spillovers=['explicit'])
        self.assertTrue(selected)
        self.assertTrue(all(r['simulated_publication_year'] == 2026 and r['expected_labels']['spillover'] == 'explicit' for r in selected))
        self.assertEqual(records, before)
        self.assertEqual(filter_scenarios(records, years=[2022]), [])

    def test_lexical_diversity_reports_similar_phrasings_without_calling_them_realistic(self):
        records = [dict(synthetic_id='SIM-a', text='I prefer ordinary frames because privacy matters a lot to me'),
                   dict(synthetic_id='SIM-b', text='I prefer ordinary frames because privacy matters a lot to us')]
        quality = diversity_report(records)
        self.assertEqual(quality['unique_four_word_openings'], 1)
        self.assertEqual(len(quality['high_similarity_pairs']), 1)
        self.assertIn('do not establish', quality['limitation'])

    def test_comments_and_frozen_references_match_recorded_generation(self):
        path = ROOT / 'demo/grounded_scenarios.json'
        if not path.exists():
            self.skipTest('No local generation recorded yet.')
        dataset = json.loads(path.read_text(encoding='utf-8'))
        generation = json.loads((ROOT / 'demo/simulation_generation.json').read_text(encoding='utf-8'))
        self.assertTrue(generation['is_synthetic'])
        self.assertEqual(fingerprint(generation['plan']), dataset['plan_sha256'])
        plan = {task['synthetic_id']: task for task in generation['plan']}
        accepted = {}
        for attempt in generation['attempts']:
            if attempt['status'] == 'accepted':
                for row in json.loads(attempt['raw_output'])['comments']:
                    accepted.setdefault(row['synthetic_id'], []).append(row['text'])
        for row in dataset['records']:
            self.assertIn(row['text'], accepted[row['synthetic_id']])
            self.assertEqual(row['expected_labels'], plan[row['synthetic_id']]['expected_labels'])
            self.assertEqual(row['generation_model_version'], dataset['generation_model']['model_version'])
        selected = {event['synthetic_id'] for event in generation.get('selection_events', [])}
        self.assertTrue(all(len(texts) == 1 or key in selected for key, texts in accepted.items()))

    def test_generation_wording_checks_are_distinct_from_classifier_labels(self):
        row = dict(scenario_category='meta_responsibility_brand_protected', text='I still like the design.')
        self.assertTrue(generation_content_issues(row))
        row['text'] = 'Meta should answer privacy questions; my traditional Ray-Ban frames still suit me.'
        self.assertEqual(generation_content_issues(row), [])
        row.update(scenario_category='wider_brand_distrust', text='I would avoid those camera glasses.')
        self.assertTrue(generation_content_issues(row))
        row['text'] = 'The whole brand makes me uneasy now.'
        self.assertEqual(generation_content_issues(row), [])

    def test_preclassification_content_review_preserves_audit_and_cannot_follow_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            dataset = copy.deepcopy(self.report)
            dataset['completed'] = True
            datafile, logfile, resultfile = (folder / name for name in ('data.json', 'log.json', 'results.json'))
            datafile.write_text(json.dumps(dataset), encoding='utf-8')
            logfile.write_text(json.dumps({'plan': self.tasks, 'attempts': []}), encoding='utf-8')
            with patch.object(builder, 'ROOT', folder), patch.object(builder, 'DATA_FILE', datafile), \
                    patch.object(builder, 'LOG_FILE', logfile), patch.object(builder, 'RESULT_FILE', resultfile), \
                    patch.object(builder, 'generate') as generate:
                builder.repair_generation('qwen2.5:3b')
                generate.assert_called_once_with('qwen2.5:3b')
                archived = json.loads(next((folder / 'benchmarks').glob('grounded_generation_before_content_review_*.json')).read_text(encoding='utf-8'))
                self.assertEqual(archived, dataset)
                remaining = json.loads(datafile.read_text(encoding='utf-8'))
                self.assertFalse(remaining['completed'])
                self.assertEqual(len(remaining['records']), 140)
                self.assertEqual(len(json.loads(logfile.read_text(encoding='utf-8'))['selection_events']), 120)
                before = datafile.read_bytes()
                resultfile.write_text('{}', encoding='utf-8')
                with self.assertRaises(ValueError):
                    builder.repair_generation('qwen2.5:3b')
                self.assertEqual(datafile.read_bytes(), before)

    def test_rejection_is_abstention_not_a_negative_prediction(self):
        labels = self.tasks[60]['expected_labels']
        wrong = dict(labels, spillover='none')
        results = [dict(case='a', reference=labels, parsed_output=wrong, label_fields_evaluable=True,
                        status='failed', seconds=1),
                   dict(case='b', reference=labels, label_fields_evaluable=False, status='failed', seconds=2)]
        summary = evaluate_simulation(results)
        self.assertEqual((summary['n'], summary['evaluable'], summary['accepted'], summary['rejected']), (2, 1, 0, 2))
        self.assertEqual(summary['false_negatives'], ['a'])
        self.assertEqual(summary['rejected_reference_positives'], ['a', 'b'])
        self.assertIsNone(summary['accepted_metrics']['explicit_spillover']['recall'])
        self.assertEqual(evaluate_simulation([])['n'], 0)
        rows = self.report['records'][:2]
        actual = dict(rows[0]['expected_labels'], sentiment='neutral')
        results = [dict(case=rows[0]['synthetic_id'], status='success', parsed_output=actual),
                   dict(case=rows[1]['synthetic_id'], status='failed')]
        selected = display_basis(rows, results)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['active_labels']['sentiment'], 'neutral')
        self.assertEqual(rows[0]['expected_labels']['sentiment'], 'negative')
        self.assertEqual(scenario_distributions(selected, label_key='active_labels')['sentiment'], {'neutral': 1})

    def test_generated_export_markers_prevent_accidental_real_data_import(self):
        for marker in ({'is_synthetic': True}, {'is_synthetic': 'True'}, {'source_kind': 'AI-generated simulation'}):
            raw = dict(text='Synthetic example only, not a customer record.', **marker)
            valid, invalid = validate_and_transform_rows([raw])
            self.assertEqual(valid, [])
            self.assertIn('is_synthetic=True', invalid[0]['errors'][0])
            valid, invalid = validate_and_transform_rows([raw], is_synthetic=True)
            self.assertEqual(invalid, [])
            self.assertEqual(valid[0]['is_synthetic'], 1)

    def test_saved_outputs_are_real_consistent_and_preserve_rejections(self):
        dataset, output, manifest = load_simulation()
        if not dataset or not output:
            self.skipTest('Local inference run not yet recorded.')
        by_id = {r['synthetic_id']: r for r in dataset['records']}
        self.assertTrue(all(r['generation_model'] == 'qwen2.5:3b' for r in dataset['records']))
        for row in output['results']:
            if row.get('raw_output'):
                try:
                    self.assertEqual(json.loads(row['raw_output']), row['parsed_output'])
                except json.JSONDecodeError:
                    self.assertEqual(row['status'], 'failed')
            if row['status'] == 'success':
                validate_labels(row['raw_output'], by_id[row['case']]['text'])
            elif row.get('raw_output'):
                with self.assertRaises(ValueError):
                    validate_labels(row['raw_output'], by_id[row['case']]['text'])
        self.assertEqual(output['summary'], evaluate_simulation(output['results']))

    def test_mocked_pipeline_checkpoints_failures_and_resumes_without_reclassifying(self):
        client = MagicMock()
        client.inspect.return_value = dict(model_name='qwen2.5:3b', model_version='unit-test-only', runtime_version='unit-test-only')
        calls = []

        def response(method, path, payload):
            task = json.loads(payload['messages'][1]['content'])['tasks'][0]
            calls.append(task['synthetic_id'])
            text = task['synthetic_id'] + ' ' + ' '.join(['unit-test-only word'] * 20)
            if len(calls) == 1:
                raise LocalModelError('Unit-test-only connection failure.')
            if len(calls) == 2:
                raw = '{"comments": []}'  # Retain malformed generation attempt.
            else:
                raw = json.dumps({'comments': [{'synthetic_id': task['synthetic_id'], 'text': text}]})
            return dict(model='qwen2.5:3b', done=True, done_reason='stop', message={'content': raw})

        client._call.side_effect = response
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'docs').mkdir()
            (folder / 'research_timeline.json').write_text(json.dumps({'events': self.events}), encoding='utf-8')
            (folder / 'media_sources.json').write_text(json.dumps({'sources': self.sources}), encoding='utf-8')
            with patch.object(builder, 'DEMO', folder), \
                    patch.object(builder, 'ROOT', folder), \
                    patch.object(builder, 'SOURCE_FILE', folder / 'media_sources.json'), \
                    patch.object(builder, 'DATA_FILE', folder / 'grounded_scenarios.json'), \
                    patch.object(builder, 'LOG_FILE', folder / 'simulation_generation.json'), \
                    patch.object(builder, 'RESULT_FILE', folder / 'simulation_classifications.json'), \
                    patch.object(builder, 'prepare_sources', return_value=self.sources), \
                    patch.object(builder, 'OllamaClient', return_value=client), \
                    patch.dict(builder.CATEGORY_COUNTS, {'privacy_product_criticism': 2}, clear=True):
                with self.assertRaises(LocalModelError):
                    builder.generate('qwen2.5:3b')
                interrupted = builder.read(builder.LOG_FILE)['attempts'][0]
                self.assertEqual(interrupted['status'], 'transport_failure')
                self.assertIsNone(interrupted['raw_output'])
                builder.generate('qwen2.5:3b')
                generated = builder.read(builder.DATA_FILE)
                self.assertEqual(len(generated['records']), 2)
                self.assertEqual(builder.read(builder.LOG_FILE)['attempts'][1]['status'], 'rejected')
                self.assertTrue((folder / 'grounded_scenarios.csv').exists())
                first = generated['records'][0]
                good = dict(first['expected_labels'], confidence=0.8, rationale='Unit-test-only rationale.',
                            evidence_quotes=[first['text']])
                client.generate.side_effect = [json.dumps(good), 'null']
                with patch('src.analysis.engine.OllamaClient', return_value=client):
                    builder.classify('qwen2.5:3b')
                    result = builder.read(builder.RESULT_FILE)
                    self.assertEqual((result['summary']['accepted'], result['summary']['rejected']), (1, 1))
                    self.assertEqual(result['results'][1]['raw_output'], 'null')
                    self.assertFalse(result['results'][1]['label_fields_evaluable'])
                    builder.classify('qwen2.5:3b')
                    self.assertEqual(client.generate.call_count, 2)


class TestGroundedDemoUI(unittest.TestCase):
    def test_public_app_filters_work_without_private_files_database_or_network(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch('src.ui.media_evidence.DATA_DIR', Path(directory)), \
                patch('sqlite3.connect', side_effect=AssertionError('No real research database')), \
                patch('requests.Session.request', side_effect=AssertionError('No inference or source requests')):
            app = AppTest.from_file(str(ROOT / 'cloud_app.py'), default_timeout=30).run()
            self.assertEqual(list(app.exception), [])
            self.assertTrue(any(NOTICE in item.value for item in app.warning))
            self.assertEqual(next(item.value for item in app.metric if item.label == 'Genuine source references'), '32')
            if any(item.key == 'simulation_years' for item in app.multiselect):
                app.multiselect(key='simulation_years').set_value([2026]).run()
                app.multiselect(key='simulation_sentiments').set_value(['negative']).run()
                app.multiselect(key='simulation_spillovers').set_value(['explicit']).run()
                self.assertEqual(list(app.exception), [])
                app.multiselect(key='simulation_sentiments').set_value(['positive']).run()
                self.assertEqual(list(app.exception), [])
                self.assertTrue(any('No scenarios match' in item.value for item in app.info))
                app.radio(key='simulation_basis').set_value('Accepted local AI predictions').run()
                self.assertEqual(list(app.exception), [])
            self.assertFalse(any(item.label == 'Save media review' for item in app.button))


if __name__ == '__main__':
    unittest.main()
