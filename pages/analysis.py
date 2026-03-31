import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date
import database.db_manager as db
from utils import select_patient, period_date_filter, render_navbar
from lab_utils import _load_norm_cache, _apply_normalization

# 20-color cyclic palette for parameter traces.
TRACE_COLORS = ["#219ebc", "#DC2626", "#059669", "#D97706", "#7C3AED",
    "#DB2777", "#0891B2", "#EA580C", "#4F46E5", "#65A30D",
    "#0284C7", "#E11D48", "#6D28D9", "#C2410C", "#047857",
    "#B45309", "#1D4ED8", "#9333EA", "#0369A1", "#166534",
]

EVENT_COLORS = {
    "Surgery":         "#DC2626",
    "Hospitalization": "#F97316",
    "Visit":           "#2563EB",
    "Vaccine":         "#059669",
}

SCORE_COLORS = {"Blood": "#EF4444", "Urine": "#F59E0B"}
COND_COLORS  = {"Chronic": "#EF4444", "Acute": "#F97316"}


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convert a hex color to rgba() string for Plotly fill colors."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ── Page ──────────────────────────────────────────────────────────────────────
render_navbar()
st.header(":material/analytics: Analysis")

patient_id = select_patient()

# Reload all data on every visit — no caching so changes from other pages are always reflected.
vitals_raw = db.get_vital_signs(patient_id)
labs_raw   = {cat: db.get_lab_history(patient_id, cat)
              for cat in ("Blood", "Urine", "Spirometria")}
meds       = db.get_medications(patient_id)        or []
conds      = db.get_medical_conditions(patient_id) or []
events     = db.get_clinical_events(patient_id)    or []

# ── Unify all measurements into a single list ─────────────────────────────────
records = []

for row in vitals_raw:
    try:
        val = float(row[6])
        d   = pd.to_datetime(str(row[2])).date()
        records.append({
            "source":    "Vitals",
            "parameter": row[5],
            "unit":      row[7] or "",
            "date":      d,
            "value":     val,
            "ref_min":   None,
            "ref_max":   None,
        })
    except (ValueError, TypeError):
        pass

mapping = _load_norm_cache()
for cat, rows in labs_raw.items():
    if not rows:
        continue
    df_lab = pd.DataFrame(
        rows, columns=["Date", "Parameter", "Value", "Unit", "Ref Min", "Ref Max", "Method"]
    )
    if mapping:
        df_lab = _apply_normalization(df_lab, mapping)
    df_lab["Value Num"]   = pd.to_numeric(df_lab["Value"],   errors="coerce")
    df_lab["Ref Min Num"] = pd.to_numeric(df_lab["Ref Min"], errors="coerce")
    df_lab["Ref Max Num"] = pd.to_numeric(df_lab["Ref Max"], errors="coerce")
    for _, r in df_lab.dropna(subset=["Value Num"]).iterrows():
        d = pd.to_datetime(r["Date"]).date()
        records.append({
            "source":    cat,
            "parameter": r["Parameter"],
            "unit":      r["Unit"] or "",
            "date":      d,
            "value":     r["Value Num"],
            "ref_min":   r["Ref Min Num"],
            "ref_max":   r["Ref Max Num"],
        })

if not records:
    st.info("No data available for the selected patient.")
    st.stop()

df_all = pd.DataFrame(records)
df_all["date"] = pd.to_datetime(df_all["date"])

patient_row = db.get_patient(patient_id)
try:
    birth_date = pd.to_datetime(str(patient_row[3])).date()
except Exception:
    birth_date = df_all["date"].min().date()
min_data        = birth_date
max_data        = date.today()
min_data_actual = df_all["date"].min().date()

start_filter, end_filter = period_date_filter(
    "analysis_period_radio", "analysis_date_slider", min_data, min_data_actual, max_data
)

df = df_all[
    (df_all["date"].dt.date >= start_filter) &
    (df_all["date"].dt.date <= end_filter)
].copy()

