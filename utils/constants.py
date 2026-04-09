"""
utils/constants.py
------------------
Costanti condivise tra tutti i moduli dell'applicazione.

Nessuna dipendenza da framework UI. Importabile da logiche.py,
"""

# ---------------------------------------------------------------------------
# Tipi movimento (valori canonici nel DB)
# ---------------------------------------------------------------------------
TIPO_ENTRATA = "ENTRATA"
TIPO_USCITA  = "USCITA"

# ---------------------------------------------------------------------------
# Struttura categorie → dettagli (usata nel form registrazione e in logiche.py)
# ---------------------------------------------------------------------------
STRUTTURA_CATEGORIE: dict[str, list[str]] = {
    "NECESSITÀ": [
        "Affitto",
        "Mutuo",
        "Auto",
        "Moto",
        "Bollette (Luce/Gas/Internet)",
        "Trasporti/Benzina",
        "Salute",
        "Assicurazioni",
        "Imposta di bollo",
    ],
    "SVAGO": [
        "Ristoranti/Bar",
        "Viaggi/Hotel",
        "Gite fuori porta",
        "Abbonamenti (Netflix, ecc.)",
        "Shopping Personale",
        "Regali",
        "Palestra",
        "Altro",
        "Carta di credito",
    ],
    "INVESTIMENTI": [
        "PAC",
        "Fondo Pensione",
    ],
    "ENTRATE": [
        "Stipendio",
        "Extra",
    ],
}

# Percentuali budget 50/30/20
PERCENTUALI_BUDGET: dict[str, float] = {
    "NECESSITÀ":    0.50,
    "SVAGO":        0.30,
    "INVESTIMENTI": 0.20,
}

# ---------------------------------------------------------------------------
# Mesi
# ---------------------------------------------------------------------------
MONTH_NAMES: dict[int, str] = {
    1: "GENNAIO",   2: "FEBBRAIO",  3: "MARZO",
    4: "APRILE",    5: "MAGGIO",    6: "GIUGNO",
    7: "LUGLIO",    8: "AGOSTO",    9: "SETTEMBRE",
    10: "OTTOBRE", 11: "NOVEMBRE", 12: "DICEMBRE",
}

MONTH_SHORT: dict[int, str] = {
    1: "Gen",  2: "Feb",  3: "Mar",
    4: "Apr",  5: "Mag",  6: "Giu",
    7: "Lug",  8: "Ago",  9: "Set",
    10: "Ott", 11: "Nov", 12: "Dic",
}

# ---------------------------------------------------------------------------
# Frequenze spese ricorrenti
# ---------------------------------------------------------------------------
FREQ_OPTIONS: dict[str, int] = {
    "Mensile":        1,
    "Bimestrale":     2,
    "Trimestrale":    3,
    "Quadrimestrale": 4,
    "Semestrale":     6,
    "Annuale":        12,
}

FREQ_MAP: dict[int, str] = {v: k for k, v in FREQ_OPTIONS.items()}

# ---------------------------------------------------------------------------
# Colori tema dark indigo (usati dai grafici Plotly e dai componenti HTML)
# ---------------------------------------------------------------------------
class Colors:
    # ── Sfondi ───────────────────────────────────────────────────────────────
    BG          = "#06010f"
    BG_SURF     = "rgba(255,255,255,0.05)"
    BG_CARD     = "rgba(255,255,255,0.06)"
    BG_FORM     = "rgba(255,255,255,0.04)"
    BG_INP      = "rgba(139,92,246,0.10)"

    # ── Accenti aurora ───────────────────────────────────────────────────────
    ACCENT      = "#7c3aed"
    ACCENT_LT   = "#c4b5fd"

    # ── Semantici ────────────────────────────────────────────────────────────
    GREEN        = "#10d98a"
    GREEN_BRIGHT = "#5ce488"
    RED          = "#f26a6a"
    RED_BRIGHT   = "#fb7185"
    AMBER        = "#f5a623"
    VIOLET       = "#a78bfa"

    # ── Testo ────────────────────────────────────────────────────────────────
    TEXT        = "#f0e8ff"
    TEXT_MID    = "rgba(220,200,255,0.55)"
    TEXT_DIM    = "rgba(200,180,255,0.35)"

    # ── Bordi ────────────────────────────────────────────────────────────────
    BORDER      = "rgba(255,255,255,0.10)"
    BORDER_MD   = "rgba(139,92,246,0.38)"

    # ── Sequenza colori grafici categoriali (aurora palette) ─────────────────
    SEQ = ["#c4b5fd", "#f9a8d4", "#6ee7b7", "#fde68a", "#93c5fd", "#fb7185", "#34d399"]

    # ── Colori per categoria budget ──────────────────────────────────────────
    BUDGET_COLORS: dict[str, tuple[str, str]] = {
        "NECESSITÀ":    ("#818cf8", "rgba(99,102,241,0.22)"),
        "SVAGO":        ("#f472b6", "rgba(236,72,153,0.22)"),
        "INVESTIMENTI": ("#34d399", "rgba(52,211,153,0.22)"),
    }

# ---------------------------------------------------------------------------
# Configurazione Plotly
# ---------------------------------------------------------------------------
PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}

# ---------------------------------------------------------------------------
# Font
# ---------------------------------------------------------------------------
FONT_SANS = "'Plus Jakarta Sans', sans-serif"
FONT_MONO = "'JetBrains Mono', monospace"