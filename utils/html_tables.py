"""
utils/html_tables.py
--------------------
Funzioni per generare tabelle HTML custom stilizzate.
Framework agnostic — restituisce sempre stringhe HTML pure.

Usato sia da Streamlit (st.markdown(..., unsafe_allow_html=True))
che da NiceGUI (ui.html(...)).
"""

from html import escape
import pandas as pd

from utils.formatters import format_eur, chip_stato_html, chip_freq_html, row_bg_stato, chip_html
from utils.constants import Colors, FONT_MONO, FONT_SANS


# ---------------------------------------------------------------------------
# Primitivi HTML tabella
# ---------------------------------------------------------------------------

def _th(label: str, align: str = "left") -> str:
    return f"<th style='text-align:{align};'>{escape(str(label))}</th>"


def _td(
    content: str,
    align: str = "left",
    color: str = Colors.TEXT,
    mono: bool = False,
    weight: int = 400,
    nowrap: bool = True,
    title: str | None = None,
) -> str:
    font = (
        f"font-family:{FONT_MONO};font-size:0.78rem;"
        if mono
        else f"font-family:{FONT_SANS};font-size:0.875rem;"
    )
    white = "white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" if nowrap else "white-space:normal;"
    title_attr = f" title='{escape(str(title))}'" if title else ""
    return (
        f"<td style='text-align:{align};color:{color};"
        f"font-weight:{weight};{font}{white}'{title_attr}>{content}</td>"
    )


def _tr(cells: list[str], style: str = "") -> str:
    style_attr = f" style='{style}'" if style else ""
    return f"<tr{style_attr}>" + "".join(cells) + "</tr>"

def _colgroup(widths: list[float]) -> str:
    total = float(sum(widths) or 1)
    return "".join(
        f"<col style='width:{(w / total) * 100:.4f}%;'>"
        for w in widths
    )


def scroll_table(
    title: str,
    right_html: str,
    columns: list[tuple[str, str]],   # [(label, align), ...]
    widths: list[float],
    rows_html: list[str],
    height_px: int = 320,
    empty_message: str = "Nessun dato disponibile.",
) -> str:
    """
    Tabella scrollabile con header fisso, barra titolo e corpo scrollabile.
    Ritorna HTML puro — da usare con st.markdown o ui.html.
    """
    if not rows_html:
        rows_html = [
            f"<tr><td class='reg-html-empty' colspan='{len(columns)}'>"
            f"{escape(empty_message)}</td></tr>"
        ]
    headers = "".join(_th(label, align) for label, align in columns)
    return f"""
<div class="reg-html-shell">
  <div class="reg-html-bar">
    <span class="reg-html-bar-title">{escape(str(title))}</span>
    <span class="reg-html-bar-value">{right_html}</span>
  </div>
  <div class="reg-html-scroll" style="max-height:{int(height_px)}px;">
    <table class="reg-html-table">
      <colgroup>{_colgroup(widths)}</colgroup>
      <thead><tr>{headers}</tr></thead>
      <tbody>{''.join(rows_html)}</tbody>
    </table>
  </div>
</div>
"""


# ---------------------------------------------------------------------------
# Tabella calendario scadenze
# ---------------------------------------------------------------------------

