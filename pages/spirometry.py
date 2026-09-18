import html
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import date, timedelta
import database.db_manager as db
from utils import select_patient, save_uploaded_file, render_navbar
import ai_manager
from lab_utils import _load_norm_cache, _apply_normalization, _normalize_new_params, MEDIA_TYPES, render_norm_expander, save_lab_results

render_navbar()

# Max date columns visible at once in the pivot table.
MAX_DATE_COLS = 5


@st.dialog("Parameter trend")
def _show_chart(param, pdata, unit):
    """Simple line chart for a spirometry parameter — no OOB coloring
    since spirometry uses predicted percentages rather than fixed ranges."""
    df_plot = pdata.copy().sort_values("Date")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_plot["Date"], y=df_plot["Value Num"],
        mode="lines+markers", name=param,
        line=dict(color="#219ebc", width=2),
        marker=dict(size=10, color="#219ebc",
                    line=dict(width=1, color="DarkSlateGrey")),
        hovertemplate="%{y}<extra></extra>",
    ))
    fig.update_layout(
        yaxis_title=unit, plot_bgcolor="white",
        margin=dict(l=20, r=20, t=20, b=20), height=320,
        showlegend=False, hovermode="x unified",
    )
    st.plotly_chart(fig, width='stretch')
    st.dataframe(
        df_plot[["Date", "Value", "Unit"]].reset_index(drop=True),
        hide_index=True,
        width='stretch',
    )


def show_results(patient_id):
    """Pivot table for spirometry results — same layout as lab_reports but without OOB."""
    rows = db.get_lab_history(patient_id, "Spirometria")
    if not rows:
        st.info("No spirometry results yet.")
        return

    df = pd.DataFrame(rows, columns=["Date", "Parameter", "Value", "Unit", "Ref Min", "Ref Max", "Method"])
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")

    most_recent_orig = df.groupby(["Parameter", "Unit"])["Date"].max().reset_index()

    mapping = _load_norm_cache()
    if mapping:
        df = _apply_normalization(df, mapping)

    df["Value Num"] = pd.to_numeric(df["Value"], errors="coerce")
    render_norm_expander(most_recent_orig, mapping, "refresh_norm_spiro")
    all_dates  = sorted(df["Date"].unique())
    all_params = df["Parameter"].unique()

    if len(all_dates) > MAX_DATE_COLS:
        start = st.slider(
            "Scroll dates", 0, len(all_dates) - MAX_DATE_COLS,
            len(all_dates) - MAX_DATE_COLS,
            key="sl_spiro"
        )
        shown_dates = all_dates[start: start + MAX_DATE_COLS]
    else:
        shown_dates = all_dates

    st.markdown("""
    <style>
    [data-testid="stHorizontalBlock"] { gap: 0.25rem; align-items: center; }
    [data-testid="stMarkdownContainer"] p { margin: 0; line-height: 1.4; }
    </style>
    """, unsafe_allow_html=True)

    col_widths = [3, 1] + [2] * len(shown_dates) + [1]

    hcols = st.columns(col_widths)
    hcols[0].markdown("**Parameter**")
    hcols[1].markdown("**Unit**")
    for i, d in enumerate(shown_dates):
        hcols[2 + i].markdown(f"**{d}**")
    hcols[-1].markdown("**Info**")
    st.markdown("<hr style='margin:4px 0 2px 0; border:none; border-top:2px solid #e5e7eb;'>", unsafe_allow_html=True)

    def _fmt_val(v):
        try:
            return f"{float(str(v).replace(',', '.')):.2f}".rstrip("0").rstrip(".")
        except Exception:
            return str(v)

    for row_idx, param in enumerate(all_params):
        pdf = df[df["Parameter"] == param].sort_values("Date")
        unit = pdf["Unit"].iloc[-1] or ""
        numeric_rows = pdf[pdf["Value Num"].notna()].copy()
        num_by_date  = dict(zip(numeric_rows["Date"], numeric_rows["Value Num"]))

        row_bg = (
            "background:#f8fafc; border-radius:3px; padding:2px 4px; display:block;"
            if row_idx % 2 == 0
            else "padding:2px 4px; display:block;"
        )

        rcols = st.columns(col_widths)
        rcols[0].markdown(f"<div style='{row_bg}'><b>{html.escape(param)}</b></div>", unsafe_allow_html=True)
        rcols[1].markdown(f"<div style='{row_bg}'><b>{html.escape(unit)}</b></div>", unsafe_allow_html=True)

        for i, d in enumerate(shown_dates):
            match = pdf[pdf["Date"] == d]
            if match.empty:
                rcols[2 + i].markdown(
                    f"<div style='{row_bg}'><span style='color:#D1D5DB'>—</span></div>",
                    unsafe_allow_html=True
                )
                continue

            r = match.iloc[0]
            val_num     = r["Value Num"]
            val_display = _fmt_val(r["Value"])

            # Blue dot — no OOB concept for spirometry.
            cell_html = f"<span style='color:#219ebc'>●</span> {val_display}"

            if pd.notna(val_num):
                prev_dates = [x for x in sorted(num_by_date.keys()) if x < d]
                if prev_dates and num_by_date[prev_dates[-1]] != 0:
                    prev_val    = num_by_date[prev_dates[-1]]
                    delta       = (val_num - prev_val) / abs(prev_val) * 100
                    arrow       = "↗" if delta >= 0 else "↘"
                    delta_color = "#F59E0B" if abs(delta) > 20 else "#9CA3AF"
                    cell_html  += (
                        f"<br><span style='color:{delta_color};font-size:0.85em'>"
                        f"{arrow} {delta:+.1f}%</span>"
                    )

            rcols[2 + i].markdown(f"<div style='{row_bg}'>{cell_html}</div>", unsafe_allow_html=True)

        if not numeric_rows.empty:
            if rcols[-1].button("📊", key=f"chart_spiro_{param}"):
                _show_chart(param, numeric_rows, unit)
        else:
            rcols[-1].markdown("")

        st.markdown("<hr style='margin:2px 0; border:none; border-top:1px solid #f0f2f6;'>", unsafe_allow_html=True)


