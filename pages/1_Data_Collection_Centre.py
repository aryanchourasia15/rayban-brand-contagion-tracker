import streamlit as st
from src.ui.runtime import app_mode

if app_mode() != 'local':
    st.info('Research data collection is available only in explicit local mode.')
    st.stop()

from src.ui.collection import render_collection_centre
render_collection_centre()
