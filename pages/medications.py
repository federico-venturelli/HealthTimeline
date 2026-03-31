import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import date, timedelta
import database.db_manager as db
from utils import select_patient, save_uploaded_file, show_table_with_downloads, period_date_filter, render_navbar

render_navbar()
st.header(":material/medication: Medications")

patient_id = select_patient()
birth_date = date.fromisoformat(db.get_patient(patient_id)[3])
min_date   = birth_date - timedelta(days=365)

tab_his, tab_ins = st.tabs(["History", "Insert"])

# ── Insert ────────────────────────────────────────────────────────────────────
with tab_ins:
    with st.container(border=True):
        # Checkbox is outside the form so it can hide/show end_date immediately.
        # Widgets inside a form only update on submit.
        still_in_use = st.checkbox("Medication still in use (no end date)", key="still_in_use")

        with st.form("form_medications", clear_on_submit=True):
            name = st.text_input("Medication name")
            col1, col2 = st.columns(2)
            dosage    = col1.text_input("Dosage",    placeholder="e.g. 500mg")
            frequency = col2.text_input("Frequency", placeholder="e.g. 2x daily")
            start_date = col1.date_input("Start date", min_value=min_date, max_value=date.today())
            end_date   = None if still_in_use else col2.date_input("End date", min_value=min_date)
            reason = st.text_input("Reason")
            notes  = st.text_input("Notes", placeholder="Optional")
            uploaded_file = st.file_uploader("Attach document", type=["pdf", "jpg", "jpeg", "png", "docx"])
            submitted = st.form_submit_button("Save")

            if submitted:
                if not name or not dosage or not frequency or not reason:
                    st.error("Please fill in all required fields.")
                elif end_date and end_date < start_date:
                    st.error("End date cannot be before start date.")
                else:
                    file_path = save_uploaded_file(uploaded_file, "medications") if uploaded_file else None
                    db.add_medication(
                        patient_id, name, dosage, frequency,
                        str(start_date), str(end_date) if end_date else None,
                        reason, file_path, notes
                    )
                    st.success("Saved!")
                    st.rerun()

# ── History ───────────────────────────────────────────────────────────────────
with tab_his:
    rows = db.get_medications(patient_id)
    if not rows:
        st.info("No medications yet.")
    else:
        today = pd.Timestamp.today().normalize()

        df_all = pd.DataFrame(rows, columns=["ID", "Patient ID", "Name", "Dosage", "Frequency", "Start Date", "End Date", "Reason", "File Path", "Notes"])
        df_all["Start Date"] = pd.to_datetime(df_all["Start Date"])
        df_all["End Date"] = df_all["End Date"].apply(
            lambda x: pd.NaT if (x is None or str(x) in ("None", "")) else pd.to_datetime(x)
        )
        df_all["Still In Use"] = df_all["End Date"].apply(lambda x: pd.isna(x) or x >= today)
        # For ongoing meds, extend the Gantt bar to today.
        df_all["Chart End"] = df_all.apply(
            lambda row: today if pd.isna(row["End Date"]) else row["End Date"], axis=1
        )

        min_data_actual = df_all["Start Date"].min().date()
        max_data        = date.today()

        start_filter, end_filter = period_date_filter(
            "med_period_radio", "med_date_slider", birth_date, min_data_actual, max_data
        )

        # Include medications that overlap the selected period.
        df_chart = df_all[df_all["Chart End"] >= pd.Timestamp(start_filter)].copy()
        x_start  = pd.Timestamp(start_filter)
        x_end    = pd.Timestamp(end_filter) + pd.Timedelta(days=5)

        if df_chart.empty:
            st.info("No medications in this period.")
        else:
            # Horizontal bar chart used as a Gantt — duration in milliseconds because x-axis is type "date".
            colors = ["#219ebc", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899", "#14B8A6", "#F97316"]
            fig = go.Figure()
            for i, (_, row) in enumerate(df_chart.iterrows()):
                duration_ms = (row["Chart End"] - row["Start Date"]).total_seconds() * 1000
                fig.add_trace(go.Bar(
                    x=[duration_ms],
                    y=[f"{row['Name']} {row['Dosage']}"],
                    base=[row["Start Date"]],
                    orientation="h",
                    marker=dict(color=colors[i % len(colors)], cornerradius=20),
                    showlegend=False,
                    hovertemplate=(
                        f"<b>{row['Name']} {row['Dosage']}</b><br>"
                        f"{row['Frequency']}<br>"
                        f"From: {row['Start Date'].strftime('%Y-%m-%d')}<br>"
                        f"To: {'In use' if pd.isna(row['End Date']) else row['Chart End'].strftime('%Y-%m-%d')}"
                        "<extra></extra>"
                    )
                ))
            fig.add_vline(
                x=today.timestamp() * 1000,
                line_dash="dash", line_color="red",
                annotation_text="Today", annotation_position="top right",
            )
            fig.update_layout(
                xaxis=dict(type="date", range=[x_start, x_end]),
                yaxis=dict(autorange="reversed"),
                plot_bgcolor="white",
                margin=dict(l=20, r=20, t=40, b=20),
                height=max(200, len(df_chart) * 55 + 80),
            )
            st.plotly_chart(fig, width='stretch')

        _DROP = ["ID", "Patient ID", "Still In Use", "Chart End"]
        active = df_all[df_all["Still In Use"]].copy()
        past   = df_all[~df_all["Still In Use"]].copy()

        st.subheader(":material/check_circle: Currently in use")
        if active.empty:
            st.info("No active medications.")
        else:
            show_table_with_downloads(active, ["Start Date", "End Date"], "dl_active", drop_cols=_DROP)

            with st.expander("Set end date for a medication"):
                active_options = {f"{row['Name']} {row['Dosage']}": row["ID"] for _, row in active.iterrows()}
                med_to_end   = st.selectbox("Medication", list(active_options.keys()), key="med_to_end")
                end_date_val = st.date_input("End date", key="med_end_date_val", min_value=min_date)
                if st.button("Save", key="save_end_date"):
                    med_start = active.loc[active["ID"] == active_options[med_to_end], "Start Date"].iloc[0]
                    if end_date_val < med_start.date():
                        st.error("End date cannot be before start date.")
                    else:
                        db.update_medication_end_date(active_options[med_to_end], str(end_date_val))
                        st.success("Saved!")
                        st.rerun()

        st.subheader(":material/history: Past medications")
        if past.empty:
            st.info("No past medications.")
        else:
            show_table_with_downloads(past, ["Start Date", "End Date"], "dl_past", drop_cols=_DROP)
