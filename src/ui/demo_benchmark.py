"""Read-only, public-safe summary of previously completed synthetic local inference."""
import json
from pathlib import Path


SUMMARY_PATH = Path(__file__).resolve().parents[2] / 'demo' / 'benchmark_summary.json'


def load_benchmark():
    report = json.loads(SUMMARY_PATH.read_text(encoding='utf-8'))
    if report.get('synthetic_only') is not True:
        raise ValueError('Public benchmark must be explicitly synthetic.')
    return report


def render_benchmark():
    import pandas as pd
    import streamlit as st

    with st.expander('Existing local AI benchmark · synthetic examples only'):
        report = load_benchmark()
        st.caption(f"Recorded offline results for {report['model']['model_name']}. "
                   'No inference runs on this server. Raw-label scores include predictions rejected '
                   'by safeguards; rejected outputs are abstentions, not negative labels. '
                   'These small synthetic samples do not measure real-world accuracy.')
        selected = st.selectbox('Benchmark cohort', ['Held-out (20 examples)', 'Regression (20 examples)'])
        heldout = selected.startswith('Held-out')
        rows = []
        for version in ('1.0.0', '2.0.0'):
            key = ('heldout:' if heldout else 'regression:') + 'brand-contagion-' + version
            if key not in report['comparison']:
                key = 'regression_v1'
            score = report['comparison'][key]
            rows.append(dict(prompt=version, n=score['n'], accepted=score['accepted'],
                             **score['accuracy'], topic_exact_match=score['topic_exact_match'],
                             precision=score['explicit']['precision'], recall=score['explicit']['recall'],
                             f1=score['explicit']['f1'], seconds_per_comment=score['mean_seconds']))
        frame = pd.DataFrame(rows)
        st.dataframe(frame, hide_index=True)
        st.bar_chart(frame.set_index('prompt')[['precision', 'recall', 'f1']])
        st.caption('Explicit-spillover precision / recall / F1, fractions from 0 to 1. '
                   'Historical regression timings are not a controlled speed comparison. '
                   'Held-out comparisons alternate v1/v2 order; v2 was frozen before evaluation.')
        with st.expander('Benchmark provenance and confusion counts'):
            st.json(report)
