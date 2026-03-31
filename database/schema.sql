-- Database schema for HealthTimeline.
-- Executed by db_manager.init_db() on startup via executescript().
-- All tables use IF NOT EXISTS so this is safe to call repeatedly.
--
-- Every table has patient_id -> patients(id) ON DELETE CASCADE:
-- deleting a patient automatically removes all their data.


-- Core patient demographics.
CREATE TABLE IF NOT EXISTS patients (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name  TEXT NOT NULL,
    birth_date DATE NOT NULL,
    gender     TEXT,
    email      TEXT,
    blood_type TEXT
);

-- Ongoing or past medical conditions (e.g. diabetes, hypertension).
-- end_date NULL means the condition is still active.
CREATE TABLE IF NOT EXISTS medical_conditions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER,
    name       TEXT NOT NULL,
    type       TEXT,             -- 'Chronic' or 'Acute'
    start_date DATE,
    end_date   DATE,             -- NULL = still ongoing
    file_path  TEXT,
    notes      TEXT,
    FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE
);

-- Medications prescribed to the patient.
-- end_date NULL means still in use.
CREATE TABLE IF NOT EXISTS medications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER,
    name       TEXT NOT NULL,
    dosage     TEXT,
    frequency  TEXT,
    start_date DATE,
    end_date   DATE,             -- NULL = still in use
    reason     TEXT,
    file_path  TEXT,
    notes      TEXT,
    FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE
);

-- Clinical events: visits, surgeries, hospitalizations, vaccines.
-- end_date NULL for single-day events.
CREATE TABLE IF NOT EXISTS clinical_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id  INTEGER,
    event_type  TEXT,            -- 'Surgery', 'Hospitalization', 'Visit', 'Vaccine'
    description TEXT,
    start_date  DATE,
    end_date    DATE,
    location    TEXT,
    file_path   TEXT,
    notes       TEXT,
    FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE
);

-- Vital sign measurements (heart rate, blood pressure, weight, etc.).
-- One row per measurement per parameter — multiple parameters recorded at the same time
-- are stored as separate rows with the same date/time.
CREATE TABLE IF NOT EXISTS vital_signs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER,
    date       DATE,
    time       TEXT,
    category   TEXT,             -- 'Cardio', 'Physical', 'Thermal' (from config.py)
    parameter  TEXT,             -- e.g. 'Heart Rate'
    value      REAL,
    unit       TEXT,             -- e.g. 'bpm'
    notes      TEXT,
    FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE
);

-- Lab report header: date, category, optional PDF attachment.
-- One-to-many with lab_results: one report contains many individual results.
CREATE TABLE IF NOT EXISTS lab_reports (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER,
    date       DATE,
    category   TEXT,             -- 'Blood', 'Urine', 'Spirometria'
    file_path  TEXT,
    notes      TEXT,
    FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE
);

-- Individual results within a lab report (e.g. "Hemoglobin 14.2 g/dL").
-- value stored as TEXT to preserve original formatting from the document.
CREATE TABLE IF NOT EXISTS lab_results (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id      INTEGER,
    parameter_name TEXT,
    value          TEXT,
    unit           TEXT,
    ref_min        REAL,
    ref_max        REAL,
    method         TEXT,
    FOREIGN KEY(report_id) REFERENCES lab_reports(id) ON DELETE CASCADE
);
