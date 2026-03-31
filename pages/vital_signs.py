import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import date, time, timedelta
import database.db_manager as db
from config import PARAMETER_MAP, PARAM_TO_CAT
from utils import select_patient, period_date_filter, render_navbar

render_navbar()
st.header(":material/monitor_heart: Vital signs")

patient_id = select_patient()
birth_date = date.fromisoformat(db.get_patient(patient_id)[3])
min_date   = birth_date - timedelta(days=365)

tab_his, tab_ins = st.tabs(["History", "Insert"])

# ── Insert ────────────────────────────────────────────────────────────────────
with tab_ins:
    # clear_on_submit=True resets all fields after a successful save.
    with st.form("form_vitals", clear_on_submit=True):
        measurement_date = st.date_input(
            "Date",
            value=date.today(),
            min_value=min_date,
            max_value=date.today(),
        )
        measurement_time = st.time_input("Time", value=time(0, 0))
        st.divider()

        inputs = {}

        # Build the form dynamically from PARAMETER_MAP — one column per parameter per category.
        for category, parameters in PARAMETER_MAP.items():
            st.subheader(category)
            cols = st.columns(len(parameters))
            for i, (param, info) in enumerate(parameters.items()):
                inputs[param] = cols[i].number_input(
                    f"{param} ({info['unit']})",
                    min_value=info['min_value'],
                    value=info['value'],
                    step=info['step']
                )

        notes = st.text_input("General notes", placeholder="Optional")
        submitted = st.form_submit_button("Save")

        if submitted:
            saved = False
            # Only save parameters with a value > 0 (0 means "not filled in").
            for param, val in inputs.items():
                if val > 0:
                    cat  = PARAM_TO_CAT[param]
                    unit = PARAMETER_MAP[cat][param]["unit"]
                    db.add_vital_sign(patient_id, measurement_date, str(measurement_time), cat, param, val, unit, notes)
                    saved = True
            if saved:
                st.success("Saved!")
                st.rerun()
            else:
                st.warning("Enter at least one value greater than 0.")

# ── History ───────────────────────────────────────────────────────────────────
with tab_his:
    all_params = [param for params in PARAMETER_MAP.values() for param in params]
    selected_param = st.selectbox("Parameter", all_params)

    rows = db.get_vital_signs(patient_id)
    if not rows:
        st.info("No data yet.")
    else:
        df_all = pd.DataFrame(rows, columns=["ID", "Patient ID", "Date", "Time", "Category", "Parameter", "Value", "Unit", "Notes"])
        df_all["Date"] = pd.to_datetime(df_all["Date"])
        min_data_actual = df_all["Date"].min().date()
        max_data        = date.today()

        start_filter, end_filter = period_date_filter(
            "vs_period_radio", "vs_date_slider", birth_date, min_data_actual, max_data
        )

        df_param = df_all[df_all["Parameter"] == selected_param].copy().sort_values("Date")
        df_chart = df_param[
            (df_param["Date"].dt.date >= start_filter) &
            (df_param["Date"].dt.date <= end_filter)
        ]

        if not df_chart.empty:
            unit = df_param["Unit"].iloc[0]
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_chart["Date"], y=df_chart["Value"],
                fill="tozeroy", fillcolor="rgba(33, 158, 188, 0.1)",
                mode="lines+markers", name=selected_param,
            ))
            fig.update_layout(
                title=selected_param, xaxis_title="Date", yaxis_title=unit,
                xaxis_range=[pd.Timestamp(start_filter), pd.Timestamp(end_filter)],
            )
            st.plotly_chart(fig, width='stretch')
        elif df_param.empty:
            st.info("No data recorded for this parameter.")
        else:
            st.info("No data in this period.")

        st.subheader(":material/table_rows: Data")
        if df_param.empty:
            st.info("No data recorded for this parameter.")
        else:
            display = df_param.drop(columns=["ID", "Patient ID"]).copy()
            display["Date"] = display["Date"].dt.strftime("%Y-%m-%d")
            st.dataframe(display, hide_index=True)
