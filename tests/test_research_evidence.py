"""Sourced context integrity, transparent synthetic results and offline integration."""
import copy
from datetime import date
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit

from streamlit.testing.v1 import AppTest

from scripts.benchmark_contagion import summarize
from scripts.run_case_study import load_cases, run
from src.ui.research_evidence import load_timeline, load_case_study
from src.analysis.evaluation import evaluate_pairs
from src.analysis.schema import validate_labels

ROOT = Path(__file__).resolve().parents[1]


class TestResearchEvidence(unittest.TestCase):
    def test_timeline_markdown_matches_dashboard_data_and_original_attribution(self):
        report = load_timeline()
        markdown = (ROOT / 'docs/CONTROVERSY_TIMELINE.md').read_text(encoding='utf-8')
        for row in report['events']:
            heading = f"## {row['date']} - {row['title']}"
            self.assertIn(heading, markdown)
            section = markdown.split(heading, 1)[1].split('\n## ', 1)[0]
            for field in ('description', 'limitation', 'date_basis', 'source_url', 'source_published_at'):
                self.assertIn(row[field], section)
        original = next(row for row in report['events'] if row['event_id'] == 'contractor_allegations_2026')
        self.assertEqual(original['date'], '2026-02-27')
        self.assertEqual(urlsplit(original['source_url']).netloc, 'www.svd.se')
        self.assertEqual(original['evidence_type'], 'Reported allegations')

    def test_raw_case_responses_reproduce_metrics_and_safeguard_decisions(self):
        report = load_case_study()
        raw_pairs, accepted_pairs = [], []
        for row in report['results']:
            prediction = json.loads(row['raw_output'])
            self.assertEqual(prediction, row['parsed_output'])
            pair = (prediction, row['reference'])
            raw_pairs.append(pair)
            if row['status'] == 'success':
                validate_labels(row['raw_output'], row['text'])
                accepted_pairs.append(pair)
            else:
                with self.assertRaises(ValueError):
                    validate_labels(row['raw_output'], row['text'])
        self.assertEqual(report['summary']['raw_metrics'], evaluate_pairs(raw_pairs))
        self.assertEqual(report['summary']['accepted_metrics'], evaluate_pairs(accepted_pairs))

    def test_timeline_dates_sources_and_epistemic_status(self):
        data = load_timeline()
        events = data['events']
        self.assertEqual(len(events), 15)
        self.assertEqual(len({row['event_id'] for row in events}), len(events))
        self.assertEqual({row['date'][:4] for row in events}, {'2023', '2024', '2025', '2026'})
        self.assertEqual(events, sorted(events, key=lambda row: row['date']))
        for row in events:
            self.assertLessEqual(date.fromisoformat(row['date']), date.fromisoformat(data['reviewed_at']))
            self.assertTrue(row['limitation'] and row['date_basis'] and row['publisher'])
            url = urlsplit(row['source_url'])
            self.assertEqual(url.scheme, 'https')
            self.assertTrue(url.netloc)
            self.assertIsNone(url.username)
            date.fromisoformat(row['source_published_at'])
        by_id = {row['event_id']: row for row in events}
        self.assertEqual(by_id['contractor_allegations_2026']['evidence_type'], 'Reported allegations')
        self.assertEqual(by_id['contractor_response_2026']['evidence_type'], 'Company response')
        self.assertEqual(by_id['senate_2026']['evidence_type'], 'Official inquiry')
        self.assertNotEqual(by_id['voice_privacy_2025']['date'], by_id['voice_privacy_2025']['source_published_at'])

    def test_case_set_is_distinct_frozen_and_covers_requested_contrasts(self):
        fixture = load_cases()
        self.assertEqual(len({row['category'] for row in fixture['examples']}), 6)
        self.assertEqual({row['labels']['spillover'] for row in fixture['examples']}, {'explicit', 'implicit', 'none', 'unclear'})
        previous = set()
        for name in ('contagion_regression_20.json', 'contagion_heldout_20.json'):
            data = json.loads((ROOT / 'tests/fixtures' / name).read_text(encoding='utf-8'))
            previous.update(case['text'] for case in data['examples'])
        self.assertFalse(previous & {row['text'] for row in fixture['examples']})

    def test_recorded_results_recompute_exactly_including_rejections(self):
        report = load_case_study()
        self.assertTrue(report['completed'])
        self.assertEqual(report['summary'], summarize(report['results']))
        self.assertEqual(report['summary']['n'], 24)
        failed = [row for row in report['results'] if row['status'] == 'failed']
        self.assertEqual(len(failed), 2)
        self.assertTrue(all(row['raw_output'] and row['validation'] != 'passed' for row in failed))
        implicit_error = next(row for row in report['results'] if row['case'] == 'case24_meta_data')
        self.assertEqual(implicit_error['status'], 'success')
        self.assertEqual(implicit_error['reference']['spillover'], 'none')
        self.assertEqual(implicit_error['parsed_output']['spillover'], 'implicit')

    def test_unmarked_or_mismatched_case_artifacts_are_blocked(self):
        original = load_case_study()
        for modification in ('marker', 'reference', 'missing'):
            with self.subTest(modification=modification), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'demo').mkdir()
                (root / 'tests/fixtures').mkdir(parents=True)
                data = copy.deepcopy(original)
                if modification == 'marker':
                    data['synthetic_only'] = False
                elif modification == 'reference':
                    data['results'][0]['reference']['spillover'] = 'explicit'
                else:
                    data['results'].pop()
                (root / 'demo/case_study_results.json').write_text(json.dumps(data), encoding='utf-8')
                (root / 'tests/fixtures/contagion_case_study_24.json').write_bytes(
                    (ROOT / 'tests/fixtures/contagion_case_study_24.json').read_bytes())
                with patch('src.ui.research_evidence.ROOT', root):
                    with self.assertRaises(ValueError):
                        load_case_study()

    def test_runner_preserves_failed_responses_and_never_overwrites_a_run(self):
        cases = load_cases()['examples']
        client = MagicMock()
        client.inspect.return_value = dict(model_name='test:local', model_version='mock-only', runtime_version='mock-only')
        bad_evidence = {**cases[1]['labels'], 'evidence_quotes': ['invented missing quotation']}
        client.generate.side_effect = ['invalid JSON', json.dumps(bad_evidence)] + [json.dumps(row['labels']) for row in cases[2:]]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'test-results.json'
            with patch('scripts.run_case_study.OllamaClient', return_value=client), \
                    patch('src.analysis.engine.OllamaClient', return_value=client):
                report = run(output, 'test:local')
                self.assertTrue(report['completed'])
                self.assertEqual(report['summary']['accepted'], 22)
                self.assertEqual(report['results'][0]['raw_output'], 'invalid JSON')
                self.assertEqual(report['results'][1]['status'], 'failed')
                fingerprint = hashlib.sha256(output.read_bytes()).hexdigest()
                with self.assertRaises(FileExistsError):
                    run(output, 'test:local')
                self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), fingerprint)


