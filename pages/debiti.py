"""
pages/debiti.py
---------------
Pagina DEBITI — Personal Budget Dashboard.

Contenuto:
  - Grafico avanzamento finanziamenti (stacked bar: pagato + residuo)
  - Pie chart totale pagato / residuo
  - Tabella riepilogo rate con colori semantici
"""

import re
from html import escape

import pandas as pd
import plotly.graph_objects as go
from nicegui import ui

import logiche as log
from utils.constants import Colors, PLOTLY_CONFIG
from utils.formatters import eur0, eur2
from utils.charts import style_fig
from utils.html_tables import scroll_table, _td, _tr

COLOR_PAGATO     = "#10d98a"
COLOR_RESIDUO    = "#f26a6a"
COLOR_RESIDUO_PIE = "rgba(242,106,106,0.55)"


def render(user_email: str, anno_sel: int, mese_sel: int, settings: dict, data: dict) -> None:
    """Entry point — chiamata da main.py."""
    df_mov = data["df_mov"]
    df_fin = data["df_fin"]

    ui.html("<div class='section-title'>DEBITI</div>")

    if df_fin.empty:
        ui.label("Nessun finanziamento presente. Aggiungilo nel tab Registro.").classes("text-sm").style("color: var(--txt-mid);")
        return

    # Calcolo avanzamento per ogni finanziamento
    fin_rows     = []
    dettagli_rows = []
    totale_capitale   = df_fin["capitale_iniziale"].sum()
    totale_residuo    = 0.0
    interessi_pagati  = 0.0
    interessi_totali  = 0.0

    for _, f in df_fin.iterrows():
        dati_base = log.calcolo_finanziamento(
            f["capitale_iniziale"], f["taeg"], f["durata_mesi"],
            f["data_inizio"], f["giorno_scadenza"]
        )
        rate_db  = int(f["rate_pagate"]) if "rate_pagate" in f.index and pd.notna(f["rate_pagate"]) else None
        rate_mov = _mesi_pagati_da_mov(df_mov, f["nome"], dati_base["rata"], f["data_inizio"])
        rate_cal = int(dati_base.get("mesi_pagati", 0))
        vals     = [v for v in [rate_db, rate_mov, rate_cal] if v is not None]
        rate_eff = max(vals) if vals else None

        dati = log.calcolo_finanziamento(
            f["capitale_iniziale"], f["taeg"], f["durata_mesi"],
            f["data_inizio"], f["giorno_scadenza"],
            rate_pagate_override=rate_eff,
        )
        pagato  = max(dati["capitale_pagato"], 0)
        residuo = max(dati["debito_residuo"],  0)

        fin_rows.append({"Nome": f["nome"], "Pagato": pagato, "Residuo": residuo})
        dettagli_rows.append({
            "Nome": f["nome"], "Rata": dati["rata"],
            "Residuo": dati["debito_residuo"],
            "% Completato": round(dati["percentuale_completato"], 1),
            "Mesi rim.": dati["mesi_rimanenti"],
        })
        totale_residuo   += residuo
        interessi_pagati += dati["interessi_pagati"]
        interessi_totali += dati["interessi_totali"]

    df_prog    = pd.DataFrame(fin_rows)
    totale_pag = max(0.0, totale_capitale - totale_residuo)
    int_res    = max(0.0, interessi_totali - interessi_pagati)

    # ── KPI sommario ──
    with ui.grid(columns=4).classes("w-full gap-3 mb-4"):
        _kpi_mini("Capitale totale",     eur2(totale_capitale),  Colors.TEXT)
        _kpi_mini("Debito residuo",       eur2(totale_residuo),   Colors.RED)
        _kpi_mini("Interessi pagati",     eur2(interessi_pagati), Colors.AMBER)
        _kpi_mini("Interessi residui",    eur2(int_res),          Colors.AMBER)

    # ── Grafici affiancati ──
    with ui.grid(columns=2).classes("w-full gap-4 mb-4"):

        with ui.card().style(
            "background: var(--bg-card); border: 1px solid var(--bdr); border-radius: 12px; padding: 16px;"
        ):
            ui.html("<div class='panel-title'>📊 Avanzamento finanziamenti</div>")
            _render_progress_chart(df_prog)

        with ui.card().style(
            "background: var(--bg-card); border: 1px solid var(--bdr); border-radius: 12px; padding: 16px;"
        ):
            ui.html("<div class='panel-title'>🥧 Pagato vs Residuo</div>")
            _render_pie_chart(totale_pag, totale_residuo)

    # ── Tabella riepilogo ──
    with ui.card().classes("w-full").style(
        "background: var(--bg-card); border: 1px solid var(--bdr); border-radius: 12px; padding: 16px;"
    ):
        ui.html("<div class='panel-title'>📋 Riepilogo rate</div>")
        df_tabella = pd.DataFrame(dettagli_rows)
        if not df_tabella.empty:
            _render_dettagli_table(df_tabella)


