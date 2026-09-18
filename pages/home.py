import streamlit as st
import pandas as pd
from datetime import date
import database.db_manager as db
from utils import render_navbar

render_navbar()

# Collapsed by default so it doesn't get in the way of the dashboard view.
with st.expander(":material/person_add: Add new patient"):
    with st.form("add_patient", clear_on_submit=True):
        c1, c2 = st.columns(2)
        first_name = c1.text_input("First Name")
        last_name  = c2.text_input("Last Name")
        c3, c4, c5, c6 = st.columns(4)
        birth_date = c3.date_input("Birth Date", min_value=date(date.today().year - 100, 1, 1), max_value=date.today())
        gender     = c4.selectbox("Gender", ["", "M", "F", "Other"])
        email      = c5.text_input("Email")
        blood_type = c6.selectbox("Blood type", ["", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"])

        if st.form_submit_button("Register patient"):
            if not first_name or not last_name or gender == "":
                st.error("First name, last name and gender are required.")
            else:
                db.add_patient(first_name, last_name, birth_date, gender, email, blood_type)
                st.success("Patient added!")
                st.rerun()

# ── Patient selector ──────────────────────────────────────────────────────────
patients = db.get_all_patients()
if not patients:
    st.info("No patients yet. Add one above.")
    st.stop()

# Map "First Last" -> id for the selectbox.
options = {f"{p[1]} {p[2]}": p[0] for p in patients}
names   = list(options.keys())

# Restore the previously selected patient if session state already has one.
default_idx = 0
if "patient_id" in st.session_state:
    for i, pid in enumerate(options.values()):
        if pid == st.session_state["patient_id"]:
            default_idx = i
            break

col_sel, _ = st.columns([2, 3])
selected   = col_sel.selectbox("Patient", names, index=default_idx)
patient_id = options[selected]
st.session_state["patient_id"] = patient_id  # persists across all pages

# ── Load patient data ─────────────────────────────────────────────────────────
patient    = db.get_patient(patient_id)
first_name, last_name = patient[1], patient[2]
birth_date  = date.fromisoformat(patient[3])
gender      = patient[4] or "—"
blood_type  = patient[6] or "—"
age         = (date.today() - birth_date).days // 365
today       = date.today()

meds        = db.get_medications(patient_id)        or []
conds       = db.get_medical_conditions(patient_id) or []
events      = db.get_clinical_events(patient_id)    or []
vitals      = db.get_vital_signs(patient_id)        or []
lab_reports = db.get_lab_reports(patient_id)        or []

# Active = no end_date, or end_date >= today.
# lab_reports is already sorted DESC by date from the DB query.
active_meds  = [m for m in meds  if not m[6] or date.fromisoformat(m[6]) >= today]
active_conds = [c for c in conds if not c[5] or date.fromisoformat(c[5]) >= today]
last_lab     = lab_reports[0][2] if lab_reports else "—"
last_vital   = max((v[2] for v in vitals), default=None) or "—"

st.divider()
st.header(f":material/person: {first_name} {last_name}")
st.caption(f"{age} years old · {gender} · Blood type {blood_type}")
st.divider()

# ── Overview ──────────────────────────────────────────────────────────────────
with st.container(border=True):
    st.markdown("##### Overview")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Medications", len(active_meds))
    m2.metric("Conditions",  len(active_conds))
    m3.metric("Last lab",    last_lab)
    m4.metric("Last vital",  last_vital)

# ── Recent activity feed ──────────────────────────────────────────────────────
st.markdown("##### Recent activity")

TYPE_ICONS = {
    "Vitals":          ":material/monitor_heart:",
    "Lab report":      ":material/science:",
    "Medication":      ":material/medication:",
    "Condition":       ":material/health_and_safety:",
    "Surgery":         ":material/event_note:",
    "Hospitalization": ":material/event_note:",
    "Visit":           ":material/event_note:",
    "Vaccine":         ":material/event_note:",
}

feed = []

# Group vitals by day — one feed item per day instead of one per measurement.
if vitals:
    df_v = pd.DataFrame(vitals, columns=["id", "patient_id", "date", "time", "category", "parameter", "value", "unit", "notes"])
    for d_str, grp in df_v.groupby("date"):
        params = grp["parameter"].tolist()
        label = ", ".join(params[:3]) + (" …" if len(params) > 3 else "")
        feed.append({"date": d_str, "type": "Vitals", "label": label})

for e in events:
    etype = e[2] or "Event"
    desc  = (e[3] or "")[:60]
    feed.append({"date": e[4], "type": etype, "label": desc or etype})

for r in lab_reports:
    feed.append({"date": r[2], "type": "Lab report", "label": r[3]})

for m in meds:
    if m[5]:
        feed.append({"date": m[5], "type": "Medication", "label": m[2]})

for c in conds:
    if c[4]:
        feed.append({"date": c[4], "type": "Condition", "label": c[2]})

feed.sort(key=lambda x: x["date"] or "", reverse=True)

if not feed:
    st.caption("No activity recorded yet.")
else:
    for item in feed[:8]:
        with st.container(border=True):
            ca, cb = st.columns([3, 1])
            icon = TYPE_ICONS.get(item["type"], ":material/event:")
            ca.markdown(f"{icon} **{item['type']}** — {item['label']}")
            cb.caption(item["date"])