if df.empty:
    st.info("No data in the selected date range.")
    st.stop()

source_order   = ["Blood", "Urine", "Spirometria", "Vitals"]
active_sources = [s for s in source_order if (df["source"] == s).any()]

if not active_sources:
    st.info("No data to display.")
    st.stop()

# ── Filter contextual data to selected period ─────────────────────────────────
def _in_range(start_str, end_str):
    """True if [start_str, end_str] overlaps the selected filter period."""
    if not start_str:
        return False
    try:
        s = pd.to_datetime(start_str).date()
        e = pd.to_datetime(end_str).date() if end_str else date.today()
        return s <= end_filter and e >= start_filter
    except Exception:
        return False


active_meds        = [m for m in meds   if _in_range(m[5], m[6])]
active_conds       = [c for c in conds  if _in_range(c[4], c[5])]
active_events_list = [e for e in events if _in_range(e[4], e[5] or e[4])]

# ── Health score: % of parameters within reference range per exam date ────────
health_scores = {}
for src in ("Blood", "Urine"):
    ref_df = df[df["source"] == src].dropna(subset=["ref_min", "ref_max"])
    if ref_df.empty:
        continue
    by_date = {}
    for d_val, grp in ref_df.groupby(ref_df["date"].dt.date):
        total  = len(grp)
        in_rng = ((grp["value"] >= grp["ref_min"]) & (grp["value"] <= grp["ref_max"])).sum()
        by_date[d_val] = int(in_rng) / total * 100 if total else None
    if by_date:
        health_scores[src] = by_date

# ── Parameter selection expanders ────────────────────────────────────────────
selected_params = {}
show_score      = {}
selected_meds   = []
selected_conds  = []
selected_events = []

_sections = [(src, "source") for src in active_sources]
if active_meds:        _sections.append(("meds",   "meds"))
if active_conds:       _sections.append(("conds",  "conds"))
if active_events_list: _sections.append(("events", "events"))

# Two expanders per row to save vertical space.
for _i in range(0, len(_sections), 2):
    _pair = _sections[_i:_i + 2]
    _cols = st.columns(len(_pair))
    for _col, (_key, _stype) in zip(_cols, _pair):
        with _col:
            if _stype == "source":
                src        = _key
                all_params = sorted(df[df["source"] == src]["parameter"].unique())
                with st.expander(f"**{src}** — {len(all_params)} params"):
                    if src in health_scores:
                        show_score[src] = st.checkbox(
                            "Show score", value=True, key=f"show_score_{src}"
                        )
                    c1, c2, _ = st.columns([1, 1, 6])
                    if c1.button("All", key=f"sel_all_{src}"):
                        st.session_state[f"analysis_params_{src}"] = list(all_params)
                        st.rerun()
                    if c2.button("Clear", key=f"sel_clear_{src}"):
                        st.session_state[f"analysis_params_{src}"] = []
                        st.rerun()
                    selected_params[src] = st.multiselect(
                        "Parameters", options=all_params,
                        key=f"analysis_params_{src}", label_visibility="collapsed",
                    )
            elif _stype == "meds":
                all_med_labels = [f"{m[2]} {m[3] or ''}".strip() for m in active_meds]
                with st.expander(f"**Medications** — {len(active_meds)} active"):
                    c1, c2, _ = st.columns([1, 1, 6])
                    if c1.button("All", key="sel_all_meds"):
                        st.session_state["analysis_params_meds"] = all_med_labels
                        st.rerun()
                    if c2.button("Clear", key="sel_clear_meds"):
                        st.session_state["analysis_params_meds"] = []
                        st.rerun()
                    sel_med_labels = st.multiselect(
                        "Medications", options=all_med_labels,
                        key="analysis_params_meds", label_visibility="collapsed",
                    )
                selected_meds = [m for m in active_meds
                                 if f"{m[2]} {m[3] or ''}".strip() in sel_med_labels]
            elif _stype == "conds":
                all_cond_labels = [c[2] for c in active_conds]
                with st.expander(f"**Conditions** — {len(active_conds)} active"):
                    c1, c2, _ = st.columns([1, 1, 6])
                    if c1.button("All", key="sel_all_conds"):
                        st.session_state["analysis_params_conds"] = all_cond_labels
                        st.rerun()
                    if c2.button("Clear", key="sel_clear_conds"):
                        st.session_state["analysis_params_conds"] = []
                        st.rerun()
                    sel_cond_labels = st.multiselect(
                        "Conditions", options=all_cond_labels,
                        key="analysis_params_conds", label_visibility="collapsed",
                    )
                selected_conds = [c for c in active_conds if c[2] in sel_cond_labels]
            elif _stype == "events":
                all_evt_labels = [f"{e[2]}: {e[3] or e[2]} ({e[4]})"
                                  for e in active_events_list]
                with st.expander(f"**Clinical events** — {len(active_events_list)} in range"):
                    c1, c2, _ = st.columns([1, 1, 6])
                    if c1.button("All", key="sel_all_evts"):
                        st.session_state["analysis_params_evts"] = all_evt_labels
                        st.rerun()
                    if c2.button("Clear", key="sel_clear_evts"):
                        st.session_state["analysis_params_evts"] = []
                        st.rerun()
                    sel_evt_labels = st.multiselect(
                        "Events", options=all_evt_labels,
                        key="analysis_params_evts", label_visibility="collapsed",
                    )
                selected_events = [e for e, lbl in zip(active_events_list, all_evt_labels)
                                   if lbl in sel_evt_labels]

