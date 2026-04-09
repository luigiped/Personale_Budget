"""
pages/patrimonio.py
-------------------
Tab PATRIMONIO — Personal Budget Dashboard.

Contenuto:
  - PAC (Piano di Accumulo Capitale): valore attuale, P&L, proiezione
  - Fondo Pensione: valore attuale, progress fiscale, proiezione
  - Composizione portafoglio (pie chart)
  - Versamenti PAC / Fondo dell'anno corrente
  - Variazione investimenti anno precedente vs attuale
"""

import pandas as pd
from datetime import date

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from utils.charts import style_fig
import logiche as log
from utils.constants import Colors, MONTH_SHORT, PLOTLY_CONFIG
from utils.formatters import eur2, hex_to_rgba, badge_html


def _fmt_k(v: float) -> str:
    """Formatta un valore in forma compatta per etichette grafico."""
    try:
        v = float(v)
        return f"€{v/1000:.1f}k" if abs(v) >= 1000 else f"€{v:.0f}"
    except Exception:
        return ""


def render(ctx: dict) -> None:
    anno_sel   = ctx["anno_sel"]
    df_mov     = ctx["df_mov"]
    s_num      = ctx["s_num"]
    s_txt      = ctx["s_txt"]
    s_num_c    = ctx["s_num_candidates"]

    pac_ticker = ctx["pac_ticker"]
    pac_quote  = ctx["pac_quote"]
    pac_cap    = ctx["pac_cap"]
    pac_vers   = ctx["pac_vers"]
    pac_rend   = ctx["pac_rend"]

    fondo_quote = ctx["fondo_quote"]
    fondo_cap   = ctx["fondo_cap"]
    fondo_vers  = ctx["fondo_vers"]
    fondo_quota = ctx["fondo_quota"]
    fondo_rend  = ctx["fondo_rend"]
    aliq_irpef  = ctx["aliq_irpef"]
    fondo_tfr   = ctx["fondo_tfr"]
    fondo_snap  = ctx["fondo_snap"]

    saldo_disp = ctx["saldo_disponibile"]
    saldo_rev  = s_num("Saldo_conto_secondario", 0.0)

    st.markdown("<div class='section-title'>PATRIMONIO</div>", unsafe_allow_html=True)

    valore_pac_attuale   = pac_cap
    valore_fondo_attuale = fondo_cap

    # ── PAC ───────────────────────────────────────────────────────────────────
    pac_title_col, pac_badge_col = st.columns([3, 2])
    with pac_title_col:
        st.markdown("<div class='panel-title'>📈 PAC — Piano di Accumulo</div>", unsafe_allow_html=True)
    pac_badge_slot = pac_badge_col.empty()

    if pac_ticker and pac_quote >= 0:
        res_pac = log.analisi_pac(
            ticker=pac_ticker, quote_base=pac_quote, capitale_base=pac_cap,
            versamento_mensile_proiezione=pac_vers,
            rendimento_annuo_stimato=pac_rend,
            df_transazioni=df_mov, anno_corrente=anno_sel,
        )
        s = res_pac["Sintesi"]
        valore_pac_attuale = s["Valore Attuale"]

        pac_badge_slot.markdown(
        f"""<div style="text-align:right">
            {badge_html(f"Ticker {pac_ticker} | {s['Quote_Totali']} Quote", 'badge-red')}
        </div>""",
        unsafe_allow_html=True,
        )

        vers_da_reg = res_pac.get("Versamento_Anno_Corrente", 0.0)
        st.markdown(
            f"<div style='font-size:0.82rem;color:var(--txt-mid);margin-bottom:14px;"
            f"background:rgba(16,217,138,0.06);border:1px solid rgba(16,217,138,0.15);"
            f"border-radius:8px;padding:8px 14px;'>"
            f"<span style='color:var(--green);font-weight:700;'>●</span> "
            f"Versamento mensile: <strong style='color:var(--txt);'>{eur2(pac_vers)}</strong>"
            f" &nbsp;|&nbsp; Rendimento stimato: <strong style='color:var(--green);'>{pac_rend:.2f}%</strong>"
            + (f" &nbsp;|&nbsp; Versato da registro ({anno_sel}): "
            f"<strong style='color:var(--acc-lt);'>{eur2(vers_da_reg)}</strong>"
            if vers_da_reg is not None else "")
            + "</div>",
            unsafe_allow_html=True,
        )

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Valore attuale",   eur2(s["Valore Attuale"]))
        k2.metric("Rendimento",       eur2(s["P&L"], signed=True), f"{s['P&L %']}%")
        k3.metric("Tasse plusvalenze", eur2(s["Imposte"]))
        k4.metric("Netto smobilizzo", eur2(s["Netto"]))

        df_pac  = res_pac["Grafico_Proiezione"]
        fig_pac = go.Figure()
        for name, color, fill in [
            ("Proiezione Stimata", "#34d399", "tozeroy"),
            ("Capitale Versato",   "#60a5fa", "tozeroy"),
            ("Valore Netto",       "#facc15", "none"),
        ]:
            _y = df_pac[name]
            _n = max(1, len(_y) // 12)
            _text = [_fmt_k(v) if i % _n == 0 else "" for i, v in enumerate(_y)]
            fig_pac.add_trace(go.Scatter(
                x=df_pac["Mese"], y=_y, name=name,
                mode="lines+text",
                line=dict(color=color, width=3 if name == "Proiezione Stimata" else 2),
                fill=fill, fillcolor=hex_to_rgba(color, 0.10),
                text=_text, textposition="top center",
                textfont=dict(size=9, color=color),
            ))
        style_fig(fig_pac, height=340, show_legend=True)
        st.plotly_chart(fig_pac, use_container_width=True, config=PLOTLY_CONFIG)
    else:
        pac_badge_slot.empty()
        st.info("Imposta 'Ticker' e 'Quote' nelle impostazioni rapide per visualizzare il PAC.")

    st.divider()

    # ── Fondo Pensione ────────────────────────────────────────────────────────
    st.markdown("<div class='panel-title'>🏦 Fondo Pensione</div>", unsafe_allow_html=True)

    if fondo_quota > 0 and fondo_quote > 0:
        _snap = pd.to_datetime(fondo_snap, errors="coerce").date() if fondo_snap else date.today()
        res_fondo = log.analisi_fondo_pensione(
            fondo_quota, fondo_quote, fondo_cap, fondo_vers, fondo_rend,
            df_mov, anno_sel, aliquota_irpef=aliq_irpef, anni=30,
            data_snapshot=_snap, tfr_versato_anno=fondo_tfr,
        )
        valore_fondo_attuale = res_fondo["Sintesi"]["Valore Attuale"]
        perc_fp = min(res_fondo["Avanzamento_Fiscale"]["Percentuale"] / 100, 1.0)

        f1, f2, f3 = st.columns(3)
        f1.metric("Valore attuale",  eur2(res_fondo["Sintesi"]["Valore Attuale"]))
        f2.metric("Quote possedute",
                  f"{res_fondo['Sintesi']['Quote Attuali']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        f3.metric("Rendimento", eur2(res_fondo["Sintesi"]["P&L"], signed=True), f"{res_fondo['Sintesi']['P&L %']}%")

        st.markdown(
            f"<div class='progress-wrap'><div class='progress-track'>"
            f"<div class='progress-fill' style='width:{perc_fp * 100:.1f}%'></div>"
            f"</div></div>",
            unsafe_allow_html=True,
        )

        df_fondo  = res_fondo["Grafico_Proiezione"].copy()
        fig_fondo = go.Figure()
        for name, color, fill in [
            ("Proiezione Teorica",     "#f472b6", "tozeroy"),
            ("Cap.Versato Cumu.",      "#60a5fa", "tozeroy"),
            ("Valore Attuale Linea",   "#facc15", "none"),
        ]:
            _y2 = df_fondo[name]
            _n2 = max(1, len(_y2) // 10)
            _text2 = [_fmt_k(v) if i % _n2 == 0 else "" for i, v in enumerate(_y2)]
            fig_fondo.add_trace(go.Scatter(
                x=df_fondo["Mese"], y=_y2, mode="lines+text",
                line=dict(color=color,
                          width=3 if "Teorica" in name else 2,
                          dash="dash" if "Linea" in name else "solid"),
                fill=fill, fillcolor=hex_to_rgba(color, 0.08),
                name=name.replace(" Linea", ""),
                text=_text2, textposition="top center",
                textfont=dict(size=9, color=color),
            ))
        style_fig(fig_fondo, height=380, show_legend=True)
        st.plotly_chart(fig_fondo, use_container_width=True, config=PLOTLY_CONFIG)
    else:
        st.info("Imposta valore quota e quote fondo nelle impostazioni rapide.")

    st.divider()

    # ── Composizione portafoglio + Versamenti ─────────────────────────────────
    r1, r2 = st.columns(2)
    with r1:
        st.markdown("<div class='panel-title'>🥧 Composizione portafoglio</div>", unsafe_allow_html=True)
        comp = log.composizione_portafoglio(
            float(saldo_disp), float(saldo_rev),
            valore_pac_attuale, valore_fondo_attuale,
        )
        if comp:
            fig_comp = px.pie(
                comp["Dettaglio"], names="Asset", values="Valore",
                hole=0.35, color_discrete_sequence=Colors.SEQ,
            )
            fig_comp.update_traces(textinfo="percent+label", textposition="inside")
            fig_comp.update_layout(showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
            style_fig(fig_comp, height=300, show_legend=False)
            st.plotly_chart(fig_comp, use_container_width=True, config=PLOTLY_CONFIG)

    with r2:
        st.markdown("<div class='panel-title'>💸 Versamenti PAC / Fondo</div>", unsafe_allow_html=True)
        df_inv = df_mov[
            (df_mov["Categoria"] == "INVESTIMENTI") &
            (df_mov["Tipo"] == "USCITA") &
            (df_mov["Data"].dt.year == anno_sel)
        ].copy()

        if not df_inv.empty:
            df_inv["Mese"] = df_inv["Data"].dt.month.map(MONTH_SHORT)
            det = df_inv["Dettaglio"].astype(str).str.upper().str.strip()
            mask_pac   = det.str.contains("PAC", na=False)
            mask_fondo = det.str.contains("FONDO|PENSION", na=False, regex=True)
            df_inv = df_inv[mask_pac | mask_fondo].copy()
            if not df_inv.empty:
                df_inv["Dettaglio"] = det.loc[df_inv.index].apply(
                    lambda x: "PAC" if "PAC" in x else "FONDO PENSIONE"
                )
                df_inv = (df_inv.groupby(["Mese", "Dettaglio"])["Importo"]
                          .sum().abs().reset_index())
                pivot = (df_inv.pivot_table(index="Mese", columns="Dettaglio", values="Importo", fill_value=0)
                         .reindex(list(MONTH_SHORT.values()), fill_value=0))
                fig_vers = go.Figure()
                for col in pivot.columns:
                    fig_vers.add_trace(go.Scatter(
                        x=list(MONTH_SHORT.values()), y=pivot[col],
                        mode="lines+markers", name=col.title(),
                        line=dict(shape="hvh", width=2), fill="tozeroy",
                    ))
                style_fig(fig_vers, height=300, show_legend=True)
                st.plotly_chart(fig_vers, use_container_width=True, config=PLOTLY_CONFIG)
            else:
                st.info("Nessun versamento PAC/Fondo trovato con i tag corretti.")
        else:
            st.info("Nessun versamento registrato per l'anno selezionato.")

    # ── Variazione investimenti anno precedente vs attuale ────────────────────
    st.divider()
    st.markdown(
        "<div class='panel-title'>📊 Variazione investimenti (anno precedente vs attuale)</div>",
        unsafe_allow_html=True,
    )
    prev_y = anno_sel - 1

    def _inv_totale_anno(df, anno):
        _d = df[
            (df["Categoria"] == "INVESTIMENTI") &
            (df["Tipo"] == "USCITA") &
            (df["Data"].dt.year == anno)
        ]
        return float(_d["Importo"].abs().sum()) if not _d.empty else 0.0

    inv_curr = _inv_totale_anno(df_mov, anno_sel)
    inv_prev = _inv_totale_anno(df_mov, prev_y)

    col_a, col_b = st.columns(2)
    col_a.metric(f"Investimenti {prev_y}", eur2(inv_prev))
    delta_inv = inv_curr - inv_prev
    col_b.metric(
        f"Investimenti {anno_sel}", eur2(inv_curr),
        delta=f"{'+' if delta_inv >= 0 else ''}{eur2(delta_inv)}",
        delta_color="normal",
    )
