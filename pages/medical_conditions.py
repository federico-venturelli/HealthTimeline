import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import date, timedelta
import database.db_manager as db
from utils import select_patient, save_uploaded_file, show_table_with_downloads, period_date_filter, render_navbar

render_navbar()
st.header(":material/health_and_safety: Medical conditions")

patient_id = select_patient()
birth_date = date.fromisoformat(db.get_patient(patient_id)[3])
min_date   = birth_date - timedelta(days=365)

tab_his, tab_ins = st.tabs(["History", "Insert"])

# ── Insert ────────────────────────────────────────────────────────────────────
with tab_ins:
    with st.container(border=True):
        still_active = st.checkbox("Condition still ongoing (no end date)", key="still_active")
        with st.form("form_conditions", clear_on_submit=True):
            name           = st.text_input("Condition name")
            condition_type = st.selectbox("Type", ["Chronic", "Acute"])
            col1, col2 = st.columns(2)
            start_date = col1.date_input("Start date", min_value=min_date, max_value=date.today())
            end_date   = None if still_active else col2.date_input("End date", min_value=min_date)
            notes         = st.text_input("Notes", placeholder="Optional")
            uploaded_file = st.file_uploader("Attach document", type=["pdf", "jpg", "jpeg", "png", "docx"])
            submitted = st.form_submit_button("Save")

            if submitted:
                if not name:
                    st.error("Please fill in the condition name.")
                elif end_date and end_date < start_date:
                    st.error("End date cannot be before start date.")
                else:
                    file_path = save_uploaded_file(uploaded_file, "conditions") if uploaded_file else None
                    db.add_medical_condition(
                        patient_id, name, condition_type,
                        str(start_date), str(end_date) if end_date else None,
                        file_path, notes
                    )
                    st.success("Saved!")
                    st.rerun()

# ── History ───────────────────────────────────────────────────────────────────
with tab_his:
    rows = db.get_medical_conditions(patient_id)
    if not rows:
        st.info("No conditions yet.")
    else:
        today = pd.Timestamp.today().normalize()
        df_all = pd.DataFrame(rows, columns=["ID", "Patient ID", "Name", "Type", "Start Date", "End Date", "File Path", "Notes"])
        df_all["Start Date"] = pd.to_datetime(df_all["Start Date"])
        df_all["End Date"]   = df_all["End Date"].apply(
            lambda x: pd.NaT if (x is None or str(x) in ("None", "")) else pd.to_datetime(x)
        )
        df_all["Still Active"] = df_all["End Date"].apply(lambda x: pd.isna(x) or x >= today)
        df_all["Chart End"]    = df_all.apply(
            lambda row: today if pd.isna(row["End Date"]) else row["End Date"], axis=1
        )

        min_data_actual = df_all["Start Date"].min().date()
        max_data        = date.today()

        start_filter, end_filter = period_date_filter(
            "cond_period_radio", "cond_date_slider", birth_date, min_data_actual, max_data
        )

        df_chart = df_all[df_all["Chart End"] >= pd.Timestamp(start_filter)].copy()
        x_start  = pd.Timestamp(start_filter)
        x_end    = pd.Timestamp(end_filter) + pd.Timedelta(days=5)

        if df_chart.empty:
            st.info("No conditions in this period.")
        else:
            # Each condition gets a unique color: warm tones for Chronic, cool for Acute.
            CHRONIC_COLORS = ["#EF4444", "#DC2626", "#B91C1C", "#F97316", "#EA580C"]
            ACUTE_COLORS   = ["#219ebc", "#0891B2", "#0369A1", "#059669", "#7C3AED"]
            chronic_idx = 0
            acute_idx   = 0
            fig = go.Figure()
            for i, (_, row) in enumerate(df_chart.iterrows()):
                if row["Type"] == "Chronic":
                    color = CHRONIC_COLORS[chronic_idx % len(CHRONIC_COLORS)]
                    chronic_idx += 1
                else:
                    color = ACUTE_COLORS[acute_idx % len(ACUTE_COLORS)]
                    acute_idx += 1
                duration_ms = (row["Chart End"] - row["Start Date"]).total_seconds() * 1000
                fig.add_trace(go.Bar(
                    x=[duration_ms],
                    y=[f"{row['Name']} ({row['Type']})"],
                    base=[row["Start Date"]],
                    orientation="h",
                    marker=dict(color=color, cornerradius=20),
                    showlegend=False,
                    hovertemplate=(
                        f"<b>{row['Name']}</b> ({row['Type']})<br>"
                        f"From: {row['Start Date'].strftime('%Y-%m-%d')}<br>"
                        f"To: {'Ongoing' if pd.isna(row['End Date']) else row['Chart End'].strftime('%Y-%m-%d')}"
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

        _DROP = ["ID", "Patient ID", "Still Active", "Chart End"]
        active = df_all[df_all["Still Active"]].copy()
        past   = df_all[~df_all["Still Active"]].copy()

        st.subheader(":material/healing: Active conditions")
        if active.empty:
            st.info("No active conditions.")
        else:
            show_table_with_downloads(active, ["Start Date", "End Date"], "dl_active", drop_cols=_DROP)

            with st.expander("Set end date for a condition"):
                active_options = {f"{row['Name']} ({row['Type']})": row["ID"] for _, row in active.iterrows()}
                cond_to_end  = st.selectbox("Condition", list(active_options.keys()), key="cond_to_end")
                end_date_val = st.date_input("End date", key="cond_end_date_val", min_value=min_date)
                if st.button("Save", key="save_cond_end_date"):
                    cond_start = active.loc[active["ID"] == active_options[cond_to_end], "Start Date"].iloc[0]
                    if end_date_val < cond_start.date():
                        st.error("End date cannot be before start date.")
                    else:
                        db.update_condition_end_date(active_options[cond_to_end], str(end_date_val))
                        st.success("Saved!")
                        st.rerun()

        st.subheader(":material/history: Past conditions")
        if past.empty:
            st.info("No past conditions.")
        else:
            show_table_with_downloads(past, ["Start Date", "End Date"], "dl_past", drop_cols=_DROP)
