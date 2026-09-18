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
st.header(":material/science: Lab reports")

patient_id = select_patient()
birth_date = date.fromisoformat(db.get_patient(patient_id)[3])
min_date = birth_date - timedelta(days=365)

# Max number of date columns visible at once; a slider lets the user scroll if there are more.
MAX_DATE_COLS = 5


# ── Trend chart dialog ────────────────────────────────────────────────────────
@st.dialog("Parameter trend")
def _show_chart(param, pdata, unit):
    """Modal chart for a single parameter's history with reference range band."""
    df_plot = pdata.copy().sort_values("Date")
    df_plot["Ref Min"] = pd.to_numeric(df_plot["Ref Min"], errors="coerce")
    df_plot["Ref Max"] = pd.to_numeric(df_plot["Ref Max"], errors="coerce")

    # Y-axis ceiling for open-ended bands (only min or only max present).
    max_val = df_plot["Value Num"].max()
    max_ref = df_plot["Ref Max"].max() if df_plot["Ref Max"].notna().any() else 0
    base_max = max(
        max_val if pd.notna(max_val) else 0,
        max_ref if pd.notna(max_ref) else 0,
    )
    if base_max == 0:
        base_max = 10
    y_ceiling = base_max * 2.0

    def _band_bounds(row):
        lo, hi = row["Ref Min"], row["Ref Max"]
        if pd.notna(lo) and pd.notna(hi):
            return lo, hi
        if pd.notna(lo):
            return lo, y_ceiling
        if pd.notna(hi):
            return 0.0, hi
        return None, None

    bounds = df_plot.apply(_band_bounds, axis=1, result_type="expand")
    df_plot["BandMin"] = bounds[0]
    df_plot["BandMax"] = bounds[1]

    def _color(row):
        v = row["Value Num"]
        if pd.isna(v):
            return "#219ebc"
        lo, hi = row["Ref Min"], row["Ref Max"]
        if pd.isna(lo) and pd.isna(hi):
            return "#219ebc"
        if pd.notna(lo) and v < lo:
            return "#ef4444"
        if pd.notna(hi) and v > hi:
            return "#ef4444"
        return "#00CC96"

    df_plot["MarkerColor"] = df_plot.apply(_color, axis=1)

    fig = go.Figure()

    has_band = df_plot["BandMin"].notna().any()
    if has_band:
        if len(df_plot) > 1:
            # Two invisible boundary traces + fill="tonexty" draws the reference band.
            fig.add_trace(go.Scatter(
                x=df_plot["Date"], y=df_plot["BandMin"],
                mode="lines", line=dict(width=0),
                hoverinfo="skip", showlegend=False,
            ))
            fig.add_trace(go.Scatter(
                x=df_plot["Date"], y=df_plot["BandMax"],
                mode="lines", line=dict(width=0),
                fill="tonexty", fillcolor="rgba(0, 204, 150, 0.3)",
                hoverinfo="skip", showlegend=False,
            ))
        else:
            # Single data point: draw a rect shape instead (fill="tonexty" needs 2+ points).
            row0 = df_plot.iloc[0]
            ts = pd.to_datetime(row0["Date"])
            x0, x1 = ts - pd.Timedelta(days=4), ts + pd.Timedelta(days=4)
            if pd.notna(row0["BandMin"]) and pd.notna(row0["BandMax"]):
                fig.add_shape(
                    type="rect", x0=x0, x1=x1,
                    y0=row0["BandMin"], y1=row0["BandMax"],
                    fillcolor="rgba(0, 204, 150, 0.3)",
                    line=dict(width=0), layer="below",
                )
            fig.update_xaxes(range=[x0, x1])

    fig.add_trace(go.Scatter(
        x=df_plot["Date"], y=df_plot["Value Num"],
        mode="lines+markers", name=param,
        line=dict(color="#aaaaaa", width=2),
        marker=dict(size=10, color=df_plot["MarkerColor"],
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
        df_plot[["Date", "Value", "Unit", "Ref Min", "Ref Max"]].reset_index(drop=True),
        hide_index=True,
        width='stretch',
    )


# ── Pivot table of results ────────────────────────────────────────────────────
def show_results(patient_id, category):
    """Render a pivot table: rows = parameters, columns = exam dates.
    Cells show value, OOB color, reference range, and trend vs previous exam.
    Called separately for Blood and Urine tabs.
    """
    rows = db.get_lab_history(patient_id, category)
    if not rows:
        st.info(f"No {category.lower()} results yet.")
        return

    df = pd.DataFrame(rows, columns=["Date", "Parameter", "Value", "Unit", "Ref Min", "Ref Max", "Method"])
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")

    # Compute most_recent_orig BEFORE normalization — the Refresh button needs original names.
    most_recent_orig = df.groupby(["Parameter", "Unit"])["Date"].max().reset_index()

    mapping = _load_norm_cache()
    if mapping:
        df = _apply_normalization(df, mapping)

    df["Value Num"] = pd.to_numeric(df["Value"], errors="coerce")
    render_norm_expander(most_recent_orig, mapping, f"refresh_norm_{category}")
    all_dates  = sorted(df["Date"].unique())
    all_params = df["Parameter"].unique()

    if len(all_dates) > MAX_DATE_COLS:
        start = st.slider(
            "Scroll dates", 0, len(all_dates) - MAX_DATE_COLS,
            len(all_dates) - MAX_DATE_COLS, key=f"sl_{category}"
        )
        shown_dates = all_dates[start : start + MAX_DATE_COLS]
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

    def _fmt_ref(v):
        try:
            return f"{float(v):.2f}".rstrip("0").rstrip(".")
        except Exception:
            return "—"

    for row_idx, param in enumerate(all_params):
        pdf = df[df["Parameter"] == param].sort_values("Date")
        unit = pdf["Unit"].iloc[-1] or ""
        numeric_rows = pdf[pdf["Value Num"].notna()].copy()
        num_by_date  = dict(zip(numeric_rows["Date"], numeric_rows["Value Num"]))

        row_bg = "background:#f8fafc; border-radius:3px; padding:2px 4px; display:block;" if row_idx % 2 == 0 else "padding:2px 4px; display:block;"

        rcols = st.columns(col_widths)
        # html.escape() prevents XSS if a parameter name contains HTML characters.
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
            val = r["Value"]
            val_num = r["Value Num"]
            oob = pd.notna(val_num) and (
                (pd.notna(r["Ref Min"]) and val_num < r["Ref Min"]) or
                (pd.notna(r["Ref Max"]) and val_num > r["Ref Max"])
            )

            try:
                val_display = f"{float(str(val).replace(',', '.')):.2f}".rstrip("0").rstrip(".")
            except (ValueError, TypeError):
                val_display = str(val)

            dot_color = "#D32F2F" if oob else "#00CC96"
            val_html  = f"<span style='color:#D32F2F;font-weight:bold'>{val_display}</span>" if oob else val_display
            cell_html = f"<span style='color:{dot_color}'>●</span> {val_html}"

            ref_min, ref_max = r["Ref Min"], r["Ref Max"]
            if pd.notna(ref_min) or pd.notna(ref_max):
                lo = _fmt_ref(ref_min) if pd.notna(ref_min) else "—"
                hi = _fmt_ref(ref_max) if pd.notna(ref_max) else "—"
                cell_html += f"<br><span style='color:#9CA3AF;font-size:0.78em'>[{lo}–{hi}]</span>"

            # Trend arrow vs the most recent prior exam with a numeric value.
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
            if rcols[-1].button("📊", key=f"chart_{category}_{param}"):
                _show_chart(param, numeric_rows, unit)
        else:
            rcols[-1].markdown("")

        st.markdown("<hr style='margin:2px 0; border:none; border-top:1px solid #f0f2f6;'>", unsafe_allow_html=True)


# ── Page layout ───────────────────────────────────────────────────────────────
tab_his, tab_ins = st.tabs(["History", "Insert"])

with tab_his:
    sub_blood, sub_urine = st.tabs(["Blood", "Urine"])
    with sub_blood:
        show_results(patient_id, "Blood")
    with sub_urine:
        show_results(patient_id, "Urine")

with tab_ins:
    # Transfer AI-extracted date before the date_input widget is instantiated,
    # otherwise Streamlit ignores the session state update.
    if "ai_pending_date" in st.session_state:
        st.session_state["ins_report_date"] = st.session_state.pop("ai_pending_date")

    col1, col2 = st.columns(2)
    report_date = col1.date_input("Date", key="ins_report_date", min_value=min_date, max_value=date.today())
    notes = col2.text_input("Notes", placeholder="Optional")

    mode = st.radio("Entry mode", ["Manual", "Upload & AI extract"], horizontal=True)

    if mode == "Manual":
        category = st.selectbox("Category", ["Blood", "Urine"])
        results = st.data_editor(
            pd.DataFrame({
                "Parameter": [""] * 3, "Value": [""] * 3, "Unit": [""] * 3,
                "Ref Min": [None, None, None], "Ref Max": [None, None, None],
                "Method": [""] * 3,
            }),
            num_rows="dynamic",
            width='stretch',
            key="lab_editor_manual",
            column_config={
                "Ref Min": st.column_config.NumberColumn("Ref Min"),
                "Ref Max": st.column_config.NumberColumn("Ref Max"),
            }
        )
        if st.button("Save", type="primary"):
            valid = results[
                results["Parameter"].notna() & results["Parameter"].ne("") &
                results["Value"].notna() & results["Value"].ne("")
            ]
            if valid.empty:
                st.error("Enter at least one result with parameter name and value.")
            else:
                report_id = db.add_lab_report(patient_id, str(report_date), category, None, notes or None)
                save_lab_results(report_id, valid)
                with st.spinner("Normalizing new parameters…"):
                    _normalize_new_params(valid, str(report_date))
                st.success("Saved!")
                if "lab_editor_manual" in st.session_state:
                    del st.session_state["lab_editor_manual"]
                st.rerun()

    else:  # Upload & AI extract
        uploaded_file = st.file_uploader(
            "Lab report (PDF, JPG, PNG)",
            type=["pdf", "jpg", "jpeg", "png"]
        )
        if uploaded_file and st.button("Extract from document"):
            ext = uploaded_file.name.rsplit(".", 1)[-1].lower()
            with st.spinner("AI is reading the document…"):
                try:
                    extracted = ai_manager.extract_lab_data(
                        uploaded_file.getvalue(),
                        MEDIA_TYPES[ext]
                    )
                    if extracted["date"]:
                        try:
                            parsed_date = date.fromisoformat(extracted["date"])
                            if min_date <= parsed_date <= date.today():
                                st.session_state["ai_pending_date"] = parsed_date
                        except ValueError:
                            pass
                    st.session_state["ai_extracted_data"] = pd.DataFrame(extracted["results"]).rename(columns={
                        "parameter": "Parameter", "value": "Value", "unit": "Unit",
                        "ref_min": "Ref Min", "ref_max": "Ref Max",
                        "method": "Method", "category": "Category",
                    })
                    if "lab_editor_ai" in st.session_state:
                        del st.session_state["lab_editor_ai"]
                    st.rerun()
                except Exception as e:
                    st.error(f"Extraction failed: {e}")

        default_ai_df = pd.DataFrame({
            "Category": ["Blood"] * 3, "Parameter": [""] * 3, "Value": [""] * 3,
            "Unit": [""] * 3, "Ref Min": [None, None, None], "Ref Max": [None, None, None],
            "Method": [""] * 3,
        })
        results = st.data_editor(
            st.session_state.get("ai_extracted_data", default_ai_df),
            num_rows="dynamic",
            width='stretch',
            key="lab_editor_ai",
            column_config={
                "Category": st.column_config.SelectboxColumn("Category", options=["Blood", "Urine"], required=True),
                "Ref Min": st.column_config.NumberColumn("Ref Min"),
                "Ref Max": st.column_config.NumberColumn("Ref Max"),
            }
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
                for cat, cat_rows in valid.groupby("Category"):
                    report_id = db.add_lab_report(patient_id, str(report_date), cat, file_path, notes or None)
                    save_lab_results(report_id, cat_rows)
                with st.spinner("Normalizing new parameters…"):
                    _normalize_new_params(valid, str(report_date))
                st.success("Saved!")
                for key in ("lab_editor_ai", "ai_extracted_data", "ins_report_date"):
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
