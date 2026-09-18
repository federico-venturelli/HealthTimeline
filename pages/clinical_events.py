import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import date, timedelta
import database.db_manager as db
from utils import select_patient, save_uploaded_file, show_table_with_downloads, period_date_filter, render_navbar

render_navbar()
st.header(":material/event_note: Clinical events")

patient_id = select_patient()
birth_date = date.fromisoformat(db.get_patient(patient_id)[3])
min_date   = birth_date - timedelta(days=365)

tab_his, tab_ins = st.tabs(["History", "Insert"])

# ── Insert ────────────────────────────────────────────────────────────────────
with tab_ins:
    with st.container(border=True):
        still_ongoing = st.checkbox("Event still ongoing (no end date)", key="still_ongoing")
        with st.form("form_events", clear_on_submit=True):
            event_type  = st.text_input("Event type")
            description = st.text_input("Description")
            col1, col2 = st.columns(2)
            start_date = col1.date_input("Start date", min_value=min_date, max_value=date.today())
            end_date   = None if still_ongoing else col2.date_input("End date", min_value=min_date, max_value=date.today())
            location      = st.text_input("Location", placeholder="Optional")
            notes         = st.text_input("Notes",    placeholder="Optional")
            uploaded_file = st.file_uploader("Attach document", type=["pdf", "jpg", "jpeg", "png", "docx"])
            submitted = st.form_submit_button("Save")

            if submitted:
                if not description or not event_type:
                    st.error("Please fill in event type and description.")
                elif end_date and end_date < start_date:
                    st.error("End date cannot be before start date.")
                else:
                    file_path = save_uploaded_file(uploaded_file, "events") if uploaded_file else None
                    db.add_clinical_event(
                        patient_id, event_type, description,
                        str(start_date), str(end_date) if end_date else None,
                        location, file_path, notes
                    )
                    st.success("Saved!")
                    st.rerun()

# ── History ───────────────────────────────────────────────────────────────────
with tab_his:
    EVENT_COLORS = [
        "#219ebc", "#10B981", "#F59E0B", "#EF4444",
        "#8B5CF6", "#EC4899", "#14B8A6", "#F97316"
    ]

    rows = db.get_clinical_events(patient_id)
    if not rows:
        st.info("No events yet.")
    else:
        today = pd.Timestamp.today().normalize()
        df_all = pd.DataFrame(rows, columns=["ID", "Patient ID", "Event Type", "Description", "Start Date", "End Date", "Location", "File Path", "Notes"])
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
            "evt_period_radio", "evt_date_slider", birth_date, min_data_actual, max_data
        )

        df_chart = df_all[df_all["Chart End"] >= pd.Timestamp(start_filter)].copy()
        x_start  = pd.Timestamp(start_filter)
        x_end    = pd.Timestamp(end_filter) + pd.Timedelta(days=5)

        if df_chart.empty:
            st.info("No events in this period.")
        else:
            fig = go.Figure()
            for i, (_, row) in enumerate(df_chart.iterrows()):
                # Single-day events (start == end) get +1 day so they're visible on the chart.
                chart_end   = row["Chart End"] if row["Chart End"] > row["Start Date"] else row["Chart End"] + pd.Timedelta(days=1)
                duration_ms = (chart_end - row["Start Date"]).total_seconds() * 1000
                fig.add_trace(go.Bar(
                    x=[duration_ms],
                    y=[f"{row['Event Type']} – {row['Description']}"],
                    base=[row["Start Date"]],
                    orientation="h",
                    marker=dict(color=EVENT_COLORS[i % len(EVENT_COLORS)], cornerradius=20),
                    showlegend=False,
                    hovertemplate=(
                        f"<b>{row['Event Type']}</b><br>"
                        f"{row['Description']}<br>"
                        f"From: {row['Start Date'].strftime('%Y-%m-%d')}<br>"
                        f"To: {'Ongoing' if pd.isna(row['End Date']) else row['End Date'].strftime('%Y-%m-%d')}<br>"
                        f"Location: {row['Location'] or '—'}"
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

        st.subheader(":material/pending: Ongoing events")
        if active.empty:
            st.info("No ongoing events.")
        else:
            show_table_with_downloads(active, ["Start Date", "End Date"], "dl_active", drop_cols=_DROP)

            with st.expander("Set end date for an event"):
                active_options = {f"{row['Event Type']} – {row['Description']}": row["ID"] for _, row in active.iterrows()}
                event_to_end = st.selectbox("Event", list(active_options.keys()), key="event_to_end")
                end_date_val = st.date_input("End date", key="event_end_date_val", min_value=min_date)
                if st.button("Save", key="save_event_end_date"):
                    event_start = active.loc[active["ID"] == active_options[event_to_end], "Start Date"].iloc[0]
                    if end_date_val < event_start.date():
                        st.error("End date cannot be before start date.")
                    else:
                        db.update_event_end_date(active_options[event_to_end], str(end_date_val))
                        st.success("Saved!")
                        st.rerun()

        st.subheader(":material/history: Past events")
        if past.empty:
            st.info("No past events.")
        else:
            show_table_with_downloads(past, ["Start Date", "End Date"], "dl_past", drop_cols=_DROP)
