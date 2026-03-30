"""
pages/home.py
-------------
Tab HOME — Personal Budget Dashboard.

Contenuto:
  - Grafico budget 50/30/20 (barre orizzontali stacked, Gen in alto)
  - Dettaglio spese per dettaglio/categoria del mese selezionato
  - Calendario spese ricorrenti con chip stato
  - Alert scadenze prossime
"""

from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import logiche as log
from utils.constants import Colors, MONTH_SHORT, PERCENTUALI_BUDGET, PLOTLY_CONFIG
from utils.formatters import eur0
from utils.charts import style_fig
from utils.html_tables import render_calendario_html


def render(ctx: dict) -> None:
    anno_sel          = ctx["anno_sel"]
    mese_sel          = ctx["mese_sel"]
    df_mov            = ctx["df_mov"]
    df_budget         = ctx["df_budget"]
    budget_base       = ctx["budget_base"]
    calcolo_scadenze  = ctx["calcolo_scadenze"]

    st.markdown("<div class='section-title'>HOME</div>", unsafe_allow_html=True)

    mesi_labels = list(MONTH_SHORT.values())   # Gen→Dic
    mask_mese   = (df_mov["Data"].dt.month == mese_sel) & (df_mov["Data"].dt.year == anno_sel)
    df_mese     = df_mov[mask_mese].copy()

    c1, c2 = st.columns([1.35, 1.2])

    # ── Budget 50/30/20 ───────────────────────────────────────────────────────
    with c1:
        st.markdown("<div class='panel-title'>📊 Budget di spesa (50/30/20)</div>", unsafe_allow_html=True)
        if not df_budget.empty:
            fig_budget = go.Figure()
            for cat in list(PERCENTUALI_BUDGET.keys()):
                df_cat   = df_budget[df_budget["Categoria"] == cat].set_index("Mese").reindex(mesi_labels)
                budget_c = df_cat["BudgetCategoria"].fillna(budget_base * PERCENTUALI_BUDGET[cat])
                speso    = df_cat["Speso"].fillna(0)
                residuo  = (budget_c - speso).clip(lower=0)
                spesa_ok = speso.where(speso <= budget_c, budget_c)
                extra    = (speso - budget_c).clip(lower=0)
                col, col_dark = Colors.BUDGET_COLORS[cat]

                fig_budget.add_bar(
                    x=residuo, y=mesi_labels, orientation="h", width=0.55,
                    name=f"{cat} residuo", marker_color=col_dark, showlegend=False,
                )
                fig_budget.add_bar(
                    x=spesa_ok, y=mesi_labels, orientation="h", width=0.55,
                    name=cat, marker_color=col, showlegend=True,
                    text=[eur0(v) if v > 0 else "" for v in spesa_ok],
                    textfont=dict(color="#ffffff", size=10),
                    textposition="inside", insidetextanchor="middle",
                )
                if extra.sum() > 0:
                    fig_budget.add_bar(
                        x=extra, y=mesi_labels, orientation="h", width=0.55,
                        name=f"{cat} extra", marker_color=Colors.RED, showlegend=False,
                        text=[eur0(v) if v > 0 else "" for v in extra],
                        textfont=dict(color="#ffffff", size=10),
                        textposition="inside", insidetextanchor="middle",
                    )

            fig_budget.update_layout(
                barmode="stack",
                # autorange="reversed" mostra Gennaio in cima (asse Y categorico)
                yaxis=dict(autorange="reversed"),
            )
            fig_budget.update_xaxes(tickprefix="€ ", tickformat=".0f")
            style_fig(fig_budget, height=420, show_legend=True)
            st.plotly_chart(fig_budget, use_container_width=True, config=PLOTLY_CONFIG)
        else:
            st.info("Imposta 'budget_mensile_base' nelle impostazioni rapide.")

    # ── Dettaglio spese mese ──────────────────────────────────────────────────
    with c2:
        st.markdown("<div class='panel-title'>📂 Dettaglio spese per categoria</div>", unsafe_allow_html=True)
        df_uscite = df_mese[df_mese["Tipo"] == "USCITA"].copy()
        det = log.dettaglio_spese(df_uscite)
        if not det.empty:
            det["Etichetta"] = det["Importo"].map(eur0)
            fig_det = px.bar(
                det, x="Dettaglio", y="Importo", color="Dettaglio",
                text="Etichetta", color_discrete_sequence=Colors.SEQ,
            )
            fig_det.update_layout(showlegend=False)
            fig_det.update_xaxes(tickangle=-35)
            fig_det.update_traces(
                texttemplate="<b>%{text}</b>", textposition="auto",
                textfont=dict(size=14, color="#ffffff"),
                marker_cornerradius=6,
            )
            fig_det.update_yaxes(tickprefix="€ ", tickformat=",.0f")
            style_fig(fig_det, height=420, show_legend=False)
            st.plotly_chart(fig_det, use_container_width=True, config=PLOTLY_CONFIG)
        else:
            st.info("Nessuna spesa nel mese selezionato.")

    # ── Calendario scadenze ───────────────────────────────────────────────────
    st.markdown("<div class='panel-title'>📅 Calendario spese ricorrenti</div>", unsafe_allow_html=True)
    cal = calcolo_scadenze(mese_sel, anno_sel)

    if cal is not None and not cal.empty:
        nascondi = st.checkbox(
            "Nascondi movimenti pagati", value=False,
            key=f"hide_paid_{anno_sel}_{mese_sel}",
        )
        cal_view = cal.copy()
        if nascondi:
            cal_view = cal_view[~cal_view["Stato"].astype(str).str.contains("PAGATO", case=False, na=False)]

        tabella = cal_view.copy()
        if "Giorno Previsto" not in tabella.columns:
            tabella["Giorno Previsto"] = pd.to_datetime(tabella["Data"], errors="coerce").dt.day
        tabella["Giorno Previsto"] = (
            pd.to_numeric(tabella["Giorno Previsto"], errors="coerce").fillna(0).astype(int)
        )
        if "Data Fine Prevista" not in tabella.columns:
            tabella["Data Fine Prevista"] = None
        tabella["Data Fine Prevista"] = (
            pd.to_datetime(tabella["Data Fine Prevista"], errors="coerce")
            .dt.strftime("%d/%m/%Y").fillna("Nessuna")
        )
        if "Frequenza" not in tabella.columns:
            tabella["Frequenza"] = "Mensile"

        tabella = (
            tabella[["Spesa", "Importo", "Giorno Previsto", "Data Fine Prevista", "Stato", "Frequenza"]]
            .rename(columns={"Spesa": "Spesa Prevista"})
        )
        st.markdown(render_calendario_html(tabella), unsafe_allow_html=True)

        # Alert scadenze entro 2 giorni
        oggi    = date.today()
        window  = [oggi + timedelta(days=i) for i in range(3)]
        coppie  = sorted({(d.year, d.month) for d in window})
        frames  = [calcolo_scadenze(m, y) for y, m in coppie]
        frames  = [f for f in frames if f is not None and not f.empty]
        if frames:
            base_alert = pd.concat(frames, ignore_index=True)
            alert_df   = log.alert_scadenze_ricorrenti(base_alert, giorni_preavviso=2, oggi=oggi)
            alert_df   = alert_df[alert_df["Giorni Alla Scadenza"] == 2]
            if not alert_df.empty:
                st.warning(f"⚠️ Hai **{len(alert_df)}** spese ricorrenti in scadenza nei prossimi 2 giorni.")
    else:
        st.info("Nessuna scadenza prevista per questo mese.")