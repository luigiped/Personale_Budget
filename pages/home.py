"""
pages/home.py
-------------
Pagina HOME — Personal Budget Dashboard NiceGUI.

Contenuto:
  - Grafico budget 50/30/20 (barre orizzontali stacked per mese)
  - Dettaglio spese per categoria/dettaglio del mese selezionato
  - Calendario spese ricorrenti con chip stato
  - Alert scadenze prossime
"""

from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from nicegui import ui

import Database as db
import logiche as log
from utils.constants import Colors, MONTH_SHORT, PERCENTUALI_BUDGET, PLOTLY_CONFIG
from utils.formatters import eur0, eur2
from utils.charts import style_fig
from utils.html_tables import render_calendario_html


def render(user_email: str, anno_sel: int, mese_sel: int, settings: dict, data: dict) -> None:
    """Entry point — chiamata da main.py."""
    from main import s_num, s_num_candidates

    df_mov = data["df_mov"]
    df_fin = data["df_fin"]

    saldo_iniziale = s_num_candidates(
        settings,
        [f"saldo_iniziale_{anno_sel}", f"saldo iniziale_{anno_sel}"],
        0.0,
    )
    budget_base = s_num(settings, "budget_mensile_base", 1600.0)

    mask_mese = (df_mov["Data"].dt.month == mese_sel) & (df_mov["Data"].dt.year == anno_sel)
    df_mese   = df_mov[mask_mese].copy()

    # ── Titolo sezione ──
    ui.html("<div class='section-title'>HOME</div>")

    # ── Riga 1: Budget + Dettaglio spese ──
    with ui.grid(columns=2).classes("w-full gap-4"):

        # Budget 50/30/20
        with ui.card().classes("col-span-1").style(
            "background: var(--bg-card); border: 1px solid var(--bdr); border-radius: 12px; padding: 16px;"
        ):
            ui.html("<div class='panel-title'>📊 Budget di spesa (50/30/20)</div>")
            df_budget = log.budget_spese_annuale(df_mov, anno_sel, budget_base)
            if not df_budget.empty:
                _render_budget_chart(df_budget, budget_base)
            else:
                ui.label("Imposta 'budget_mensile_base' nelle impostazioni rapide.").classes("text-sm").style("color: var(--txt-mid);")

        # Dettaglio spese mese
        with ui.card().classes("col-span-1").style(
            "background: var(--bg-card); border: 1px solid var(--bdr); border-radius: 12px; padding: 16px;"
        ):
            ui.html("<div class='panel-title'>📂 Dettaglio spese per categoria</div>")
            df_uscite = df_mese[df_mese["Tipo"] == "USCITA"].copy()
            det = log.dettaglio_spese(df_uscite)
            if not det.empty:
                _render_dettaglio_chart(det)
            else:
                ui.label("Nessuna spesa nel mese selezionato.").classes("text-sm").style("color: var(--txt-mid);")

    # ── Calendario scadenze ──
    ui.html("<div class='panel-title' style='margin-top:20px;'>📅 Calendario spese ricorrenti</div>")
    cal = _calcola_calendario(user_email, df_mov, df_fin, mese_sel, anno_sel)

    if cal is not None and not cal.empty:
        _render_calendario(cal, user_email, df_mov, df_fin, mese_sel, anno_sel)
    else:
        ui.label("Nessuna scadenza prevista per questo mese.").classes("text-sm").style("color: var(--txt-mid);")


# ---------------------------------------------------------------------------
# Grafico budget 50/30/20
# ---------------------------------------------------------------------------

def _render_budget_chart(df_budget: pd.DataFrame, budget_base: float) -> None:
    mesi_labels = list(MONTH_SHORT.values())
    fig = go.Figure()
    for cat in list(PERCENTUALI_BUDGET.keys()):
        df_cat   = df_budget[df_budget["Categoria"] == cat].set_index("Mese").reindex(mesi_labels)
        budget_c = df_cat["BudgetCategoria"].fillna(budget_base * PERCENTUALI_BUDGET[cat])
        speso    = df_cat["Speso"].fillna(0)
        residuo  = (budget_c - speso).clip(lower=0)
        spesa_ok = speso.where(speso <= budget_c, budget_c)
        extra    = (speso - budget_c).clip(lower=0)
        col, col_dark = Colors.BUDGET_COLORS[cat]

        fig.add_bar(x=residuo, y=mesi_labels, orientation="h", width=0.55,
            name=f"{cat} residuo", marker_color=col_dark, showlegend=False)
        fig.add_bar(x=spesa_ok, y=mesi_labels, orientation="h", width=0.55,
            name=cat, marker_color=col, showlegend=True)
        if extra.sum() > 0:
            fig.add_bar(x=extra, y=mesi_labels, orientation="h", width=0.55,
                name=f"{cat} extra", marker_color=Colors.RED, showlegend=False)

    fig.update_layout(barmode="stack", bargap=0.18)
    fig.update_xaxes(tickprefix="€ ", tickformat=".0f")
    style_fig(fig, height=420, show_legend=False)
    ui.plotly(fig).classes("w-full")


