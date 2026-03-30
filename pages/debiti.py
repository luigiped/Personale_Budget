"""
pages/debiti.py
---------------
Tab DEBITI — Personal Budget Dashboard.

Contenuto:
  - 4 KPI cards riepilogo (capitale, residuo, interessi pagati/residui)
  - Grafico avanzamento finanziamenti (stacked bar orizzontale)
  - Pie chart pagato vs residuo
  - Grafico interessi pagati vs residui
  - Tabella riepilogo rate con colori semantici
"""

import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from html import escape

import logiche as log
from utils.constants import Colors, PLOTLY_CONFIG
from utils.formatters import eur0, eur2, format_eur, chip_html
from utils.charts import style_fig
from utils.html_tables import scroll_table, _td, _tr


# ──────────────────────────────────────────────────────────────────────────────
# Helper: calcola rate pagate ricavandole dai movimenti
# ──────────────────────────────────────────────────────────────────────────────

def _mesi_pagati_da_mov(df_m: pd.DataFrame, nome_fin: str, rata=None, data_inizio=None) -> int | None:
    """Inferisce le rate pagate cercando i movimenti che corrispondono al finanziamento."""
    if df_m is None or df_m.empty:
        return None

    raw    = str(nome_fin or "").strip()
    tokens = [raw]
    if "." in raw:
        tokens.append(raw.split(".")[-1])
    tokens.append(re.sub(r"^fin\.?\s*", "", raw, flags=re.I))
    for t in re.split(r"[\s\-_/.]+", raw):
        if len(t.strip()) >= 3:
            tokens.append(t.strip())
    tokens  = list(dict.fromkeys(t for t in tokens if t.strip()))
    pattern = "|".join(re.escape(t) for t in tokens) if tokens else None
    if not pattern:
        return None

    tipo = df_m["Tipo"].astype(str).str.upper().str.strip()
    mask = (tipo == "USCITA") & (
        df_m["Dettaglio"].astype(str).str.contains(pattern, case=False, na=False) |
        df_m["Note"].astype(str).str.contains(pattern, case=False, na=False)
    )
    df_f = df_m[mask].copy()
    if df_f.empty:
        return None

    df_f["Data"] = pd.to_datetime(df_f["Data"], errors="coerce")
    df_f = df_f[df_f["Data"].notna()]
    if data_inizio is not None:
        inizio = pd.to_datetime(data_inizio, errors="coerce")
        if pd.notna(inizio):
            df_f = df_f[df_f["Data"] >= inizio]
    if df_f.empty:
        return None

    rata_abs = abs(float(rata)) if rata is not None else 0.0
    if rata_abs > 0:
        tol  = max(1.0, rata_abs * 0.25)
        df_f = df_f[df_f["Importo"].abs().between(rata_abs - tol, rata_abs + tol)]

    return int(len(df_f)) if not df_f.empty else None


# ──────────────────────────────────────────────────────────────────────────────
# Render principale
# ──────────────────────────────────────────────────────────────────────────────

