# HealthTimeline

A personal health data aggregator built with Python and Streamlit. Tracks vital signs, lab results, medications, medical conditions, and clinical events for multiple patients in a local SQLite database.

---

## Features

- **Vital signs** — record and chart heart rate, blood pressure, SpO2, weight, temperature over time
- **Lab reports** — manual entry or AI-powered extraction from PDF/image scans; pivot table with OOB highlighting and trend arrows
- **Spirometry** — dedicated page for pulmonary function test results
- **Medications** — Gantt timeline of active and past medications
- **Medical conditions** — chronic and acute conditions with timeline visualization
- **Clinical events** — surgeries, hospitalizations, visits, vaccines on a timeline
- **Analysis** — unified multi-panel chart combining all data sources with a configurable date range
- **AI normalization** — Claude API groups equivalent lab parameters across reports (e.g. "Hb", "HGB", "Hemoglobin") with a persistent JSON cache

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Streamlit (multi-page) |
| Charts | Plotly |
| Data | pandas |
| Database | SQLite via sqlite3 |
| AI | Anthropic Claude API |

## Project Structure

```
HealthTimeline/
├── app.py                  # Entry point and router
├── config.py               # Vital sign parameter definitions
├── utils.py                # Shared UI components (navbar, patient selector, date filter)
├── ai_manager.py           # All Claude API calls (extraction + normalization)
├── lab_utils.py            # Lab-specific utilities (normalization cache, pivot table)
├── database/
│   ├── schema.sql          # All CREATE TABLE statements
│   └── db_manager.py       # Data access layer
├── pages/
│   ├── home.py             # Patient dashboard + patient management
│   ├── vital_signs.py
│   ├── medications.py
│   ├── medical_conditions.py
│   ├── clinical_events.py
│   ├── lab_reports.py
│   ├── spirometry.py
│   └── analysis.py
└── assets/
    └── logo.svg
```

## Setup

**1. Clone the repo**
```bash
git clone https://github.com/federico-venturelli/HealthTimeline.git
cd HealthTimeline
```

**2. Create a virtual environment and install dependencies**
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**3. Configure the API key (optional — only needed for AI features)**

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and add your Anthropic API key:
```toml
ANTHROPIC_API_KEY = "sk-ant-..."
```
Alternatively, paste the key directly in the sidebar when the app is running.

**4. Run**
```bash
streamlit run app.py
```

The database is created automatically on first run.

## Notes

- The database and uploaded files are excluded from the repository (`.gitignore`) — they are created locally on first use
- AI features (lab extraction and parameter normalization) require an [Anthropic API key](https://console.anthropic.com/)
- The normalization cache (`lab_normalization_cache.json`) is also excluded — it is rebuilt automatically when new lab data is saved