# ── Build subplot row list ─────────────────────────────────────────────────────
# Each scored category gets its own mini-row directly below the parameter row.
# Using separate rows avoids secondary_y axis bugs with shared_xaxes in Plotly.
rows_list = []
for src in active_sources:
    if src in health_scores and show_score.get(src, True):
        rows_list.append(f"{src} Score")
    if selected_params.get(src):
        rows_list.append(src)
if selected_meds:
    rows_list.append("Medications")
if selected_conds:
    rows_list.append("Conditions")
if selected_events:
    rows_list.append("Clinical Events")

if not rows_list:
    st.info("Select at least one parameter to display the chart.")
    st.stop()

n = len(rows_list)

row_heights = []
for r in rows_list:
    if r in ("Medications", "Conditions"):
        row_heights.append(0.35)
    elif r == "Clinical Events":
        row_heights.append(0.5)
    else:
        row_heights.append(1.0)

fig = make_subplots(
    rows=n, cols=1,
    shared_xaxes=True,
    subplot_titles=rows_list,
    row_heights=row_heights,
    vertical_spacing=0.03,
    specs=[[{}] for _ in rows_list],
)

# ── Parameter traces ──────────────────────────────────────────────────────────
for src in active_sources:
    has_params = bool(selected_params.get(src))
    has_score  = f"{src} Score" in rows_list
    if not has_params and not has_score:
        continue
    src_df     = df[df["source"] == src]
    params_sel = selected_params.get(src, [])

    # Health score mini-row — filled area 0-100%.
    if has_score:
        score_row = rows_list.index(f"{src} Score") + 1
        by_date   = health_scores[src]
        dates_s   = sorted(by_date.keys())
        scores_s  = [by_date[d] for d in dates_s]
        sc_color  = SCORE_COLORS[src]
        fig.add_trace(
            go.Scatter(
                x=[pd.Timestamp(d) for d in dates_s],
                y=scores_s,
                mode="lines+markers",
                name=f"{src} Score",
                legendgroup=f"score_{src}",
                legendgrouptitle={"text": f"{src} Score"},
                line=dict(color=sc_color, width=2),
                marker=dict(size=6, color=sc_color, symbol="diamond"),
                fill="tozeroy",
                fillcolor=_hex_to_rgba(sc_color, 0.10),
                hovertemplate=(
                    f"<b>{src} Score</b><br>%{{x|%Y-%m-%d}}<br>%{{y:.1f}}%<extra></extra>"
                ),
            ),
            row=score_row, col=1,
        )
        valid_scores = [v for v in scores_s if v is not None]
        s_min = min(valid_scores) if valid_scores else 0
        s_max = max(valid_scores) if valid_scores else 100
        padding = max((s_max - s_min) * 0.1, 1)
        fig.update_yaxes(
            row=score_row, col=1,
            range=[max(s_min - padding, 0), 100],
            ticksuffix="%",
            showgrid=True, gridcolor="#f0f2f6", zeroline=False,
            tickfont=dict(size=9, color=sc_color),
        )

    if not has_params:
        continue
    row_idx    = rows_list.index(src) + 1
    params_all  = sorted(src_df["parameter"].unique())
    first_shown = True
    for param_idx, param in enumerate(params_all):
        if param not in params_sel:
            continue
        pdata = src_df[src_df["parameter"] == param].sort_values("date")
        unit  = pdata["unit"].iloc[0] if not pdata.empty else ""
        color = TRACE_COLORS[param_idx % len(TRACE_COLORS)]

        # Reference band: two invisible boundary traces + fill="tonexty".
        # More reliable than add_hrect with shared_xaxes.
        ref_min_s = pdata["ref_min"].dropna()
        ref_max_s = pdata["ref_max"].dropna()
        has_ref   = not ref_min_s.empty and not ref_max_s.empty
        if has_ref:
            ref_band = pdata[pdata["ref_min"].notna() & pdata["ref_max"].notna()]
            fig.add_trace(
                go.Scatter(
                    x=ref_band["date"], y=ref_band["ref_max"],
                    mode="lines", line=dict(width=0),
                    showlegend=False, hoverinfo="skip", name="_ref_hi",
                ),
                row=row_idx, col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=ref_band["date"], y=ref_band["ref_min"],
                    mode="lines", line=dict(width=0),
                    fill="tonexty", fillcolor=_hex_to_rgba(color, 0.20),
                    showlegend=False, hoverinfo="skip", name="_ref_lo",
                ),
                row=row_idx, col=1,
            )

        # Color out-of-range markers red; in-range markers use the trace color.
        if has_ref:
            marker_colors = [
                "#EF4444"
                if (pd.notna(row["ref_min"]) and pd.notna(row["ref_max"]) and
                    (row["value"] < row["ref_min"] or row["value"] > row["ref_max"]))
                else color
                for _, row in pdata.iterrows()
            ]
            marker_sizes = [10 if c == "#EF4444" else 7 for c in marker_colors]
        else:
            marker_colors = color
            marker_sizes  = 7

        fig.add_trace(
            go.Scatter(
                x=pdata["date"],
                y=pdata["value"],
                mode="lines+markers",
                name=param,
                legendgroup=src,
                legendgrouptitle={"text": src} if first_shown else {},
                line=dict(color=color, width=2),
                marker=dict(size=marker_sizes, color=marker_colors,
                            line=dict(width=1.5, color="white")),
                hovertemplate=f"<b>{param}</b><br>%{{x|%Y-%m-%d}}<br>%{{y}} {unit}<extra></extra>",
            ),
            row=row_idx, col=1,
        )
        first_shown = False

    fig.update_yaxes(row=row_idx, col=1,
                     showgrid=True, gridcolor="#f0f2f6", zeroline=False)