def render(ctx: dict) -> None:
    df_fin = ctx["df_fin"]
    df_mov = ctx["df_mov"]

    st.markdown("<div class='section-title'>DEBITI</div>", unsafe_allow_html=True)

    if df_fin.empty:
        st.info("Nessun finanziamento presente. Aggiungilo nel tab Registro.")
        return

    # ── Calcola aggregati ─────────────────────────────────────────────────────
    totale_capitale  = df_fin["capitale_iniziale"].sum()
    totale_residuo   = 0.0
    interessi_pagati = 0.0
    interessi_totali = 0.0
    fin_rows         = []
    dettagli_rows    = []

    for _, f in df_fin.iterrows():
        dati_base = log.calcolo_finanziamento(
            f["capitale_iniziale"], f["taeg"], f["durata_mesi"],
            f["data_inizio"], f["giorno_scadenza"],
        )
        rate_db  = int(f["rate_pagate"]) if "rate_pagate" in f.index and pd.notna(f["rate_pagate"]) else None
        rate_mov = _mesi_pagati_da_mov(df_mov, f["nome"], dati_base["rata"], f["data_inizio"])
        rate_cal = int(dati_base.get("mesi_pagati", 0))
        vals     = [v for v in [rate_db, rate_mov, rate_cal] if v is not None]
        rate_eff = max(vals) if vals else None

        dati    = log.calcolo_finanziamento(
            f["capitale_iniziale"], f["taeg"], f["durata_mesi"],
            f["data_inizio"], f["giorno_scadenza"],
            rate_pagate_override=rate_eff,
        )
        pagato  = max(dati["capitale_pagato"], 0)
        residuo = max(dati["debito_residuo"],  0)

        fin_rows.append({"Nome": f["nome"], "Pagato": pagato, "Residuo": residuo})
        dettagli_rows.append({
            "Nome":          f["nome"],
            "Rata":          dati["rata"],
            "Residuo":       dati["debito_residuo"],
            "% Completato":  round(dati["percentuale_completato"], 1),
            "Mesi rim.":     dati["mesi_rimanenti"],
        })
        totale_residuo   += residuo
        interessi_pagati += dati["interessi_pagati"]
        interessi_totali += dati["interessi_totali"]

    df_prog    = pd.DataFrame(fin_rows)
    totale_pag = max(0.0, totale_capitale - totale_residuo)
    int_res    = max(0.0, interessi_totali - interessi_pagati)

    # ── 4 KPI ─────────────────────────────────────────────────────────────────
    _kpis = [
        ("Capitale totale",   eur2(totale_capitale),  Colors.TEXT,       "rgba(79,142,240,0.15)"),
        ("Debito residuo",    eur2(totale_residuo),   Colors.RED_BRIGHT, "rgba(250,89,142,0.18)"),
        ("Interessi pagati",  eur2(interessi_pagati), Colors.AMBER,      "rgba(245,166,35,0.15)"),
        ("Interessi residui", eur2(int_res),          Colors.AMBER,      "rgba(245,166,35,0.12)"),
    ]
    _cols = st.columns(4)
    for _c, (_l, _v, _color, _glow) in zip(_cols, _kpis):
        _c.markdown(
            f"""<div style="background:#0c1120;border:1px solid rgba(92,118,178,0.22);
            border-radius:14px;padding:18px 14px 14px;text-align:center;
            box-shadow:0 4px 20px rgba(0,0,0,0.4),0 0 24px {_glow};position:relative;overflow:hidden;">
  <div style="font-size:0.65rem;font-weight:700;letter-spacing:1.4px;text-transform:uppercase;
    color:rgba(180,200,240,0.55);margin-bottom:8px;">{_l}</div>
  <div style="font-family:'JetBrains Mono',monospace;font-size:1.2rem;font-weight:700;color:{_color};">{_v}</div>
  <div style="position:absolute;bottom:0;left:0;right:0;height:2px;
    background:linear-gradient(90deg,{_color}60,transparent);"></div>
</div>""",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # ── Avanzamento + Pie ─────────────────────────────────────────────────────
    c1, c2 = st.columns([1.4, 1], gap="large")
    with c1:
        st.markdown("<div class='panel-title'>📊 Avanzamento finanziamenti</div>", unsafe_allow_html=True)
        fig_prog = go.Figure()
        fig_prog.add_bar(
            y=df_prog["Nome"], x=df_prog["Pagato"], orientation="h",
            name="Totale pagato", marker_color="#10d98a", marker_cornerradius=6,
            text=df_prog["Pagato"].map(eur0), textposition="inside",
            insidetextanchor="middle", textfont=dict(color="#07090f", size=12),
        )
        fig_prog.add_bar(
            y=df_prog["Nome"], x=df_prog["Residuo"], orientation="h",
            name="Debito residuo", marker_color="#f26a6a", marker_cornerradius=6,
            text=df_prog["Residuo"].map(eur0), textposition="inside",
            insidetextanchor="middle", textfont=dict(color="#ffffff", size=12),
        )
        fig_prog.update_layout(barmode="stack", xaxis=dict(tickprefix="€ ", tickformat=",.0f"))
        style_fig(fig_prog, height=300, show_legend=True)
        st.plotly_chart(fig_prog, use_container_width=True, config=PLOTLY_CONFIG)

    with c2:
        st.markdown("<div class='panel-title'>🥧 Pagato vs Residuo</div>", unsafe_allow_html=True)
        fig_pie = go.Figure(go.Pie(
            labels=["Pagato", "Residuo"],
            values=[totale_pag, totale_residuo],
            hole=0.35, textinfo="percent+label",
            marker=dict(colors=["#10d98a", "rgba(242,106,106,0.60)"]),
            textfont=dict(size=13, color="#ffffff"),
        ))
        style_fig(fig_pie, height=300, show_legend=False)
        st.plotly_chart(fig_pie, use_container_width=True, config=PLOTLY_CONFIG)

    # ── Interessi + Riepilogo rate ────────────────────────────────────────────
    c3, c4 = st.columns([1, 1.3], gap="large")
    with c3:
        st.markdown("<div class='panel-title'>💰 Interessi pagati vs residui</div>", unsafe_allow_html=True)
        fig_int = go.Figure()
        fig_int.add_bar(
            y=["Interessi"], x=[interessi_pagati], orientation="h",
            name="Quota pagata", marker_color="#f5a623", marker_cornerradius=6,
            text=[eur0(interessi_pagati)], textposition="inside",
            insidetextanchor="middle", textfont=dict(color="#07090f", size=13),
        )
        fig_int.add_bar(
            y=["Interessi"], x=[int_res], orientation="h",
            name="Interessi residui", marker_color="#5a6f8c", marker_cornerradius=6,
            text=[eur0(int_res)], textposition="inside",
            insidetextanchor="middle", textfont=dict(color="#ffffff", size=13),
        )
        fig_int.update_layout(
            barmode="stack",
            xaxis=dict(tickprefix="€ ", tickformat=",.0f"),
            yaxis=dict(tickfont=dict(color=Colors.TEXT)),
            margin=dict(l=10, r=40, t=20, b=10),
        )
        style_fig(fig_int, height=180, show_legend=True)
        st.plotly_chart(fig_int, use_container_width=True, config=PLOTLY_CONFIG)

    with c4:
        st.markdown("<div class='panel-title'>📋 Riepilogo rate</div>", unsafe_allow_html=True)
        df_tab = pd.DataFrame(dettagli_rows)
        if not df_tab.empty:
            debt_rows = []
            for _, row in df_tab.iterrows():
                perc   = float(row["% Completato"])
                mesi_r = int(row["Mesi rim."])
                pc = Colors.GREEN if perc >= 50 else Colors.AMBER if perc >= 25 else Colors.RED
                mc = Colors.RED   if mesi_r > 120 else Colors.AMBER if mesi_r > 36 else Colors.GREEN
                debt_rows.append(_tr([
                    _td(f"<strong>{escape(str(row['Nome']))}</strong>", color=Colors.TEXT, weight=600),
                    _td(eur2(row["Rata"]),    color=Colors.RED,  mono=True, weight=600),
                    _td(eur2(row["Residuo"]), color=Colors.TEXT, mono=True),
                    _td(f"{perc:.1f}%",       color=pc,          mono=True, align="center"),
                    _td(str(mesi_r),          color=mc,          mono=True, align="center"),
                ]))
            st.markdown(scroll_table(
                title="Riepilogo finanziamenti", right_html="",
                columns=[("Nome","left"),("Rata","center"),("Residuo","center"),("% Compl.","center"),("Mesi","left")],
                widths=[1.4, 1.1, 1.5, 0.9, 0.7],
                rows_html=debt_rows, height_px=230,
            ), unsafe_allow_html=True)
        else:
            st.info("Nessun finanziamento trovato.")