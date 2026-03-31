# Data access layer — all database operations go through here.
# No other module imports sqlite3 directly; they call these functions instead.

import sqlite3
from pathlib import Path

BASE_DIR    = Path(__file__).parent
DB_PATH     = BASE_DIR / "health_timeline.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"


def init_db():
    # executescript() runs multiple SQL statements separated by ";".
    # The "with" context manager commits on success, rolls back on error,
    # and closes the connection automatically.
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA_PATH.read_text())


# ── Patients ──────────────────────────────────────────────────────────────────

def add_patient(first_name, last_name, birth_date, gender, email, blood_type):
    with sqlite3.connect(DB_PATH) as conn:
        # "?" placeholders prevent SQL injection — values are always treated as data,
        # never as executable SQL.
        conn.execute(
            "INSERT INTO patients(first_name, last_name, birth_date, gender, email, blood_type) VALUES (?,?,?,?,?,?)",
            (first_name, last_name, birth_date, gender, email, blood_type),
        )


def get_all_patients():
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT * FROM patients").fetchall()


def get_patient(patient_id):
    with sqlite3.connect(DB_PATH) as conn:
        # (patient_id,) — the trailing comma makes it a tuple, required by sqlite3.
        return conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()


# ── Vital signs ───────────────────────────────────────────────────────────────

def add_vital_sign(patient_id, date, time, category, parameter, value, unit, notes):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO vital_signs(patient_id, date, time, category, parameter, value, unit, notes) VALUES (?,?,?,?,?,?,?,?)",
            (patient_id, date, time, category, parameter, value, unit, notes),
        )


def get_vital_signs(patient_id):
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT * FROM vital_signs WHERE patient_id = ?", (patient_id,)).fetchall()


# ── Medications ───────────────────────────────────────────────────────────────

def add_medication(patient_id, name, dosage, frequency, start_date, end_date, reason, file_path, notes):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO medications(patient_id, name, dosage, frequency, start_date, end_date, reason, file_path, notes) VALUES (?,?,?,?,?,?,?,?,?)",
            (patient_id, name, dosage, frequency, start_date, end_date, reason, file_path, notes),
        )


def get_medications(patient_id):
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT * FROM medications WHERE patient_id = ?", (patient_id,)).fetchall()


def update_medication_end_date(medication_id, end_date):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE medications SET end_date = ? WHERE id = ?", (end_date, medication_id))


# ── Medical conditions ────────────────────────────────────────────────────────

def add_medical_condition(patient_id, name, condition_type, start_date, end_date, file_path, notes):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO medical_conditions(patient_id, name, type, start_date, end_date, file_path, notes) VALUES (?,?,?,?,?,?,?)",
            (patient_id, name, condition_type, start_date, end_date, file_path, notes),
        )


def get_medical_conditions(patient_id):
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT * FROM medical_conditions WHERE patient_id = ?", (patient_id,)).fetchall()


def update_condition_end_date(condition_id, end_date):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE medical_conditions SET end_date = ? WHERE id = ?", (end_date, condition_id))


# ── Clinical events ───────────────────────────────────────────────────────────

def add_clinical_event(patient_id, event_type, description, start_date, end_date, location, file_path, notes):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO clinical_events(patient_id, event_type, description, start_date, end_date, location, file_path, notes) VALUES (?,?,?,?,?,?,?,?)",
            (patient_id, event_type, description, start_date, end_date, location, file_path, notes),
        )


def get_clinical_events(patient_id):
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(
            "SELECT * FROM clinical_events WHERE patient_id = ?", (patient_id,)
        ).fetchall()


def update_event_end_date(event_id, end_date):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE clinical_events SET end_date = ? WHERE id = ?", (end_date, event_id)
        )


# ── Lab reports ───────────────────────────────────────────────────────────────

def get_lab_reports(patient_id):
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(
            "SELECT * FROM lab_reports WHERE patient_id = ? ORDER BY date DESC", (patient_id,)
        ).fetchall()


def add_lab_report(patient_id, report_date, category, file_path, notes):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "INSERT INTO lab_reports(patient_id, date, category, file_path, notes) VALUES (?,?,?,?,?)",
            (patient_id, report_date, category, file_path, notes),
        )
        # lastrowid returns the id of the row just inserted — needed to link lab_results.
        return cursor.lastrowid


def add_lab_result(report_id, parameter_name, value, unit, ref_min, ref_max, method):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO lab_results(report_id, parameter_name, value, unit, ref_min, ref_max, method) VALUES (?,?,?,?,?,?,?)",
            (report_id, parameter_name, value, unit, ref_min, ref_max, method),
        )


def get_lab_history(patient_id, category):
    with sqlite3.connect(DB_PATH) as conn:
        # JOIN to get the report date alongside each result row.
        return conn.execute("""
            SELECT r.date, res.parameter_name, res.value, res.unit, res.ref_min, res.ref_max, res.method
            FROM lab_results res
            JOIN lab_reports r ON res.report_id = r.id
            WHERE r.patient_id = ? AND r.category = ?
            ORDER BY r.date ASC, res.parameter_name ASC
        """, (patient_id, category)).fetchall()
