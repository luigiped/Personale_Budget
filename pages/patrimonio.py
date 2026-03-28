"""
pages/patrimonio.py
-------------------
Pagina PATRIMONIO — Personal Budget Dashboard.

Contenuto:
  - PAC (Piano di Accumulo Capitale): valore attuale, P&L, proiezione
  - Fondo Pensione: valore attuale, progress fiscale, proiezione
  - Composizione portafoglio (pie chart)
  - Versamenti PAC / Fondo dell'anno
"""

from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from nicegui import ui

import logiche as log
from utils.constants import Colors, MONTH_SHORT, PLOTLY_CONFIG
from utils.formatters import eur0, eur2, fmt_num_it, hex_to_rgba
from utils.charts import style_fig


def render(user_email: str, anno_sel: int, mese_sel: int, settings: dict, data: dict) -> None:
    """Entry point — chiamata da main.py."""
    from main import s_num, s_num_candidates, s_txt

    df_mov = data["df_mov"]

    # Lettura parametri
    pac_ticker  = s_txt(settings, "pac_ticker", "")
    pac_quote   = s_num(settings, "pac_quote", 0.0)
    pac_cap     = s_num(settings, "pac_capitale_investito", 0.0)
    pac_vers    = s_num(settings, "pac_versamento_mensile", 80.0)
    pac_rend    = s_num(settings, "pac_rendimento_stimato", 7.0)

    fondo_quote      = s_num(settings, "fondo_quote", 0.0)
    fondo_cap        = s_num(settings, "fondo_capitale_investito", 0.0)
    fondo_vers       = s_num(settings, "fondo_versamento_mensile", 50.0)
    fondo_valore_q   = s_num(settings, "fondo_valore_quota", 7.28)
    fondo_rend       = s_num(settings, "fondo_rendimento_stimato", 5.0)
    aliq_irpef       = s_num(settings, "aliquota_irpef", 0.26)
    fondo_tfr        = s_num(settings, "fondo_tfr_versato_anno", 0.0)
    fondo_snapshot_s = s_txt(settings, "fondo_data_snapshot", str(date.today()))
    fondo_snapshot   = pd.to_datetime(fondo_snapshot_s, errors="coerce").date() if fondo_snapshot_s else date.today()

    saldo_disp  = s_num_candidates(settings, [f"saldo_iniziale_{anno_sel}", f"saldo iniziale_{anno_sel}"], 0.0)
    saldo_rev   = s_num(settings, "saldo_revolut", 0.0)

    ui.html("<div class='section-title'>PATRIMONIO</div>")

    # Valori calcolati (usati anche per composizione portafoglio)
    valore_pac_attuale   = pac_cap
    valore_fondo_attuale = fondo_cap

    # ── PAC ──
    with ui.card().classes("w-full mb-4").style(
        "background: var(--bg-card); border: 1px solid var(--bdr); border-radius: 12px; padding: 16px;"
    ):
        with ui.row().classes("items-center justify-between w-full mb-2"):
            ui.html("<div class='panel-title'>📈 PAC — Piano di Accumulo</div>")
            if pac_ticker and pac_quote >= 0:
                ui.html(
                    f"<span class='badge badge-red' style='font-size:0.72rem;'>Ticker {pac_ticker} | {int(pac_quote)} Quote</span>"
                )

        if pac_ticker and pac_quote >= 0:
            res_pac = log.analisi_pac(
                ticker=pac_ticker, quote_base=pac_quote, capitale_base=pac_cap,
                versamento_mensile_proiezione=pac_vers,
                rendimento_annuo_stimato=pac_rend,
                df_transazioni=df_mov, anno_corrente=anno_sel,
            )
            s = res_pac["Sintesi"]
            valore_pac_attuale = s["Valore Attuale"]

            _render_pac_kpi(s)
            _render_pac_chart(res_pac["Grafico_Proiezione"])
        else:
            ui.label("Imposta 'Ticker' e 'Quote' nelle impostazioni rapide.").classes("text-sm").style("color: var(--txt-mid);")

    ui.separator().style("border-color: var(--bdr); margin: 4px 0 16px;")

    # ── Fondo Pensione ──
    with ui.card().classes("w-full mb-4").style(
        "background: var(--bg-card); border: 1px solid var(--bdr); border-radius: 12px; padding: 16px;"
    ):
        ui.html("<div class='panel-title'>🏦 Fondo Pensione</div>")
        if fondo_valore_q > 0 and fondo_quote > 0:
            res_fondo = log.analisi_fondo_pensione(
                fondo_valore_q, fondo_quote, fondo_cap, fondo_vers, fondo_rend,
                df_mov, anno_sel, aliquota_irpef=aliq_irpef, anni=30,
                data_snapshot=fondo_snapshot, tfr_versato_anno=fondo_tfr,
            )
            valore_fondo_attuale = res_fondo["Sintesi"]["Valore Attuale"]
            perc_fp = min(res_fondo["Avanzamento_Fiscale"]["Percentuale"] / 100, 1.0)

            _render_fondo_kpi(res_fondo["Sintesi"])
            _render_progress_bar(perc_fp)
            _render_fondo_chart(res_fondo["Grafico_Proiezione"])
        else:
            ui.label("Imposta valore quota e quote fondo nelle impostazioni rapide.").classes("text-sm").style("color: var(--txt-mid);")

    ui.separator().style("border-color: var(--bdr); margin: 4px 0 16px;")

    # ── Composizione portafoglio + Versamenti ──
    with ui.grid(columns=2).classes("w-full gap-4"):

        with ui.card().style(
            "background: var(--bg-card); border: 1px solid var(--bdr); border-radius: 12px; padding: 16px;"
        ):
            ui.html("<div class='panel-title'>🥧 Composizione portafoglio</div>")
            # Recupera saldo disponibile reale
            from logiche import saldo_disponibile_da_inizio
            saldo_d = saldo_disponibile_da_inizio(df_mov, anno_sel, mese_sel, saldo_disp)
            comp = log.composizione_portafoglio(float(saldo_d), float(saldo_rev), valore_pac_attuale, valore_fondo_attuale)
            if comp:
                fig_comp = px.pie(
                    comp["Dettaglio"], names="Asset", values="Valore",
                    hole=0.35, color_discrete_sequence=Colors.SEQ,
                )
                fig_comp.update_traces(textinfo="percent+label", textposition="inside")
                fig_comp.update_layout(showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
                style_fig(fig_comp, height=300, show_legend=False)
                ui.plotly(fig_comp).classes("w-full")

        with ui.card().style(
            "background: var(--bg-card); border: 1px solid var(--bdr); border-radius: 12px; padding: 16px;"
        ):
            ui.html("<div class='panel-title'>💸 Versamenti PAC / Fondo</div>")
            _render_versamenti_chart(df_mov, anno_sel)


# ---------------------------------------------------------------------------
# KPI cards PAC
# ---------------------------------------------------------------------------

def _render_pac_kpi(s: dict) -> None:
    with ui.grid(columns=4).classes("w-full gap-3 mb-3"):
        _kpi_mini("Valore attuale",     eur2(s["Valore Attuale"]), Colors.GREEN_BRIGHT)
        _kpi_mini("Rendimento",         f"{eur2(s['P&L'], signed=True)} ({s['P&L %']}%)",
                   Colors.GREEN if s.get("P&L", 0) >= 0 else Colors.RED)
        _kpi_mini("Tasse plusvalenze",  eur2(s["Imposte"]),  Colors.AMBER)
        _kpi_mini("Netto smobilizzo",   eur2(s["Netto"]),    Colors.ACCENT if hasattr(Colors, "ACCENT") else "#4f8ef0")


def _render_fondo_kpi(s: dict) -> None:
    with ui.grid(columns=3).classes("w-full gap-3 mb-3"):
        _kpi_mini("Valore attuale",  eur2(s["Valore Attuale"]), Colors.GREEN_BRIGHT)
        _kpi_mini("Quote possedute", fmt_num_it(s["Quote Attuali"]), Colors.TEXT)
        _kpi_mini("Rendimento",      f"{eur2(s['P&L'], signed=True)} ({s['P&L %']}%)",
                   Colors.GREEN if s.get("P&L", 0) >= 0 else Colors.RED)


def _kpi_mini(label: str, value: str, color: str) -> None:
    with ui.element("div").style(
        f"background: var(--bg-form); border: 1px solid var(--bdr); border-radius: 8px; "
        f"padding: 12px 14px; text-align: center;"
    ):
        ui.html(f"<div style='font-size:0.62rem;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:var(--txt-mid);margin-bottom:6px;'>{label}</div>")
        ui.html(f"<div style='font-family:JetBrains Mono,monospace;font-size:0.95rem;font-weight:700;color:{color};'>{value}</div>")


# ---------------------------------------------------------------------------
# Progress bar fiscale fondo pensione
# ---------------------------------------------------------------------------

def _render_progress_bar(perc: float) -> None:
    pct = perc * 100
    ui.html(
        f"<div style='background:rgba(79,142,240,0.08);border-radius:4px;height:6px;margin:10px 0 16px;'>"
        f"<div style='background:var(--acc);height:6px;border-radius:4px;width:{pct:.1f}%;'></div>"
        f"</div>"
    )


# ---------------------------------------------------------------------------
# Grafici PAC e Fondo
# ---------------------------------------------------------------------------

def _render_pac_chart(df_pac: pd.DataFrame) -> None:
    fig = go.Figure()
    for name, color, fill in [
        ("Proiezione Stimata", "#34d399", "tozeroy"),
        ("Capitale Versato",   "#60a5fa", "tozeroy"),
        ("Valore Netto",       "#facc15", "none"),
    ]:
        fig.add_trace(go.Scatter(
            x=df_pac["Mese"], y=df_pac[name], name=name,
            mode="lines",
            line=dict(color=color, width=3 if name == "Proiezione Stimata" else 2),
            fill=fill, fillcolor=hex_to_rgba(color, 0.1),
        ))
    style_fig(fig, height=320, show_legend=True)
    ui.plotly(fig).classes("w-full")


def _render_fondo_chart(df_fondo: pd.DataFrame) -> None:
    fig = go.Figure()
    for name, color, fill in [
        ("Proiezione Teorica",  "#f472b6", "tozeroy"),
        ("Cap.Versato Cumu.",   "#60a5fa", "tozeroy"),
        ("Valore Attuale Linea", "#facc15", "none"),
    ]:
        fig.add_trace(go.Scatter(
            x=df_fondo["Mese"], y=df_fondo[name], mode="lines",
            line=dict(color=color, width=3 if "Teorica" in name else 2,
                      dash="dash" if "Linea" in name else "solid"),
            fill=fill, fillcolor=hex_to_rgba(color, 0.08),
            name=name.replace(" Linea", ""),
        ))
    style_fig(fig, height=380, show_legend=True)
    ui.plotly(fig).classes("w-full")


# ---------------------------------------------------------------------------
# Grafico versamenti PAC/Fondo
# ---------------------------------------------------------------------------

def _render_versamenti_chart(df_mov: pd.DataFrame, anno_sel: int) -> None:
    df_inv = df_mov[
        (df_mov["Categoria"] == "INVESTIMENTI") &
        (df_mov["Tipo"] == "USCITA") &
        (df_mov["Data"].dt.year == anno_sel)
    ].copy()

    if df_inv.empty:
        ui.label("Nessun versamento registrato per l'anno selezionato.").classes("text-sm").style("color: var(--txt-mid);")
        return

    df_inv["Mese"] = df_inv["Data"].dt.month.map(MONTH_SHORT)
    det = df_inv["Dettaglio"].astype(str).str.upper().str.strip()
    mask_pac   = det.str.contains("PAC", na=False)
    mask_fondo = det.str.contains("FONDO|PENSION", na=False, regex=True)
    df_inv = df_inv[mask_pac | mask_fondo].copy()

    if df_inv.empty:
        ui.label("Nessun versamento PAC/Fondo trovato per l'anno.").classes("text-sm").style("color: var(--txt-mid);")
        return

    df_inv["Dettaglio"] = det.loc[df_inv.index].apply(
        lambda x: "PAC" if "PAC" in x else "FONDO PENSIONE"
    )
    grouped = df_inv.groupby(["Mese", "Dettaglio"])["Importo"].sum().reset_index()

    fig = px.bar(
        grouped, x="Mese", y="Importo", color="Dettaglio",
        barmode="group", color_discrete_map={"PAC": "#34d399", "FONDO PENSIONE": "#f472b6"},
    )
    fig.update_layout(bargap=0.20)
    fig.update_yaxes(tickprefix="€ ", tickformat=",.0f")
    style_fig(fig, height=300, show_legend=True)
    ui.plotly(fig).classes("w-full")