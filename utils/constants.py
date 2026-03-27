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
    BG          = "#07090F"
    BG_SURF     = "#0c1120"
    BG_CARD     = "#0c1120"
    BG_FORM     = "#0F1628"
    BG_INP      = "#090E1B"

    ACCENT      = "#4f8ef0"
    ACCENT_LT   = "#82b4f7"

    GREEN       = "#10d98a"
    GREEN_BRIGHT = "#5ce488"
    RED         = "#f26a6a"
    RED_BRIGHT  = "#fa598e"
    AMBER       = "#f5a623"
    VIOLET      = "#9b74f5"

    TEXT        = "#dde6f5"
    TEXT_MID    = "#5a6f8c"
    TEXT_DIM    = "rgba(180,200,240,0.55)"

    BORDER      = "rgba(92,118,178,0.20)"
    BORDER_MD   = "rgba(112,143,215,0.34)"

    # Sequenza colori grafici categoriali
    SEQ = ["#facc15", "#60a5fa", "#34d399", "#fb7185", "#a78bfa", "#f472b6", "#22c55e"]

    # Colori per categoria budget
    BUDGET_COLORS: dict[str, tuple[str, str]] = {
        "NECESSITÀ":    ("#4f8ef0", "#1d3a6e"),
        "SVAGO":        ("#f472b6", "#6d2040"),
        "INVESTIMENTI": ("#10d98a", "#0a4a36"),
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