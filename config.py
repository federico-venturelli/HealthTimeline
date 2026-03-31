# Vital sign parameters used throughout the app.
# Edit here to add or remove parameters — vital_signs.py builds its form dynamically from this.

# Nested dict: category -> parameter -> widget options.
# unit:      displayed next to the input
# min_value: lower bound for the number input
# value:     default (0 means "not entered")
# step:      increment per click
PARAMETER_MAP = {
    "Cardio": {
        "Heart Rate":   {"unit": "bpm",  "min_value": 0,   "value": 0,   "step": 1},
        "Pressure Sys": {"unit": "mmHg", "min_value": 0,   "value": 0,   "step": 1},
        "Pressure Dia": {"unit": "mmHg", "min_value": 0,   "value": 0,   "step": 1},
        "SpO2":         {"unit": "%",    "min_value": 0,   "value": 0,   "step": 1},
    },
    "Physical": {
        "Weight": {"unit": "kg", "min_value": 0.0, "value": 0.0, "step": 1.0},
        "Height": {"unit": "cm", "min_value": 0,   "value": 0,   "step": 1},
    },
    "Thermal": {
        "Body Temperature": {"unit": "°C", "min_value": 0.0, "value": 0.0, "step": 1.0},
    },
}

# Reverse lookup: parameter name -> category.
# Built automatically from PARAMETER_MAP so we never have to maintain it separately.
# e.g. PARAM_TO_CAT["Heart Rate"] == "Cardio"
PARAM_TO_CAT = {param: cat for cat, params in PARAMETER_MAP.items() for param in params}
