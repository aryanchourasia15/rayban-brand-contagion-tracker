"""Cloud demo must work without credentials, database access or network requests."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src.ui.runtime import app_mode
from src.ui.demo_benchmark import load_benchmark

ROOT = Path(__file__).resolve().parents[1]


class TestDeploymentMode(unittest.TestCase):
    def test_importing_configuration_needs_no_writable_data_directory(self):
        import importlib
        import src.config
        with patch('pathlib.Path.mkdir', side_effect=AssertionError('No startup directory writes')):
            importlib.reload(src.config)

    def test_safe_default_explicit_local_and_invalid_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(app_mode(), 'demo')
        with patch.dict(os.environ, {'RAYBAN_APP_MODE': 'local'}):
            self.assertEqual(app_mode(), 'local')
            self.assertEqual(app_mode(cloud=True), 'demo')
        with patch.dict(os.environ, {'RAYBAN_APP_MODE': 'typo'}):
            with self.assertRaises(ValueError):
                app_mode()
            self.assertEqual(app_mode(cloud=True), 'demo')

    def test_public_summary_matches_existing_recorded_results(self):
        report = load_benchmark()
        self.assertTrue(report['synthetic_only'])
        score = report['comparison']['heldout:brand-contagion-2.0.0']
        self.assertEqual((score['n'], score['accepted']), (20, 16))
        self.assertEqual((score['explicit']['tp'], score['explicit']['fp'], score['explicit']['fn']), (5, 1, 0))
        self.assertNotIn('raw_output', json.dumps(report))
        self.assertNotIn('text', report)

    def test_unmarked_summary_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / 'summary.json'
            summary.write_text('{"synthetic_only": false}', encoding='utf-8')
            with patch('src.ui.demo_benchmark.SUMMARY_PATH', summary):
                with self.assertRaises(ValueError):
                    load_benchmark()


class TestCloudApplication(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'RAYBAN_APP_MODE': 'local',
                                          'GUARDIAN_API_KEY': '', 'GUARDIAN_PERMISSION_REFERENCE': ''})
        self.env.start()
        self.addCleanup(self.env.stop)
        for target in ('sqlite3.connect', 'requests.Session.request'):
            guard = patch(target, side_effect=AssertionError('Demo must not access database or network'))
            guard.start()
            self.addCleanup(guard.stop)

    def app(self):
        app = AppTest.from_file(str(ROOT / 'cloud_app.py'), default_timeout=30).run()
        self.assertEqual(list(app.exception), [])
        return app

    def test_cloud_ignores_local_setting_and_has_no_research_controls(self):
        app = self.app()
        self.assertIn('Brand Contagion Analysis', [item.value for item in app.title])
        self.assertFalse(any(item.label == 'Analysis mode' for item in app.radio))
        self.assertEqual(len(app.get('file_uploader')), 0)
        self.assertFalse(any('Ollama' in button.label or 'Classify approved' in button.label for button in app.button))
        self.assertTrue(any('SYNTHETIC DEMONSTRATION' in item.value for item in app.warning))

    def test_demo_filters_benchmark_review_and_refresh_stay_offline(self):
        app = self.app()
        app.text_input(key='voice_search_True').set_value('traditional').run()
        self.assertEqual(list(app.exception), [])
        app.selectbox[0].select('Regression (20 examples)').run()
        self.assertEqual(list(app.exception), [])
        app.text_input(key='voice_search_True').set_value('').run()
        next(item for item in app.text_input if item.label == 'Reviewer identifier').set_value('Demo reviewer')
        next(item for item in app.text_input if item.label == 'Reason for correction or confirmation').set_value('Synthetic demonstration')
        next(item for item in app.button if item.label == 'Save human review').click().run()
        self.assertEqual(list(app.exception), [])
        self.assertTrue(app.session_state['contagion_demo_reviews'])
        next(item for item in app.button if item.label == 'Refresh analysis').click().run()
        self.assertEqual(list(app.exception), [])

    def test_default_entry_is_demo_and_collection_page_is_gated(self):
        with patch.dict(os.environ, {'RAYBAN_APP_MODE': 'demo'}):
            app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
            self.assertEqual(list(app.exception), [])
            app = AppTest.from_file(str(ROOT / 'pages' / '1_Data_Collection_Centre.py')).run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(len(app.get('file_uploader')), 0)


class TestLocalApplication(unittest.TestCase):
    def test_local_mode_retains_collection_with_an_isolated_database(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'local-test.db'
            with patch.dict(os.environ, {'RAYBAN_APP_MODE': 'local'}), \
                    patch('src.data.db.DB_PATH', database), \
                    patch('requests.Session.request', side_effect=AssertionError('No automatic collection')):
                app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
                self.assertEqual(list(app.exception), [])
                self.assertTrue(database.exists())
                self.assertIn('Data Collection Centre', [item.value for item in app.title])
                self.assertEqual(len(app.get('file_uploader')), 1)
