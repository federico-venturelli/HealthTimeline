# HealthTimeline — Project Context

## About
Personal health data aggregator built with Python + Streamlit + SQLite.
The user is a 2nd-year CS student rebuilding this project from scratch to learn.
Working approach: **guided, not written for him** — explain, suggest, let him write.

## Tech Stack
- **Python** + **Streamlit** (multi-page app via `pages/` directory)
- **SQLite** via `sqlite3` (no ORM)
- **Plotly** (`plotly.graph_objects`) for charts
- **pandas** for data manipulation
- Run with: `streamlit run app.py`

## File Structure
```
HealthTimeline/
├── app.py                  # Entry point — calls db.init_db(), sets title
├── config.py               # PARAMETER_MAP and (TODO) PARAM_TO_CAT
├── database/
│   ├── schema.sql          # All CREATE TABLE statements
│   ├── db_manager.py       # All DB functions
│   └── health_timeline.db  # SQLite file (auto-created)
└── pages/
    ├── patients.py         # DONE
    └── vital_signs.py      # DONE
```

## Database Schema (schema.sql)
Tables: `patients`, `vital_signs`, `medical_conditions`, `medications`, `clinical_events`, `lab_reports`, `lab_results`.
Only `patients` and `vital_signs` are active so far.

`patients`: id, first_name, last_name, birth_date, gender, email, blood_type
`vital_signs`: id, patient_id, date (TEXT), time (TEXT), category, parameter, value (REAL), unit, notes

Dates stored as strings via `str(measurement_date)` and `str(measurement_time)`.

## db_manager.py — Functions
- `init_db()` — reads schema.sql, runs executescript
- `add_patient(first_name, last_name, birth_date, gender, email, blood_type)`
- `get_all_patients()` — returns list of tuples
- `add_vital_sign(patient_id, date, time, category, parameter, value, unit, notes)`
- `get_vital_signs(patient_id)` — returns list of tuples

## config.py — PARAMETER_MAP
Each parameter has: `unit`, `min_value`, `value`, `step`.
Categories: Cardio (Heart Rate, Pressure Sys, Pressure Dia, SpO2), Physical (Weight, Height), Thermal (Body Temperature).
**TODO**: add `PARAM_TO_CAT = {param: cat for cat, params in PARAMETER_MAP.items() for param in params}` and use it in vital_signs.py to replace the `next(...)` lookup on line 49-50.

## Pages Completed

### patients.py
- Form to add patient (validates first_name, last_name, gender required; blood_type optional)
- Shows patient table with pandas DataFrame + proper column names

### vital_signs.py
- Patient selector (dropdown from DB, shows "First Last")
- **Insert tab**: form with date/time + all parameters grouped by category (inputs dict), saves only val > 0, calls st.rerun() after save
- **History tab**: parameter selectbox + period radio (1 Month/6 Months/1 Year/All), Plotly line chart with fill, data table with formatted dates

## Key Conventions
- All column names and code in **English**
- `st.rerun()` after form submissions that need to refresh data
- Date comparison uses `pd.to_datetime()` + `pd.Timestamp.today()`
- Display dates formatted with `.dt.strftime("%Y-%m-%d")`
- `hide_index=True` on all dataframes
- `st.stop()` to halt page if no patients found

## Pending Small Fixes
- **vital_signs.py line 28**: closing `)` of `st.date_input` is at wrong indentation (4 spaces instead of 8) — cosmetic but worth fixing
- **vital_signs.py lines 49-50**: still uses `next(c for c, params in PARAMETER_MAP.items() if param in params)` — replace with `PARAM_TO_CAT[param]` once `PARAM_TO_CAT` is added to config.py
- **patients.py line 4**: `datetime` is imported but never used — remove it

## Next Pages to Build (in order)
1. `pages/medications.py` — name, dosage, frequency, start/end date, reason, notes. Same pattern: Insert tab + History tab with table.
2. `pages/clinical_events.py` — event_type (Surgery, Hospitalization, Visit, Vaccine), description, date, location, notes
3. `pages/lab_reports.py` — category (Blood, Urine, Spirometry), date, file_path, notes + lab_results sub-table (parameter_name, value, unit, ref_min, ref_max, method)
4. `pages/dashboard.py` — overview: latest vitals per parameter, active medications, recent events

## Design Decisions Made
- One page at a time: build → test visually → improve → move on
- Each page has **History tab first, Insert tab second** — History is the default view, Insert is secondary
- Patient selector in **sidebar** via `select_patient()` from `utils.py` — call at top of every page with `patient_id = select_patient()`
- All data in English
- Dates stored as TEXT strings in SQLite, converted with pd.to_datetime() when needed for filtering/charting
- `st.rerun()` after form submit to refresh data immediately
- `st.stop()` to halt page execution if no patients in DB
