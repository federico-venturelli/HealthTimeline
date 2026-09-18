# Shared utilities used across all pages.

import base64
import streamlit as st
import pandas as pd
import database.db_manager as db
from pathlib import Path
from datetime import date, timedelta

UPLOADS_DIR  = Path(__file__).parent / "uploads"
PROJECT_ROOT = UPLOADS_DIR.parent


def save_uploaded_file(uploaded_file, subfolder):
    """Save a file from st.file_uploader to uploads/<subfolder>/.
    Returns the relative path string to store in the database."""
    folder = UPLOADS_DIR / subfolder
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / uploaded_file.name
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    # Store relative paths so the project remains portable.
    return str(file_path.relative_to(PROJECT_ROOT))


def resolve_file_path(relative_path):
    """Rebuild the absolute path from a relative path stored in the DB."""
    return PROJECT_ROOT / relative_path


def render_navbar():
    """Render the top navbar, sidebar, and global CSS.
    Call at the top of every page, right after imports."""

    # Hide Streamlit's auto-generated sidebar nav and apply brand colors.
    st.markdown("""
    <style>
    [data-testid="stSidebarNav"] { display: none !important; }
    [data-testid="stHeadingWithActionElements"] * { color: #219ebc !important; }
    [data-testid="stPageLink"] span { color: #219ebc !important; }
    [data-testid="stSidebar"] { background-color: #219ebc !important; }
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] span { color: black !important; }
    </style>
    """, unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("#### API Key")
        key_val = st.text_input(
            "Anthropic API Key",
            type="password",
            value=st.session_state.get("api_key", ""),
            placeholder="sk-ant-...",
            help="Required for AI features: lab extraction and normalization",
            label_visibility="collapsed",
        )
        if key_val:
            st.session_state["api_key"] = key_val
            st.caption("✓ Key set")
        else:
            st.session_state.pop("api_key", None)
            st.caption("No key — AI features disabled")

    # SVG logo encoded as base64 so it can be embedded inline in HTML
    # without needing a static file server.
    logo_path = Path(__file__).parent / "assets" / "logo.svg"
    logo_b64 = base64.b64encode(logo_path.read_bytes()).decode()

    pages = [
        ("pages/home.py",               "Home",        ":material/home:"),
        ("pages/vital_signs.py",        "Vitals",      ":material/monitor_heart:"),
        ("pages/medications.py",        "Medications", ":material/medication:"),
        ("pages/medical_conditions.py", "Conditions",  ":material/health_and_safety:"),
        ("pages/clinical_events.py",    "Events",      ":material/event_note:"),
        ("pages/lab_reports.py",        "Labs",        ":material/science:"),
        ("pages/spirometry.py",         "Spirometry",  ":material/air:"),
        ("pages/analysis.py",           "Analysis",    ":material/analytics:"),
    ]
    # [2] + [1] * N gives the column width ratio: brand takes twice the space of each nav link.
    col_brand, *nav_cols = st.columns([2] + [1] * len(pages))
    col_brand.markdown(
        f'<img src="data:image/svg+xml;base64,{logo_b64}" width="28" style="vertical-align:middle;margin-right:8px">'
        f'<span style="font-size:1.1rem;font-weight:700;vertical-align:middle;color:#003049">Health Timeline</span>',
        unsafe_allow_html=True,
    )
    for col, (page, label, icon) in zip(nav_cols, pages):
        col.page_link(page, label=label, icon=icon)
    st.divider()


def select_patient():
    """Guard function for pages that require a selected patient.
    Stops page execution if none is selected, with a link back to Home."""
    patient_id = st.session_state.get("patient_id")
    if not patient_id:
        st.warning("No patient selected. Please go to the Home page and select a patient.")
        st.page_link("pages/home.py", label="Go to Home")
        st.stop()
    return patient_id


def show_table_with_downloads(section_df, date_cols, key_prefix, drop_cols=None):
    """Render a DataFrame with formatted dates and a download expander for attached files.

    section_df:  DataFrame with 'File Path' and 'ID' columns
    date_cols:   column names to format as YYYY-MM-DD
    key_prefix:  unique prefix for download button keys
    drop_cols:   columns to hide from the displayed table
    """
    display = section_df.drop(columns=drop_cols or [], errors="ignore").copy()

    if "File Path" in display.columns:
        display["File Path"] = display["File Path"].apply(
            lambda x: Path(x).name if x and str(x) not in ("None", "") else ""
        )
        display = display.rename(columns={"File Path": "File"})

    for col in date_cols:
        if col in display.columns:
            display[col] = display[col].apply(lambda x: "" if pd.isna(x) else x.strftime("%Y-%m-%d"))

    st.dataframe(display, hide_index=True)

    files = section_df[section_df["File Path"].apply(lambda x: bool(x and str(x) not in ("None", "")))]
    if not files.empty:
        with st.expander("Downloads"):
            for _, row in files.iterrows():
                fp = row["File Path"]
                full_fp = resolve_file_path(fp)
                if full_fp.exists():
                    with open(full_fp, "rb") as f:
                        st.download_button(
                            Path(fp).name, f,
                            file_name=Path(fp).name,
                            key=f"{key_prefix}_{row['ID']}"
                        )


def period_date_filter(radio_key, slider_key, min_value, min_data_actual, max_data):
    """Reusable period selector: radio presets (1M/6M/1Y/All) synced with a date slider.

    Selecting a preset updates the slider. Moving the slider clears the preset.

    Returns: (start_date, end_date) tuple.
    """
    def _preset(p):
        if p == "All":
            return (min_data_actual, max_data)
        days = {"1M": 30, "6M": 180, "1Y": 365}[p]
        return (max(date.today() - timedelta(days=days), min_value), max_data)

    def _on_period():
        p = st.session_state.get(radio_key)
        if p:
            st.session_state[slider_key] = _preset(p)

    def _on_slider():
        # Setting to None deselects the radio (no preset active).
        st.session_state[radio_key] = None

    # Initialize to "All" only on first render; don't pass index= to avoid
    # conflicts when _on_slider sets the value to None.
    if radio_key not in st.session_state:
        st.session_state[radio_key] = "All"
    st.radio("Period", ["1M", "6M", "1Y", "All"], horizontal=True,
             key=radio_key, on_change=_on_period)
    return st.slider("Date range", min_value=min_value, max_value=max_data,
                     value=(min_data_actual, max_data),
                     key=slider_key, on_change=_on_slider)