# ---------------------------------------------------------------------------
# Grafico dettaglio spese
# ---------------------------------------------------------------------------

def _render_dettaglio_chart(det: pd.DataFrame) -> None:
    det["Etichetta"] = det["Importo"].map(eur0)
    fig = px.bar(det, x="Dettaglio", y="Importo", color="Dettaglio",
        text="Etichetta", color_discrete_sequence=Colors.SEQ)
    fig.update_layout(showlegend=False)
    fig.update_xaxes(tickangle=-35)
    fig.update_traces(
        texttemplate="<b>%{text}</b>", textposition="auto",
        textfont=dict(size=14, color="#ffffff"), marker_cornerradius=6,
    )
    fig.update_yaxes(tickprefix="€ ", tickformat=",.0f")
    style_fig(fig, height=420, show_legend=False)
    ui.plotly(fig).classes("w-full")


# ---------------------------------------------------------------------------
# Calendario scadenze
# ---------------------------------------------------------------------------

def _calcola_calendario(user_email: str, df_mov: pd.DataFrame,
                         df_fin: pd.DataFrame, mese_ref: int, anno_ref: int):
    """Calcola il calendario scadenze per il mese selezionato."""
    df_ric = db.carica_spese_ricorrenti(user_email)
    if not df_ric.empty:
        df_ric = df_ric.rename(columns={
            "descrizione": "Descrizione", "importo": "Importo",
            "giorno_scadenza": "Giorno Scadenza", "frequenza_mesi": "Frequenza",
            "data_inizio": "Data Inizio", "data_fine": "Data Fine",
        })
    df_fin_cal = pd.DataFrame()
    if not df_fin.empty:
        df_fin_cal = df_fin.rename(columns={
            "nome": "Nome Finanziamento", "capitale_iniziale": "Capitale",
            "taeg": "TAEG", "durata_mesi": "Durata",
            "data_inizio": "Data Inizio", "giorno_scadenza": "Giorno Scadenza",
            "rate_pagate": "Rate Pagate",
        })
    return log.calcolo_spese_ricorrenti(df_ric, df_fin_cal, df_mov, mese_ref, anno_ref)


def _render_calendario(cal: pd.DataFrame, user_email: str, df_mov: pd.DataFrame,
                        df_fin: pd.DataFrame, mese_sel: int, anno_sel: int) -> None:
    """Rendering tabella calendario con filtro 'nascondi pagati'."""

    # Toggle nascondi pagati
    nascondi = {"value": False}
    toggle = ui.checkbox("Nascondi movimenti pagati", value=False)

    cal_container = ui.element("div").classes("w-full")

    def refresh_cal():
        cal_container.clear()
        with cal_container:
            cal_view = cal.copy()
            if toggle.value:
                cal_view = cal_view[~cal_view["Stato"].astype(str).str.contains("PAGATO", case=False, na=False)]

            tabella = cal_view.copy()
            if "Giorno Previsto" not in tabella.columns:
                tabella["Giorno Previsto"] = pd.to_datetime(tabella["Data"], errors="coerce").dt.day
            tabella["Giorno Previsto"] = pd.to_numeric(tabella["Giorno Previsto"], errors="coerce").fillna(0).astype(int)
            if "Data Fine Prevista" not in tabella.columns:
                tabella["Data Fine Prevista"] = None
            tabella["Data Fine Prevista"] = pd.to_datetime(tabella["Data Fine Prevista"], errors="coerce").dt.strftime("%d/%m/%Y").fillna("Nessuna")
            if "Frequenza" not in tabella.columns:
                tabella["Frequenza"] = "Mensile"
            tabella = tabella[["Spesa", "Importo", "Giorno Previsto", "Data Fine Prevista", "Stato", "Frequenza"]].rename(columns={"Spesa": "Spesa Prevista"})

            ui.html(render_calendario_html(tabella)).classes("w-full")

            # Alert scadenze nei prossimi 3 giorni
            oggi = date.today()
            window = [oggi + timedelta(days=i) for i in range(3)]
            coppie = sorted({(d.year, d.month) for d in window})
            frames_a = [_calcola_calendario(user_email, df_mov, df_fin, m, y) for y, m in coppie]
            frames_a = [f for f in frames_a if f is not None and not f.empty]
            if frames_a:
                base_alert = pd.concat(frames_a, ignore_index=True)
                alert_df = log.alert_scadenze_ricorrenti(base_alert, giorni_preavviso=2, oggi=oggi)
                alert_df = alert_df[alert_df["Giorni Alla Scadenza"] == 2]
                if not alert_df.empty:
                    ui.notify(f"⚠️ {len(alert_df)} spese ricorrenti in scadenza nei prossimi 2 giorni.", type="warning")

    toggle.on("update:model-value", lambda: refresh_cal())
    refresh_cal()