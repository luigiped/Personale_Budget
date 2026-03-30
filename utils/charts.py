"""
utils/charts.py
---------------
Helper per la stilizzazione dei grafici Plotly — framework agnostic.

Restituisce sempre oggetti `plotly.graph_objects.Figure` già stilizzati,
pronti per essere renderizzati da Streamlit (`st.plotly_chart`) o
NiceGUI (`ui.plotly`).
"""

import plotly.graph_objects as go
from utils.constants import Colors, FONT_SANS, FONT_MONO, PLOTLY_CONFIG, MONTH_SHORT
 
# Ordine canonico mesi Gen→Dic
MONTH_ORDER = list(MONTH_SHORT.values())
 
MONTH_ORDER_Y_REVERSED = list(reversed(MONTH_ORDER))  # Dic→Gen (Plotly li mostrerà al contrario = Gen in alto)
 
 
def style_fig(fig, title=None, height=300, show_legend=True):
    layout_kwargs = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT_SANS, color=Colors.TEXT, size=12),
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="left", x=0,
            font=dict(size=11, color=Colors.TEXT),
            bgcolor="rgba(0,0,0,0)",
        ),
        height=height,
        xaxis_title=None,
        yaxis_title=None,
        showlegend=show_legend,
        legend_title_text="",
        separators=",.",
        autosize=True,
        uniformtext=dict(mode="hide", minsize=8),
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
        tickfont=dict(size=11, color=Colors.TEXT, family=FONT_SANS),
        title_font=dict(color=Colors.TEXT),
        linecolor="rgba(92,118,178,0.25)",
    )
    fig.update_yaxes(
        showgrid=False,
        gridcolor="rgba(79,142,240,0.08)",
        zeroline=False,
        tickfont=dict(size=11, color=Colors.TEXT, family=FONT_SANS),
        title_font=dict(color=Colors.TEXT),
        linecolor="rgba(92,118,178,0.25)",
    )
    return fig
 
 
def apply_month_order_x(fig):
    """Asse X categorico con mesi Gen→Dic da sinistra a destra."""
    fig.update_xaxes(categoryorder="array", categoryarray=MONTH_ORDER)
    return fig
 
 
def apply_month_order_y(fig):
    """
    Asse Y categorico con Gen in ALTO e Dic in basso
    (grafici a barre orizzontali).
    Plotly con categoryorder='array' mette il primo elemento IN BASSO,
    quindi passiamo l'array rovesciato (Dic→Gen) così Plotly lo mostrerà
    con Gen in cima.
    """
    fig.update_yaxes(
        categoryorder="array",
        categoryarray=MONTH_ORDER_Y_REVERSED,
    )
    return fig
 
 
def kpi_card_html(label: str, value: str, color: str, glow_color: str) -> str:
    return (
        f"<div class='kpi-card' style='box-shadow:0 4px 24px rgba(0,0,0,0.4),0 0 28px {glow_color};'>"
        f"<div class='kpi-label'>{label}</div>"
        f"<div class='kpi-value' style='color:{color};text-shadow:0 0 18px {glow_color};'>{value}</div>"
        f"<div class='kpi-bar' style='background:linear-gradient(90deg,{color}80,transparent);'></div>"
        f"</div>"
    )

def asset_card_html(label: str, value: str, perc: str, color: str, glow_color: str) -> str:
    return (
        f"<div style='background: #0c1120; border: 1px solid #1e293b; border-radius: 12px; padding: 15px; text-align: center; box-shadow: 0 0 20px {glow_color};'>"
        f"<div style='color: #94a3b8; font-size: 0.7rem; text-transform: uppercase;'>{label}</div>"
        f"<div style='color: {color}; font-size: 1.5rem; font-weight: bold; margin: 5px 0;'>{value}</div>"
        f"<div style='display: inline-block; background: rgba(34, 197, 94, 0.2); color: #22c55e; padding: 2px 10px; border-radius: 15px; font-size: 0.8rem; font-weight: bold;'>{perc}</div>"
        f"</div>"
    )
 
 
KPI_DEFINITIONS = {
    "saldo":     ("Saldo Disponibile", Colors.GREEN_BRIGHT, "rgba(92,228,136,0.18)"),
    "uscite":    ("Uscite Mese",       Colors.RED_BRIGHT,   "rgba(250,89,142,0.18)"),
    "risparmio": ("Risparmio Mese",    Colors.GREEN_BRIGHT, "rgba(92,228,136,0.18)"),
    "tasso":     ("Tasso Risparmio",   Colors.VIOLET,       "rgba(155,127,232,0.18)"),
}