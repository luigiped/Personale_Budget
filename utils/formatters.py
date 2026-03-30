"""
utils/formatters.py
-------------------
Funzioni di formattazione condivise — framework agnostic.
"""

from html import escape as _escape

# ---------------------------------------------------------------------------
# Valuta
# ---------------------------------------------------------------------------

def format_eur(value, decimals: int = 0, signed: bool = False) -> str:
    """
    Formatta un valore numerico come valuta EUR con separatori italiani.

    Esempi:
        format_eur(1234.5)         → "€ 1.234"
        format_eur(1234.5, 2)      → "€ 1.234,50"
        format_eur(-50, signed=True) → "-€ 50"
    """
    if value is None:
        return ""
    try:
        val = float(value)
    except (TypeError, ValueError):
        return ""

    sign = "-" if signed and val < 0 else ""
    val_abs = abs(val) if signed else val

    s = f"{val_abs:,.{decimals}f}"
    # Converti separatori: 1,234.50 → 1.234,50
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")

    if decimals == 0:
        s = s.split(",")[0]

    return f"{sign}€ {s}"

def eur0(value, signed: bool = False) -> str:
    """Valuta senza decimali: € 1.234"""
    return format_eur(value, decimals=0, signed=signed)


def eur2(value, signed: bool = False) -> str:
    """Valuta con due decimali: € 1.234,50"""
    return format_eur(value, decimals=2, signed=signed)


# ---------------------------------------------------------------------------
# Numeri
# ---------------------------------------------------------------------------

def fmt_num_it(value, decimals: int = 2) -> str:
    """Formatta un numero con separatori italiani senza simbolo €."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    s = f"{v:,.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_perc(value, decimals: int = 1) -> str:
    """Formatta una percentuale: 23.4 → '23,4%'"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    s = f"{v:.{decimals}f}".replace(".", ",")
    return f"{s}%"


# ---------------------------------------------------------------------------
# Colori
# ---------------------------------------------------------------------------

def hex_to_rgba(hex_color: str, alpha: float | None = None) -> str:
    """
    Converte un colore HEX (6 o 8 cifre) in una stringa rgba() per Plotly/CSS.

    - 6 cifre: usa alpha passato (default 0.1)
    - 8 cifre: usa l'alpha incorporato nell'ultima coppia di cifre
    """
    raw = str(hex_color or "").strip().lstrip("#")
    try:
        if len(raw) == 8:
            r, g, b = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
            a = round(int(raw[6:8], 16) / 255, 2) if alpha is None else alpha
            return f"rgba({r},{g},{b},{a})"
        if len(raw) == 6:
            r, g, b = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
            a = 0.1 if alpha is None else alpha
            return f"rgba({r},{g},{b},{a})"
    except Exception:
        pass
    fallback = 0.1 if alpha is None else alpha
    return f"rgba(255,255,255,{fallback})"


# ---------------------------------------------------------------------------
# HTML badge / chip (usati nel tab Registro e nel calendario)
# ---------------------------------------------------------------------------

def badge_html(text: str, variant: str = "") -> str:
    """
    Ritorna HTML per un badge inline.
    variant: '' | 'badge-green' | 'badge-red' | 'badge-blue' | 'badge-pink'
    """
    cls = f"badge {variant}".strip()
    return f"<span class='{cls}'>{_escape(str(text))}</span>"


def chip_html(
    label: str,
    color: str,
    bg: str,
    border: str,
    size: str = "0.72rem",
    padding: str = "3px 11px",
    weight: int = 700,
) -> str:
    """Chip/badge generico con colori custom."""
    return (
        f"<span class='reg-chip' "
        f"style='background:{bg};color:{color};"
        f"border:1px solid {border};font-size:{size};font-weight:{weight};"
        f"padding:{padding};'>"
        f"{_escape(str(label))}</span>"
    )


def chip_stato_html(stato: str) -> str:
    """Chip colorato per lo stato di una scadenza (Pagato / In scadenza / Da pagare)."""
    s = str(stato).upper()
    if "PAGATO" in s:
        return (
            "<span style='display:inline-flex;align-items:center;gap:4px;"
            "padding:3px 10px;border-radius:20px;font-size:0.72rem;font-weight:700;"
            "background:rgba(16,217,138,0.12);color:#10d98a;"
            "border:1px solid rgba(16,217,138,0.3);'>"
            "<span style='width:5px;height:5px;border-radius:50%;"
            "background:#10d98a;display:inline-block;'></span>"
            " ✓ Pagato</span>"
        )
    if "IN SCADENZA" in s:
        return (
            "<span style='display:inline-flex;align-items:center;gap:4px;"
            "padding:3px 10px;border-radius:20px;font-size:0.72rem;font-weight:700;"
            "background:rgba(245,166,35,0.12);color:#f5a623;"
            "border:1px solid rgba(245,166,35,0.3);'>"
            "<span style='width:5px;height:5px;border-radius:50%;"
            "background:#f5a623;display:inline-block;'></span>"
            " ⚠ In scadenza</span>"
        )
    return (
        "<span style='display:inline-flex;align-items:center;gap:4px;"
        "padding:3px 10px;border-radius:20px;font-size:0.72rem;font-weight:700;"
        "background:rgba(242,106,106,0.10);color:#f26a6a;"
        "border:1px solid rgba(242,106,106,0.25);'>"
        "<span style='width:5px;height:5px;border-radius:50%;"
        "background:#f26a6a;display:inline-block;'></span>"
        " Da pagare</span>"
    )


def chip_freq_html(freq_label: str) -> str:
    """Chip per la frequenza di una spesa ricorrente."""
    return (
        f"<span style='display:inline-flex;align-items:center;"
        f"padding:3px 9px;border-radius:20px;font-size:0.72rem;font-weight:600;"
        f"background:rgba(79,142,240,0.10);color:#82b4f7;"
        f"border:1px solid rgba(79,142,240,0.25);'>{_escape(freq_label)}</span>"
    )


def row_bg_stato(stato: str) -> str:
    """CSS inline per il background di una riga della tabella calendario."""
    s = str(stato).upper()
    if "PAGATO" in s:
        return "background:rgba(16,217,138,0.07);border-left:3px solid #10d98a;"
    if "IN SCADENZA" in s:
        return "background:rgba(245,166,35,0.07);border-left:3px solid #f5a623;"
    return "background:rgba(242,106,106,0.06);border-left:3px solid #f26a6a;"