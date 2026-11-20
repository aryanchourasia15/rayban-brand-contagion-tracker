"""Safe-by-default entry point; explicitly opt into local research operations."""
import streamlit as st

from src.ui.runtime import app_mode


def main(*, cloud=False):
    st.set_page_config(page_title="Ray-Ban | Trust Intelligence", page_icon="◉", layout="wide")
    try:
        mode = app_mode(cloud=cloud)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    if mode == 'demo':
        from src.ui.contagion import render_contagion
        st.sidebar.info('DEMO MODE · Synthetic customer examples and separate sourced media · No research database or live AI')
        st.navigation([st.Page(lambda: render_contagion(force_demo=True),
                              title='Brand Contagion Demo', default=True)]).run()
    else:
        from src.analysis.storage import init_analysis_db
        init_analysis_db()
        st.sidebar.warning('LOCAL RESEARCH MODE · Keep this server on localhost')
        st.navigation([
            st.Page('pages/1_Data_Collection_Centre.py', title='Data Collection Centre', default=True),
            st.Page('pages/2_Brand_Contagion_Analysis.py', title='Brand Contagion Analysis'),
        ]).run()


if __name__ == '__main__':
    main()
