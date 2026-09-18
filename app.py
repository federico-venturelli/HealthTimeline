# Entry point. Run with: streamlit run app.py
# Initializes the DB and wires up the multi-page router.

import streamlit as st
import database.db_manager as db

# set_page_config must be called once, here in the router, not in individual pages.
st.set_page_config(layout="wide", page_title="Health Timeline", page_icon=":material/monitor_heart:")

# Safe to call every startup — uses CREATE TABLE IF NOT EXISTS under the hood.
db.init_db()

# position="hidden" suppresses Streamlit's auto-generated sidebar nav.
# We use our own navbar via render_navbar() in utils.py.
pages = [
    st.Page("pages/home.py",               title="Home"),
    st.Page("pages/vital_signs.py",        title="Vitals"),
    st.Page("pages/medications.py",        title="Medications"),
    st.Page("pages/medical_conditions.py", title="Conditions"),
    st.Page("pages/clinical_events.py",    title="Events"),
    st.Page("pages/lab_reports.py",        title="Labs"),
    st.Page("pages/spirometry.py",         title="Spirometry"),
    st.Page("pages/analysis.py",           title="Analysis"),
]

pg = st.navigation(pages, position="hidden")
pg.run()