# ── Medications Gantt ─────────────────────────────────────────────────────────
if selected_meds:
    med_row = rows_list.index("Medications") + 1
    for i, med in enumerate(selected_meds):
        m_start = max(pd.Timestamp(med[5]), pd.Timestamp(start_filter))
        m_end   = min(
            pd.Timestamp(med[6]) if med[6] else pd.Timestamp.today(),
            pd.Timestamp(end_filter),
        )
        if m_start >= m_end:
            continue
        label = f"{med[2]} {med[3] or ''}".strip()
        color = TRACE_COLORS[i % len(TRACE_COLORS)]
        fig.add_trace(
            go.Scatter(
                x=[m_start, m_end],
                y=[label, label],
                mode="lines+markers",
                name=label,
                legendgroup="Medications",
                legendgrouptitle={"text": "Medications"} if i == 0 else {},
                line=dict(color=color, width=8),
                marker=dict(size=8, color=color),
                hovertemplate=f"<b>{label}</b><br>%{{x|%Y-%m-%d}}<extra></extra>",
            ),
            row=med_row, col=1,
        )
    fig.update_yaxes(row=med_row, col=1,
                     showgrid=False, zeroline=False, tickfont=dict(size=9))

# ── Conditions Gantt ──────────────────────────────────────────────────────────
if selected_conds:
    cond_row = rows_list.index("Conditions") + 1
    for i, cond in enumerate(selected_conds):
        c_start = max(pd.Timestamp(cond[4]), pd.Timestamp(start_filter))
        c_end   = min(
            pd.Timestamp(cond[5]) if cond[5] else pd.Timestamp.today(),
            pd.Timestamp(end_filter),
        )
        if c_start >= c_end:
            continue
        name  = cond[2]
        ctype = cond[3] or ""
        color = COND_COLORS.get(ctype, "#6B7280")
        label = f"{name} ({ctype})" if ctype else name
        fig.add_trace(
            go.Scatter(
                x=[c_start, c_end],
                y=[name, name],
                mode="lines+markers",
                name=label,
                legendgroup="Conditions",
                legendgrouptitle={"text": "Conditions"} if i == 0 else {},
                line=dict(color=color, width=8),
                marker=dict(size=8, color=color),
                hovertemplate=f"<b>{label}</b><br>%{{x|%Y-%m-%d}}<extra></extra>",
            ),
            row=cond_row, col=1,
        )
    fig.update_yaxes(row=cond_row, col=1,
                     showgrid=False, zeroline=False, tickfont=dict(size=9))

