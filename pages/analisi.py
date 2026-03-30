"""
pages/analisi.py
----------------
Tab ANALISI — Personal Budget Dashboard.

Contenuto:
  - Grafico obiettivo risparmio (confronto anno precedente vs corrente)
  - Andamento entrate mensili (barre verticali)
  - Previsione saldo (area chart con regressione lineare)
"""

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import logiche as log
from utils.constants import Colors, PLOTLY_CONFIG
from utils.formatters import eur0
from utils.charts import style_fig


def render(ctx: dict) -> None:
    anno_sel    = ctx["anno_sel"]
    mese_sel    = ctx["mese_sel"]
    df_mov      = ctx["df_mov"]
    prev_year   = ctx["prev_year"]
    risp_prev   = ctx["risp_prev"]
    target_perc = ctx["target_perc"]
    saldo_iniz  = ctx["saldo_iniziale"]

    st.markdown("<div class='section-title'>ANALISI</div>", unsafe_allow_html=True)

    df_anno = df_mov[df_mov["Data"].dt.year == anno_sel].copy()

    c1, c2 = st.columns([1, 1], gap="large")

    # ── Obiettivo risparmio ───────────────────────────────────────────────────
    with c1:
        st.markdown("<div class='panel-title'>🎯 Obiettivo risparmio</div>", unsafe_allow_html=True)

        entrate_a = df_anno[df_anno["Tipo"] == "ENTRATA"]["Importo"].sum()
        uscite_a  = df_anno[df_anno["Tipo"] == "USCITA"]["Importo"].abs().sum()
        risp_corr = entrate_a - uscite_a

        if risp_prev > 0:
            accumulo = max(risp_corr, 0)
            target   = risp_prev * (1 + target_perc / 100)
            mancante = max(target - accumulo, 0)

            sign = "+" if target_perc >= 0 else ""
            st.markdown(
                f"<div style='text-align:right;margin-bottom:-6px;'>"
                f"<span style='background:#f5a623;color:#07090f;font-weight:800;"
                f"font-size:0.88rem;padding:5px 14px;border-radius:8px;'>"
                f"Target {sign}{target_perc:.0f}%</span></div>",
                unsafe_allow_html=True,
            )

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
                    x=[mancante], 
                    base=[accumulo], 
                    y=[0], orientation="h", width=0.46,
                    name="Mancante al target",
                    marker_color="rgba(242,106,106,0.30)", 
                    marker_cornerradius=6,
                    hoverinfo="skip",
                    text=[eur0(mancante)],
                    texttemplate="<b>%{text}</b>",
                    textposition="auto", 
                    insidetextanchor="middle",
                    textfont=dict(color=Colors.RED, size=11),
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
                yaxis=dict(
                    tickvals=[1, 0], ticktext=[str(prev_year), str(anno_sel)],
                    range=[-0.6, 1.6],
                    tickfont=dict(color=Colors.TEXT, size=12),
                ),
                xaxis=dict(tickprefix="€ ", tickformat=",.0f"),
                margin=dict(l=50, r=80, t=40, b=30),
            )
            style_fig(fig, height=280, show_legend=True)
            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
        else:
            st.info(f"Imposta il risparmio dell'anno precedente ({prev_year}) nelle impostazioni rapide.")

    # ── Andamento entrate mensili ─────────────────────────────────────────────
    with c2:
        st.markdown("<div class='panel-title'>📈 Andamento entrate</div>", unsafe_allow_html=True)
        entrate = log.analizza_entrate(df_mov, anno_sel)
        if not entrate.empty:
            vals = entrate["Importo"].tolist()
            fig  = go.Figure()
            fig.add_bar(
                x=entrate["Mese"], y=vals,
                marker_color=Colors.GREEN, marker_cornerradius=6,
                text=[eur0(v) if v > 0 else "" for v in vals],
                texttemplate="<b>%{text}</b>", textposition="auto",
                insidetextanchor="middle",
                textfont=dict(color="#ffffff", size=11),
            )
            fig.update_layout(bargap=0.30)
            fig.update_yaxes(tickprefix="€ ", tickformat=",.0f", range=[0, max(vals, default=0) * 1.8])
            style_fig(fig, height=300, show_legend=False)
            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
        else:
            st.info("Nessuna entrata disponibile per l'anno selezionato.")

    # ── Previsione saldo ──────────────────────────────────────────────────────
    st.markdown("<div class='panel-title'>🔮 Previsione saldo</div>", unsafe_allow_html=True)
    df_prev = log.previsione_saldo(
        df_mov, anno_sel, saldo_iniziale=saldo_iniz, mese_riferimento=mese_sel
    )
    if not df_prev.empty:
        fig = px.area(
            df_prev, x="Mese", y="Saldo", color="Tipo",
            color_discrete_sequence=["#4f8ef0", "#f5a623"],
        )
        fig.update_yaxes(tickprefix="€ ", tickformat=",.0f")
        style_fig(fig, height=320, show_legend=True)
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
    else:
        st.info("Dati insufficienti per la previsione saldo.")