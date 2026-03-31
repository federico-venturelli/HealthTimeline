# All Claude API calls go through this module.
# Separating AI logic from UI keeps pages clean and lets lab_reports and spirometry share the same functions.

import anthropic
import base64
import json
import re
import streamlit as st


def _client():
    # Priority: sidebar input > st.secrets (for cloud deployment).
    api_key = st.session_state.get("api_key") or st.secrets.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("No API key set. Please enter your Anthropic API key in the sidebar.")
    return anthropic.Anthropic(api_key=api_key)


def _parse_json(text: str):
    # Claude sometimes wraps JSON in markdown code fences — strip them before parsing.
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


def _make_content_block(file_bytes: bytes, media_type: str) -> dict:
    # Claude accepts files as base64-encoded strings. PDFs and images use slightly different structures.
    b64 = base64.standard_b64encode(file_bytes).decode("utf-8")
    if media_type == "application/pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}}


def _normalize_decimals(results: list) -> list:
    # Some European lab reports use commas as decimal separators (e.g. "14,2").
    # This converts them to periods as a safety net even though the prompt already asks for periods.
    for item in results:
        if isinstance(item.get("value"), str):
            item["value"] = item["value"].replace(",", ".")
        for key in ("ref_min", "ref_max"):
            v = item.get(key)
            if isinstance(v, str):
                try:
                    item[key] = float(v.replace(",", "."))
                except ValueError:
                    item[key] = None
    return results


def extract_lab_data(file_bytes: bytes, media_type: str) -> dict:
    """Send a PDF or image to Claude and return extracted lab results.

    Returns: {"date": "YYYY-MM-DD" or None, "results": list of parameter dicts}
    """
    content_block = _make_content_block(file_bytes, media_type)

    message = _client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        messages=[{
            "role": "user",
            "content": [
                content_block,
                {
                    "type": "text",
                    "text": (
                        "Extract all lab results from this document and the report date. "
                        "Return a JSON object with two keys: "
                        "\"date\" (the report/sample date in \"YYYY-MM-DD\" format, or null if not found), "
                        "\"results\" (array where each item has: "
                        "\"parameter\" (exact name as it appears in the document), "
                        "\"value\" (string, always use period as decimal separator, never comma), "
                        "\"unit\" (string), "
                        "\"ref_min\" (number or null, period as decimal separator), "
                        "\"ref_max\" (number or null, period as decimal separator), "
                        "\"method\" (string or null), "
                        "\"category\" (\"Blood\" or \"Urine\" based on the test type)). "
                        "Return only valid JSON, no other text."
                    )
                }
            ]
        }]
    )

    raw = _parse_json(message.content[0].text)

    # Handle cases where Claude returns a bare list instead of the expected dict.
    if isinstance(raw, list):
        date_str = None
        results = raw
    else:
        date_str = raw.get("date")
        results = raw.get("results", [])

    return {"date": date_str, "results": _normalize_decimals(results)}


def extract_spirometry_data(file_bytes: bytes, media_type: str) -> dict:
    """Send a spirometry report to Claude and return extracted results.

    The prompt is in Italian because Italian spirometry reports use specific terminology
    (Orto/Clino/Tosse) that Claude handles better with instructions in the same language.

    Returns: {"date": "YYYY-MM-DD" or None, "results": list of parameter dicts}
    """
    content_block = _make_content_block(file_bytes, media_type)

    message = _client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                content_block,
                {
                    "type": "text",
                    "text": (
                        "Sei un esperto pneumologo. Analizza questo referto di Spirometria.\n\n"
                        "OBIETTIVO: Estrarre SOLO i valori misurati reali (ORTO/CLINO/TOSSE). "
                        "IGNORA colonne teoriche (Teor, Pred, %) e percentuali.\n\n"
                        "ISTRUZIONI:\n"
                        "1. Crea parametri nel formato \"Nome (Condizione)\". "
                        "Esempio: \"FVC (Orto)\", \"FVC (Clino)\", \"PEF (Tosse)\".\n"
                        "2. VALORI: Estrai il numero esatto misurato. Usa il punto come separatore decimale.\n"
                        "3. Estrai la data del referto come \"date\" in formato YYYY-MM-DD (o null se non trovata).\n\n"
                        "Restituisci un JSON con: "
                        "\"date\" (stringa YYYY-MM-DD o null) e "
                        "\"results\" (array di oggetti con: "
                        "\"parameter\" (nome nel formato \"Nome (Condizione)\"), "
                        "\"value\" (stringa, punto come decimale), "
                        "\"unit\" (stringa), "
                        "\"method\" (sempre \"Spirometria\")). "
                        "Restituisci solo JSON valido, nessun altro testo."
                    )
                }
            ]
        }]
    )
    raw = _parse_json(message.content[0].text)

    if isinstance(raw, list):
        date_str = None
        results = raw
    else:
        # Handle slight variations in the date field name Claude might return.
        date_str = raw.get("date") or raw.get("report_date")
        results = raw.get("results", [])

    return {"date": date_str, "results": _normalize_decimals(results)}


def normalize_parameter_names(parameters: list[dict]) -> dict[str, dict]:
    """Group clinically equivalent parameters under a single canonical name.

    The same test (e.g. hemoglobin) can appear as "Hb", "HGB", or "Emoglobina" across
    different lab reports. This function asks Claude to unify them.

    Args:
        parameters: list of {"name": ..., "unit": ..., "date": ...}

    Returns:
        dict keyed by "ORIGINAL_NAME||ORIGINAL_UNIT" with target_name, target_unit, and
        factor (unit conversion multiplier, 1.0 if unchanged).
    """
    if not parameters:
        return {}

    prompt = f"""
Sei un esperto di laboratorio biomedico.
Ho la storia dei parametri di laboratorio di un paziente nel tempo.
Ogni voce ha: name (nome), unit (unità), date (data dell'esame, formato YYYY-MM-DD).

COMPITO:
1. RAGGRUPPA i parametri che misurano la stessa quantità clinica
   (es. "Hb", "HGB", "Emoglobina" sono tutti la stessa cosa).
2. Per ogni gruppo, usa come 'target_name' e 'target_unit' quelli con la DATA PIU' RECENTE nel gruppo.
   (Il nome più recente è quello del laboratorio più aggiornato, quindi il più corretto.)
3. Calcola il 'factor' per convertire il valore originale al target (se le unità differiscono).
   Se le unità sono le stesse, factor = 1.0.

REGOLA IMPORTANTE: se i parametri sono clinicamente DIVERSI
(es. "Basofili %" misura la percentuale, "Basofili" misura il valore assoluto),
tienili in gruppi separati con target_name diversi.

INPUT (lista di tutti i parametri storici del paziente):
{json.dumps(parameters)}

OUTPUT JSON — chiave = "NOME_ORIGINALE||UNITA_ORIGINALE":
{{
    "Hb||g/dL":         {{"target_name": "Hemoglobin", "target_unit": "g/dL", "factor": 1.0}},
    "HGB||g/dL":        {{"target_name": "Hemoglobin", "target_unit": "g/dL", "factor": 1.0}},
    "Hemoglobin||g/dL": {{"target_name": "Hemoglobin", "target_unit": "g/dL", "factor": 1.0}}
}}

Restituisci solo JSON valido, nessun altro testo.
"""
    try:
        message = _client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=20000,
            messages=[{"role": "user", "content": prompt}]
        )
        return _parse_json(message.content[0].text)
    except Exception as e:
        # Show a warning instead of crashing — normalization is optional.
        st.warning(f"Normalization failed: {e}")
        return {}