# ── Events Gantt ──────────────────────────────────────────────────────────────
if selected_events:
    evt_row = rows_list.index("Clinical Events") + 1
    for i, e in enumerate(selected_events):
        etype  = e[2] or "Event"
        desc   = e[3] or ""
        loc    = e[6] or ""
        color  = TRACE_COLORS[i % len(TRACE_COLORS)]
        label  = f"{desc} ({etype})" if desc else etype
        e_start = max(pd.Timestamp(e[4]), pd.Timestamp(start_filter))
        if e[5]:
            e_end = min(pd.Timestamp(e[5]), pd.Timestamp(end_filter))
            xs, ys, mode = [e_start, e_end], [label, label], "lines+markers"
        else:
            xs, ys, mode = [e_start], [label], "markers"
        hover = f"<b>{label}</b>"
        if loc:
            hover += f"<br>{loc}"
        hover += "<br>%{x|%Y-%m-%d}<extra></extra>"
        fig.add_trace(
            go.Scatter(
                x=xs, y=ys,
                mode=mode,
                name=label,
                legendgroup="Events",
                legendgrouptitle={"text": "Clinical Events"} if i == 0 else {},
                line=dict(color=color, width=8),
                marker=dict(size=8, color=color, symbol="diamond"),
                hovertemplate=hover,
            ),
            row=evt_row, col=1,
        )
    fig.update_yaxes(row=evt_row, col=1,
                     showgrid=False, zeroline=False, tickfont=dict(size=9))

# ── Layout ────────────────────────────────────────────────────────────────────
total_height = sum(
    100 if r in ("Medications", "Conditions")
    else 130 if r == "Clinical Events"
    else 350
    for r in rows_list
) + 60

fig.update_xaxes(
    showgrid=True, gridcolor="#f0f2f6",
    range=[pd.Timestamp(start_filter), pd.Timestamp(end_filter)],
)
fig.update_layout(
    height=max(total_height, 400),
    plot_bgcolor="white",
    hovermode="x unified",
    margin=dict(l=0, r=0, t=25, b=10),
    showlegend=False,
)

st.plotly_chart(fig, width='stretch')
