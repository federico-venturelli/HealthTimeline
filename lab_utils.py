# Shared utilities for lab_reports.py, spirometry.py, and analysis.py.
# Handles parameter name normalization: the same test can appear as "Hb", "HGB",
# or "Emoglobina" across reports — these functions unify them for display.

import json
from pathlib import Path
import pandas as pd
import streamlit as st
import ai_manager
import database.db_manager as db

# Persistent JSON cache for normalization rules.
# Survives app restarts unlike st.session_state.
NORM_CACHE_FILE = Path(__file__).parent / "lab_normalization_cache.json"

# File extension to MIME type mapping for the Claude API.
MEDIA_TYPES = {
    "pdf":  "application/pdf",
    "jpg":  "image/jpeg",
    "jpeg": "image/jpeg",
    "png":  "image/png",
}


def _load_norm_cache() -> dict:
    """Load normalization rules from the JSON cache file."""
    if NORM_CACHE_FILE.exists():
        try:
            return json.loads(NORM_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_norm_cache(mapping: dict):
    """Write normalization rules back to the JSON cache file."""
    NORM_CACHE_FILE.write_text(
        json.dumps(mapping, indent=4, ensure_ascii=False), encoding="utf-8"
    )


def _apply_normalization(valid: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """Apply normalization rules to a DataFrame of lab results.

    Resolves alias chains (A->B->C becomes A->C) with up to 10 passes.
    The µ character has two different Unicode code points (U+00B5 and U+03BC) —
    we normalize before building the lookup key to avoid missed matches.
    """
    valid = valid.copy()
    for _ in range(10):
        changed = False
        for idx, row in valid.iterrows():
            unit = str(row["Unit"]) if pd.notna(row.get("Unit")) and str(row.get("Unit", "")).strip() else ""
            unit_norm = unit.replace("\u00b5", "\u03bc")
            key = f"{row['Parameter']}||{unit_norm}"
            if key not in mapping:
                key = f"{row['Parameter']}||{unit}"
            m = mapping.get(key)
            if not m:
                continue

            target_unit = m["target_unit"] if m["target_unit"] is not None else ""
            if row["Parameter"] == m["target_name"] and unit == target_unit:
                continue  # already normalized

            changed = True
            valid.at[idx, "Parameter"] = m["target_name"]
            valid.at[idx, "Unit"]      = m["target_unit"]

            factor = float(m.get("factor", 1.0))
            if factor != 1.0:
                try:
                    val = float(str(row["Value"]).replace(",", "."))
                    valid.at[idx, "Value"] = f"{val * factor:.8g}"
                except (ValueError, TypeError):
                    pass
                for ref_col in ("Ref Min", "Ref Max"):
                    if ref_col in valid.columns and pd.notna(row.get(ref_col)):
                        try:
                            valid.at[idx, ref_col] = round(float(row[ref_col]) * factor, 8)
                        except (ValueError, TypeError):
                            pass

        if not changed:
            break  # all alias chains resolved

    return valid


def save_lab_results(report_id: int, rows_df: pd.DataFrame):
    """Persist all result rows from a DataFrame to the database."""
    for _, row in rows_df.iterrows():
        db.add_lab_result(
            report_id,
            row["Parameter"],
            str(row["Value"]),
            str(row["Unit"]) if pd.notna(row.get("Unit")) and str(row.get("Unit", "")).strip() else "",
            float(row["Ref Min"]) if pd.notna(row.get("Ref Min")) else None,
            float(row["Ref Max"]) if pd.notna(row.get("Ref Max")) else None,
            str(row["Method"]) if pd.notna(row.get("Method")) and str(row.get("Method", "")).strip() else None,
        )


def render_norm_expander(most_recent_orig: pd.DataFrame, mapping: dict, button_key: str):
    """Render the normalization mapping expander with a Re-normalize button.

    most_recent_orig: DataFrame with original (pre-normalization) parameter names.
    button_key:       unique key to avoid widget conflicts across pages.
    """
    with st.expander("🔬 Normalization mapping"):
        col_refresh, _ = st.columns([1, 4])
        if col_refresh.button("↺ Re-normalize all", key=button_key):
            params_for_ai = [
                {
                    "name": row["Parameter"],
                    "unit": str(row["Unit"]).strip() if pd.notna(row["Unit"]) and str(row["Unit"]).strip() else "",
                    "date": row["Date"],
                }
                for _, row in most_recent_orig.iterrows()
            ]
            try:
                with st.spinner("Calling normalization AI…"):
                    new_rules = ai_manager.normalize_parameter_names(params_for_ai)
                    full = _load_norm_cache()
                    full.update(new_rules)
                    _save_norm_cache(full)
                st.rerun()
            except Exception as e:
                st.error(f"Normalization failed: {e}")

        # Build preview: only rules relevant to the current patient's parameters.
        orig_keys = {
            f"{row['Parameter']}||{(str(row['Unit']).strip() if pd.notna(row['Unit']) and str(row['Unit']).strip() else '')}"
            for _, row in most_recent_orig.iterrows()
        }
        preview = [
            {
                "Original name":    k.split("||")[0],
                "Original unit":    k.split("||")[1],
                "→ Normalized name": v["target_name"],
                "→ Unit":           v["target_unit"],
                "Factor":           v.get("factor", 1.0),
            }
            for k, v in mapping.items()
            if k in orig_keys
        ]
        if preview:
            st.dataframe(pd.DataFrame(preview), hide_index=True, width='stretch')
        else:
            st.caption("No mapping yet — save data first or click Re-normalize.")


def _normalize_new_params(rows_df: pd.DataFrame, report_date_str: str):
    """Normalize only parameters not already in the JSON cache.

    Incremental strategy: only sends unknown parameters to the AI,
    keeping calls minimal.
    """
    current = _load_norm_cache()
    unknowns = []

    for _, row in rows_df[["Parameter", "Unit"]].drop_duplicates().iterrows():
        unit = str(row["Unit"]).strip() if pd.notna(row["Unit"]) and str(row["Unit"]).strip() else ""
        unit_norm = unit.replace("\u00b5", "\u03bc")
        key = f"{row['Parameter']}||{unit_norm}"
        if key not in current:
            key = f"{row['Parameter']}||{unit}"
        if key not in current:
            unknowns.append({"name": row["Parameter"], "unit": unit, "date": report_date_str})

    if unknowns:
        try:
            new_rules = ai_manager.normalize_parameter_names(unknowns)
            current.update(new_rules)
            _save_norm_cache(current)
        except Exception:
            pass  # normalization is optional — the app keeps working without it