# ---------------------------------------------------------------------------
# KPI mini
# ---------------------------------------------------------------------------

def _kpi_mini(label: str, value: str, color: str) -> None:
    with ui.element("div").style(
        f"background: var(--bg-form); border: 1px solid var(--bdr); border-radius: 8px; "
        f"padding: 12px 14px; text-align: center;"
    ):
        ui.html(f"<div style='font-size:0.62rem;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:var(--txt-mid);margin-bottom:6px;'>{label}</div>")
        ui.html(f"<div style='font-family:JetBrains Mono,monospace;font-size:0.95rem;font-weight:700;color:{color};'>{value}</div>")


# ---------------------------------------------------------------------------
# Grafico avanzamento (stacked bar orizzontale)
# ---------------------------------------------------------------------------

def _render_progress_chart(df_prog: pd.DataFrame) -> None:
    fig = go.Figure()
    fig.add_bar(
        y=df_prog["Nome"], x=df_prog["Pagato"], orientation="h",
        name="Totale pagato", marker_color=COLOR_PAGATO, marker_cornerradius=6,
        text=df_prog["Pagato"].map(eur0), textposition="inside",
        insidetextanchor="middle", textfont=dict(color="#ffffff", size=13),
    )
    fig.add_bar(
        y=df_prog["Nome"], x=df_prog["Residuo"], orientation="h",
        name="Debito residuo", marker_color=COLOR_RESIDUO, marker_cornerradius=6,
        text=df_prog["Residuo"].map(eur0), textposition="inside",
        insidetextanchor="middle", textfont=dict(color="#ffffff", size=13),
    )
    fig.update_layout(barmode="stack", xaxis=dict(tickprefix="€ ", tickformat=",.0f"))
    style_fig(fig, height=320, show_legend=True)
    ui.plotly(fig).classes("w-full")


# ---------------------------------------------------------------------------
# Pie chart
# ---------------------------------------------------------------------------

def _render_pie_chart(totale_pag: float, totale_residuo: float) -> None:
    fig = go.Figure(go.Pie(
        labels=["Pagato", "Residuo"],
        values=[totale_pag, totale_residuo],
        hole=0.35, textinfo="percent",
        marker=dict(colors=[COLOR_PAGATO, COLOR_RESIDUO_PIE]),
        textfont=dict(size=15),
    ))
    style_fig(fig, height=320, show_legend=True)
    ui.plotly(fig).classes("w-full")


# ---------------------------------------------------------------------------
# Tabella riepilogo finanziamenti
# ---------------------------------------------------------------------------

def _render_dettagli_table(df_tabella: pd.DataFrame) -> None:
    debt_rows = []
    for _, row in df_tabella.iterrows():
        perc       = float(row["% Completato"])
        mesi_r     = int(row["Mesi rim."])
        perc_color = Colors.GREEN if perc >= 50 else Colors.AMBER if perc >= 25 else Colors.RED
        mesi_color = Colors.RED   if mesi_r > 120 else Colors.AMBER if mesi_r > 36 else Colors.GREEN
        debt_rows.append(_tr([
            _td(f"<strong>{escape(str(row['Nome']))}</strong>", color=Colors.TEXT, weight=600),
            _td(eur2(row["Rata"]),     color=Colors.RED,  mono=True, weight=600),
            _td(eur2(row["Residuo"]),  color=Colors.TEXT, mono=True),
            _td(f"{perc:.1f}%",        color=perc_color,  mono=True, align="center"),
            _td(str(mesi_r),           color=mesi_color,  mono=True, align="center"),
        ]))
    ui.html(scroll_table(
        title="Riepilogo finanziamenti", right_html="",
        columns=[("Nome","left"),("Rata","center"),("Residuo","center"),("% Compl.","center"),("Mesi","left")],
        widths=[1.4, 1.1, 1.5, 0.9, 0.7],
        rows_html=debt_rows, height_px=230,
    )).classes("w-full")


# ---------------------------------------------------------------------------
# Helper: conta rate pagate dai movimenti
# ---------------------------------------------------------------------------

def _mesi_pagati_da_mov(df_m: pd.DataFrame, nome_fin: str, rata=None, data_inizio=None):
    def _fin_match_pattern(nome: str):
        tokens = [t for t in re.split(r"[\s\-_/]+", nome.strip()) if len(t) >= 3]
        return "|".join(re.escape(t) for t in tokens) if tokens else None

    if df_m is None or df_m.empty:
        return None
    pattern = _fin_match_pattern(nome_fin)
    if not pattern:
        return None
    tipo  = df_m["Tipo"].astype(str).str.upper().str.strip()
    mask  = (tipo == "USCITA") & (
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