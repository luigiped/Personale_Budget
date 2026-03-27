"""
utils/charts.py
---------------
Helper per la stilizzazione dei grafici Plotly — framework agnostic.

Restituisce sempre oggetti `plotly.graph_objects.Figure` già stilizzati,
pronti per essere renderizzati da Streamlit (`st.plotly_chart`) o
NiceGUI (`ui.plotly`).
"""

import plotly.graph_objects as go
from utils.constants import Colors, FONT_SANS, FONT_MONO, PLOTLY_CONFIG


def style_fig(
    fig: go.Figure,
    title: str | None = None,
    height: int = 300,
    show_legend: bool = True,
) -> go.Figure:
    """
    Applica il tema dark indigo a qualsiasi figura Plotly.
    Chiamare dopo aver aggiunto tutte le tracce.
    """
    layout_kwargs: dict = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT_SANS, color=Colors.TEXT, size=12),
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="left",   x=0,
            font=dict(size=11, color=Colors.TEXT_MID),
            bgcolor="rgba(0,0,0,0)",
        ),
        height=height,
        xaxis_title=None,
        yaxis_title=None,
        showlegend=show_legend,
        legend_title_text="",
        separators=",.",
    )

    if title:
        layout_kwargs["title"] = dict(
            text=title, x=0.02, xanchor="left",
            font=dict(size=13, color=Colors.TEXT, family=FONT_SANS),
        )
    else:
        layout_kwargs["title_text"] = ""

    fig.update_layout(**layout_kwargs)

    fig.update_xaxes(
        showgrid=True,
        gridcolor="rgba(79,142,240,0.08)",
        zeroline=False,
        tickfont=dict(size=11, color=Colors.TEXT_MID, family=FONT_SANS),
    )
    fig.update_yaxes(
        showgrid=False,
        gridcolor="rgba(79,142,240,0.08)",
        zeroline=False,
        tickfont=dict(size=11, color=Colors.TEXT_MID, family=FONT_SANS),
    )
    return fig


def kpi_card_html(label: str, value: str, color: str, glow_color: str) -> str:
    """
    Genera l'HTML per una KPI card con glow effect.
    Usata sia in Streamlit (st.markdown) che in NiceGUI (ui.html).
    """
    return f"""
<div style="
    background:{Colors.BG_CARD};
    border:1px solid {Colors.BORDER};
    border-radius:10px;
    padding:16px 20px;
    text-align:center;
    position:relative;
    overflow:hidden;
    box-shadow:0 4px 24px rgba(0,0,0,0.4), 0 0 28px {glow_color};
    transition:box-shadow .25s;
">
  <div style="
    font-size:0.80rem;font-weight:700;letter-spacing:1.4px;
    text-transform:uppercase;color:{Colors.TEXT_DIM};
    margin-bottom:8px;font-family:{FONT_SANS};
  ">{label}</div>
  <div style="
    font-family:{FONT_MONO};
    font-size:1.6rem;font-weight:700;
    color:{color};
    text-shadow:0 0 18px {glow_color};
    line-height:1.15;
  ">{value}</div>
  <div style="
    position:absolute;bottom:0;left:0;right:0;height:2px;
    background:linear-gradient(90deg,{color}80,transparent);
  "></div>
</div>"""


# Configurazione KPI card — (label, color, glow_color)
KPI_DEFINITIONS = {
    "saldo":    ("Saldo Disponibile", Colors.GREEN_BRIGHT,  "rgba(92,228,136,0.18)"),
    "uscite":   ("Uscite Mese",       Colors.RED_BRIGHT,    "rgba(250,89,142,0.18)"),
    "risparmio":("Risparmio Mese",    Colors.GREEN_BRIGHT,  "rgba(92,228,136,0.18)"),
    "tasso":    ("Tasso Risparmio",   Colors.VIOLET,        "rgba(155,127,232,0.18)"),
}