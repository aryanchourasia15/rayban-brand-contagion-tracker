"""Story hierarchy and chart boundaries for the unchanged synthetic corpus."""
import json
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from src.ui.synthetic_reactions import ROOT, load_simulation
from src.ui.strategic_story import QUESTION, CONCLUSION, SECTIONS, readable, render_count_chart


class TestStrategicStory(unittest.TestCase):
    def test_landing_mechanisms_and_appendix_are_separate_and_offline(self):
        with patch('sqlite3.connect', side_effect=AssertionError('No database')), \
                patch('requests.Session.request', side_effect=AssertionError('No inference or network')):
            app = AppTest.from_file(str(ROOT/'cloud_app.py'), default_timeout=30).run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.title[0].value, QUESTION)
        sections = {tab.label:tab for tab in app.tabs if tab.label in SECTIONS}
        self.assertEqual(list(sections), SECTIONS)
        self.assertTrue(any(item.value == CONCLUSION for item in sections['Strategic Question'].info))
        dataset, _, _ = load_simulation()
        cards = '\n'.join(item.value for item in sections['Strategic Question'].markdown)
        for record_id in ('SIM-0001', 'SIM-0080', 'SIM-0133'):
            row = next(r for r in dataset['records'] if r['synthetic_id']==record_id)
            from html import escape
            self.assertIn(escape(row['text']), cards)
            self.assertIn(record_id, cards)
        self.assertEqual(len(sections['Strategic Question'].get('json')), 0)
        self.assertEqual(len(sections['Brand Contagion Analysis'].get('json')), 0)
        self.assertGreater(len(sections['Research Appendix'].get('json')), 0)
        process = '\n'.join(item.value for item in sections['Evidence & Methodology'].markdown)
        self.assertIn('32 genuine news sources', process)
        self.assertIn('260 AI-generated scenarios', process)

    def test_readable_chart_labels_preserve_exact_counts_and_input(self):
        counts = {'explicit': 30, 'implicit': 30, 'none': 190, 'unclear': 10}
        original = dict(counts)
        with patch('streamlit.vega_lite_chart') as chart, patch('streamlit.markdown'), \
                patch('streamlit.caption') as caption, patch('streamlit.write'):
            render_count_chart(counts, 'Test', 'Interpretation', basis='Design references')
        spec = chart.call_args.args[0]
        self.assertEqual(sum(v['Scenarios'] for v in spec['data']['values']), 260)
        self.assertEqual(spec['data']['values'][0]['Label'], 'Explicit wider-brand distrust')
        self.assertIn('n=260', caption.call_args.args[0])
        self.assertEqual(counts, original)
        self.assertNotIn('privacy_product_criticism', readable('privacy_product_criticism'))
        self.assertNotIn('_', readable('meta_responsibility_brand_protected'))

    def test_purchase_chart_does_not_mislabel_intention_as_behaviour(self):
        with patch('streamlit.vega_lite_chart') as chart, patch('streamlit.markdown'), \
                patch('streamlit.caption'), patch('streamlit.write'):
            render_count_chart({'negative':3, 'positive':2, 'unclear':1}, 'Test', 'Test',
                               basis='Accepted AI predictions', field='purchase_intent')
        labels = [row['Label'] for row in chart.call_args.args[0]['data']['values']]
        self.assertEqual(labels, ['Less willing to purchase', 'More willing to purchase', 'Unclear / not stated'])


if __name__ == '__main__':
    unittest.main()
