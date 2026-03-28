"""
pages/analisi.py
----------------
Pagina ANALISI — Personal Budget Dashboard.

Contenuto:
  - Grafico obiettivo risparmio (confronto anno precedente vs corrente)
  - Andamento entrate mensili
  - Previsione saldo (area chart con regressione lineare)
"""

import plotly.express as px
import plotly.graph_objects as go
from nicegui import ui

import logiche as log
from utils.constants import Colors, PLOTLY_CONFIG
from utils.formatters import eur0, eur2
from utils.charts import style_fig


def render(user_email: str, anno_sel: int, mese_sel: int, settings: dict, data: dict) -> None:
    """Entry point — chiamata da main.py."""
    from main import s_num, s_num_candidates

    df_mov = data["df_mov"]
    df_anno = df_mov[df_mov["Data"].dt.year == anno_sel].copy()
    prev_year = anno_sel - 1

    risp_prev      = s_num(settings, f"risparmio_precedente_{prev_year}", 0.0)
    target_perc    = s_num(settings, "obiettivo_risparmio_perc", 30.0)
    saldo_iniziale = s_num_candidates(
        settings,
        [f"saldo_iniziale_{anno_sel}", f"saldo iniziale_{anno_sel}"],
        0.0,
    )

    ui.html("<div class='section-title'>ANALISI</div>")

    # ── Riga 1: Obiettivo risparmio + Andamento entrate ──
    with ui.grid(columns=2).classes("w-full gap-4"):

        with ui.card().style(
            "background: var(--bg-card); border: 1px solid var(--bdr); border-radius: 12px; padding: 16px;"
        ):
            ui.html("<div class='panel-title'>🎯 Obiettivo risparmio</div>")
            _render_obiettivo(df_anno, anno_sel, prev_year, risp_prev, target_perc)

        with ui.card().style(
            "background: var(--bg-card); border: 1px solid var(--bdr); border-radius: 12px; padding: 16px;"
        ):
            ui.html("<div class='panel-title'>📈 Andamento entrate</div>")
            _render_entrate(df_mov, anno_sel)

    # ── Riga 2: Previsione saldo (full width) ──
    with ui.card().classes("w-full mt-4").style(
        "background: var(--bg-card); border: 1px solid var(--bdr); border-radius: 12px; padding: 16px;"
    ):
        ui.html("<div class='panel-title'>🔮 Previsione saldo</div>")
        _render_previsione(df_mov, anno_sel, saldo_iniziale, mese_sel)


# ---------------------------------------------------------------------------
# Grafico obiettivo risparmio
# ---------------------------------------------------------------------------

def _render_obiettivo(df_anno, anno_sel: int, prev_year: int,
                       risp_prev: float, target_perc: float) -> None:
    if risp_prev <= 0:
        ui.label(f"Imposta il risparmio dell'anno precedente ({prev_year}) nelle impostazioni rapide.").classes("text-sm").style("color: var(--txt-mid);")
        return

    entrate = df_anno[df_anno["Tipo"] == "ENTRATA"]["Importo"].sum()
    uscite  = df_anno[df_anno["Tipo"] == "USCITA"]["Importo"].abs().sum()
    risp_corrente = entrate - uscite
    target_curr   = risp_prev * (1 + target_perc / 100)

    accumulo  = max(risp_corrente, 0)
    mancante  = max(target_curr - accumulo, 0)

    fig = go.Figure()
    fig.add_bar(
        x=[risp_prev], y=[1], orientation="h", width=0.46,
        name=str(prev_year), marker_color=Colors.GREEN, marker_cornerradius=6,
        text=[eur0(risp_prev)], texttemplate="<b>%{text}</b>",
        textposition="inside", insidetextanchor="middle",
        textfont=dict(color="#07090f", size=13),
    )
    if mancante > 0:
        fig.add_bar(
            x=[accumulo + mancante], y=[0], orientation="h", width=0.46,
            name="Mancante al target", marker_color="rgba(242,106,106,0.30)",
            marker_cornerradius=6, hoverinfo="skip",
        )
    fig.add_bar(
        x=[accumulo], y=[0], orientation="h", width=0.46,
        name=f"{anno_sel} accumulato", marker_color=Colors.VIOLET, marker_cornerradius=6,
        text=[eur0(accumulo, signed=True)], texttemplate="<b>%{text}</b>",
        textposition="inside", insidetextanchor="middle",
        textfont=dict(color="#ffffff", size=13), showlegend=False,
    )
    fig.update_layout(
        barmode="overlay",
        yaxis=dict(tickvals=[1, 0], ticktext=[str(prev_year), str(anno_sel)], range=[-0.6, 1.6]),
        xaxis=dict(tickprefix="€ ", tickformat=",.0f"),
        margin=dict(l=50, r=80, t=40, b=30),
    )
    style_fig(fig, height=280, show_legend=True)
    ui.plotly(fig).classes("w-full")


# ---------------------------------------------------------------------------
# Grafico andamento entrate
# ---------------------------------------------------------------------------

def _render_entrate(df_mov, anno_sel: int) -> None:
    entrate = log.analizza_entrate(df_mov, anno_sel)
    if entrate.empty:
        ui.label("Nessuna entrata disponibile per l'anno selezionato.").classes("text-sm").style("color: var(--txt-mid);")
        return

    vals = entrate["Importo"].tolist()
    fig = go.Figure()
    fig.add_bar(
        x=entrate["Mese"], y=vals,
        marker_color=Colors.GREEN, marker_cornerradius=6,
        text=[eur0(v) for v in vals],
        texttemplate="<b>%{text}</b>", textposition="auto", insidetextanchor="middle",
    )
    fig.update_layout(bargap=0.30)
    fig.update_yaxes(tickprefix="€ ", tickformat=",.0f", range=[0, max(vals, default=0) * 1.8])
    style_fig(fig, height=300, show_legend=False)
    ui.plotly(fig).classes("w-full")


# ---------------------------------------------------------------------------
# Grafico previsione saldo
# ---------------------------------------------------------------------------

def _render_previsione(df_mov, anno_sel: int, saldo_iniziale: float, mese_sel: int) -> None:
    df_prev = log.previsione_saldo(
        df_mov, anno_sel,
        saldo_iniziale=saldo_iniziale,
        mese_riferimento=mese_sel,
    )
    if df_prev.empty:
        ui.label("Dati insufficienti per la previsione saldo.").classes("text-sm").style("color: var(--txt-mid);")
        return

    fig = px.area(
        df_prev, x="Mese", y="Saldo", color="Tipo",
        color_discrete_sequence=["#4f8ef0", "#f5a623"],
    )
    fig.update_yaxes(tickprefix="€ ", tickformat=",.0f")
    style_fig(fig, height=320, show_legend=True)
    ui.plotly(fig).classes("w-full")