# ── Page ──────────────────────────────────────────────────────────────────────
st.header(":material/air: Spirometry")

patient_id = select_patient()
birth_date = date.fromisoformat(db.get_patient(patient_id)[3])
min_date   = birth_date - timedelta(days=365)

tab_his, tab_ins = st.tabs(["History", "Insert"])

with tab_his:
    show_results(patient_id)

with tab_ins:
    if "spiro_pending_date" in st.session_state:
        st.session_state["spiro_report_date"] = st.session_state.pop("spiro_pending_date")

    col1, col2 = st.columns(2)
    report_date = col1.date_input("Date", key="spiro_report_date", min_value=min_date, max_value=date.today())
    notes = col2.text_input("Notes", placeholder="Optional")

    mode = st.radio("Entry mode", ["Manual", "Upload & AI extract"], horizontal=True)

    if mode == "Manual":
        results = st.data_editor(
            pd.DataFrame({
                "Parameter": [""] * 3, "Value": [""] * 3,
                "Unit": [""] * 3, "Method": [""] * 3,
            }),
            num_rows="dynamic",
            width='stretch',
            key="spiro_editor_manual",
        )
        if st.button("Save", type="primary"):
            valid = results[
                results["Parameter"].notna() & results["Parameter"].ne("") &
                results["Value"].notna() & results["Value"].ne("")
            ]
            if valid.empty:
                st.error("Enter at least one result with parameter name and value.")
            else:
                report_id = db.add_lab_report(patient_id, str(report_date), "Spirometria", None, notes or None)
                save_lab_results(report_id, valid)
                with st.spinner("Normalizing new parameters…"):
                    _normalize_new_params(valid, str(report_date))
                st.success("Saved!")
                if "spiro_editor_manual" in st.session_state:
                    del st.session_state["spiro_editor_manual"]
                st.rerun()

    else:  # Upload & AI extract
        uploaded_file = st.file_uploader(
            "Spirometry report (PDF, JPG, PNG)",
            type=["pdf", "jpg", "jpeg", "png"]
        )
        if uploaded_file and st.button("Extract from document"):
            ext = uploaded_file.name.rsplit(".", 1)[-1].lower()
            with st.spinner("AI is reading the document…"):
                try:
                    extracted = ai_manager.extract_spirometry_data(
                        uploaded_file.getvalue(),
                        MEDIA_TYPES[ext]
                    )
                    if extracted["date"]:
                        try:
                            parsed_date = date.fromisoformat(extracted["date"])
                            if min_date <= parsed_date <= date.today():
                                st.session_state["spiro_pending_date"] = parsed_date
                        except ValueError:
                            pass
                    raw_results = extracted["results"]
                    spiro_rows = [
                        {
                            "Parameter": r.get("parameter", ""),
                            "Value":     r.get("value", ""),
                            "Unit":      r.get("unit", ""),
                            "Method":    r.get("method", ""),
                        }
                        for r in raw_results
                    ]
                    st.session_state["spiro_extracted_data"] = pd.DataFrame(spiro_rows)
                    if "spiro_editor_ai" in st.session_state:
                        del st.session_state["spiro_editor_ai"]
                    st.rerun()
                except Exception as e:
                    st.error(f"Extraction failed: {e}")

        default_ai_df = pd.DataFrame({
            "Parameter": [""] * 3, "Value": [""] * 3,
            "Unit": [""] * 3, "Method": [""] * 3,
        })
        results = st.data_editor(
            st.session_state.get("spiro_extracted_data", default_ai_df),
            num_rows="dynamic",
            width='stretch',
            key="spiro_editor_ai",
        )
        if st.button("Save", type="primary"):
            valid = results[
                results["Parameter"].notna() & results["Parameter"].ne("") &
                results["Value"].notna() & results["Value"].ne("")
            ]
            if valid.empty:
                st.error("Enter at least one result with parameter name and value.")
            else:
                file_path = save_uploaded_file(uploaded_file, "lab_reports") if uploaded_file else None
                report_id = db.add_lab_report(patient_id, str(report_date), "Spirometria", file_path, notes or None)
                save_lab_results(report_id, valid)
                with st.spinner("Normalizing new parameters…"):
                    _normalize_new_params(valid, str(report_date))
                st.success("Saved!")
                for key in ("spiro_editor_ai", "spiro_extracted_data", "spiro_report_date"):
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