def render_calendario_html(df: pd.DataFrame) -> str:
    """
    Renderizza il calendario spese ricorrenti come tabella HTML stilizzata.
    Accetta il DataFrame prodotto da logiche.calcolo_spese_ricorrenti.
    """
    if df is None or df.empty:
        return f"<p style='color:{Colors.TEXT_MID};font-size:0.82rem;'>Nessuna spesa prevista.</p>"

    cols = ["Spesa Prevista", "Importo", "Giorno Previsto", "Data Fine Prevista", "Stato", "Frequenza"]

    header_cells = "".join(
        f"<th style='padding:8px 13px;font-size:0.60rem;font-weight:700;"
        f"letter-spacing:1px;text-transform:uppercase;color:{Colors.TEXT_MID};"
        f"text-align:left;background:rgba(0,0,0,0.18);"
        f"border-bottom:1px solid rgba(139,92,246,0.18);white-space:nowrap;'>{c}</th>"
        for c in cols
    )

    rows_html = ""
    for _, row in df.iterrows():
        stato_val = str(row.get("Stato", ""))
        bg = row_bg_stato(stato_val)
        importo_fmt = format_eur(row.get("Importo", 0), decimals=2)
        giorno = int(row.get("Giorno Previsto", 0))
        freq_str = str(row.get("Frequenza", "Mensile"))

        cells = [
            f"<td style='padding:10px 13px;font-size:0.82rem;color:{Colors.TEXT};'>"
            f"{escape(str(row.get('Spesa Prevista', '')))}</td>",

            f"<td style='padding:10px 13px;font-family:{FONT_MONO};"
            f"font-size:0.82rem;color:{Colors.RED};'>{importo_fmt}</td>",

            f"<td style='padding:10px 13px;font-family:{FONT_MONO};"
            f"font-size:0.82rem;color:{Colors.TEXT_MID};'>{giorno}</td>",

            f"<td style='padding:10px 13px;font-size:0.82rem;color:{Colors.TEXT_MID};'>"
            f"{escape(str(row.get('Data Fine Prevista', '')))}</td>",

            f"<td style='padding:10px 13px;'>{chip_stato_html(stato_val)}</td>",

            f"<td style='padding:10px 13px;'>{chip_freq_html(freq_str)}</td>",
        ]
        rows_html += (
            f"<tr style='{bg}border-bottom:1px solid rgba(139,92,246,0.06);'>"
            + "".join(cells) + "</tr>"
        )

    totale = format_eur(df["Importo"].sum(), decimals=2)
    n = df.shape[0]

    return f"""
<div style="border:1px solid rgba(139,92,246,0.20);border-radius:12px;overflow:hidden;margin-top:4px;">
  <div style="display:flex;align-items:center;justify-content:space-between;
              padding:9px 14px;background:rgba(139,92,246,0.07);
              border-bottom:1px solid rgba(139,92,246,0.18);">
    <span style="font-size:0.68rem;font-weight:700;letter-spacing:1.2px;
                 text-transform:uppercase;color:{Colors.TEXT_MID};">
      Spese pianificate — {n} voci
    </span>
    <span style="font-family:{FONT_MONO};font-size:0.82rem;color:{Colors.ACCENT_LT};">
      Totale mese: {totale}
    </span>
  </div>
  <div style="overflow-x:auto;">
    <table style="width:100%;border-collapse:collapse;">
      <thead><tr>{header_cells}</tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
</div>
"""


# ---------------------------------------------------------------------------
# Tabella registro movimenti
# ---------------------------------------------------------------------------

FREQ_STYLE: dict[str, tuple[str, str, str]] = {
    "Mensile":    ("#c4b5fd", "rgba(139,92,246,0.12)", "rgba(139,92,246,0.30)"),
    "Annuale":    ("#f5a623", "rgba(245,166,35,0.12)", "rgba(245,166,35,0.28)"),
    "Semestrale": ("#a78bfa", "rgba(167,139,250,0.12)", "rgba(167,139,250,0.28)"),
}
_DEFAULT_FREQ_STYLE = ("#c4b5fd", "rgba(139,92,246,0.12)", "rgba(139,92,246,0.30)")


def render_ricorrenti_rows(df: pd.DataFrame, freq_map: dict[int, str]) -> list[str]:
    """
    Genera le righe HTML per la tabella delle spese ricorrenti nel tab Registro.
    Restituisce lista di stringhe <tr>...</tr>.
    """
    rows = []
    for _, row in df.iterrows():
        freq_n = int(row.get("frequenza_mesi", 1))
        freq_lbl = freq_map.get(freq_n, f"{freq_n}m")
        fc, fbg, fbd = FREQ_STYLE.get(freq_lbl, _DEFAULT_FREQ_STYLE)

        fine_val = row.get("data_fine")
        fine_str = str(fine_val)[:10] if (fine_val and str(fine_val) not in ["None", "NaT", ""]) else "—"
        importo_it = format_eur(float(row.get("importo", 0)), decimals=2)
        desc_txt = str(row["descrizione"])

        rows.append(_tr([
            _td(escape(str(row["id"])),    color=Colors.TEXT_MID, mono=True),
            _td(escape(desc_txt),          color=Colors.TEXT,     weight=500, title=desc_txt),
            _td(importo_it,                color=Colors.RED,      mono=True,  weight=600),
            _td(chip_html(freq_lbl, fc, fbg, fbd), nowrap=False),
            _td(str(int(row.get("giorno_scadenza", 0))), color=Colors.TEXT_MID, mono=True, align="center"),
            _td(str(row.get("data_inizio", ""))[:10],   color=Colors.TEXT_MID, mono=True, align="center"),
            _td(fine_str,                               color=Colors.TEXT_MID, mono=True, align="center"),
        ]))
    return rows