class TestEvidenceDashboard(unittest.TestCase):
    def test_timeline_and_case_filters_work_without_network_or_database(self):
        with patch('sqlite3.connect', side_effect=AssertionError('No research storage')), \
                patch('requests.Session.request', side_effect=AssertionError('No network')):
            app = AppTest.from_file(str(ROOT / 'cloud_app.py'), default_timeout=30).run()
            self.assertEqual(list(app.exception), [])
            evidence = next(tab for tab in app.tabs if tab.label == 'Evidence & Methodology')
            self.assertIn('Verified context, not customer sentiment', [item.value for item in evidence.subheader])
            app.multiselect(key='context_years').set_value(['2026']).run()
            app.multiselect(key='case_status').set_value(['failed']).run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(len(app.selectbox(key='case_output').options), 2)
            self.assertTrue(any('unsupported' in item.value.lower() for item in app.markdown))

    def test_empty_research_panels_hide_filters_charts_and_matrix(self):
        app = AppTest.from_string('''
from src.ui.contagion import analytics_panel, explorer_panel, evaluation_panel
analytics_panel([], False)
explorer_panel([], False)
evaluation_panel([], False)
''', default_timeout=30).run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(len(app.multiselect), 0)
        self.assertEqual(len(app.dataframe), 0)
        self.assertEqual(len(app.metric), 0)
