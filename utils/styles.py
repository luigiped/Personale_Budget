"""
utils/styles.py
---------------
CSS del tema dark indigo, estratto da interfaccia.py.

Struttura:
  CSS_BASE        — variabili CSS, reset, layout base, sidebar, tipografia
  CSS_COMPONENTS  — KPI cards, tab, plotly, dataframe, form, bottoni, badge
  CSS_REGISTRO    — stili specifici del tab Registro (tabelle HTML scrollabili)
  CSS_TAB_METRICS — override metriche dentro i tab (Patrimonio, Analisi, ecc.)

  CSS_ALL         — tutto concatenato (comodità per chi vuole iniettare tutto in una volta)

Uso in Streamlit:
    from utils.styles import CSS_ALL
    st.markdown(f"<style>{CSS_ALL}</style>", unsafe_allow_html=True)

In NiceGUI il CSS verrà caricato tramite ui.add_css() o un file .css statico.
"""

CSS_BASE = """
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500&display=swap');

/* ── Keyframes globali ───────────────────────────────────────────────────── */
@keyframes aurora-shimmer {
    0%   { background-position:  200% center; }
    100% { background-position: -200% center; }
}
@keyframes aurora-float-a {
    0%,100% { transform: scale(1)    translate(0px,  0px);   }
    33%      { transform: scale(1.07) translate(20px,-25px);  }
    66%      { transform: scale(0.95) translate(-8px, 16px);  }
}
@keyframes aurora-float-b {
    0%,100% { transform: scale(1)    translate(0px, 0px);    }
    33%      { transform: scale(0.93) translate(-18px,22px);  }
    66%      { transform: scale(1.05) translate(14px,-12px);  }
}
@keyframes aurora-float-c {
    0%,100% { transform: scale(1)    translate(0px, 0px);   }
    50%      { transform: scale(1.10) translate(16px,10px);  }
}
@keyframes badge-breathe {
    0%,100% { opacity:1;    }
    50%      { opacity:0.45; }
}
@keyframes pulse-ring {
    0%   { box-shadow: 0 0 0 0   rgba(139,92,246,0.45); }
    70%  { box-shadow: 0 0 0 10px rgba(139,92,246,0.00); }
    100% { box-shadow: 0 0 0 0   rgba(139,92,246,0.00); }
}
@keyframes login-card-in {
    from { opacity:0; transform: translateY(28px) scale(0.97); }
    to   { opacity:1; transform: translateY(0)    scale(1);    }
}
@keyframes login-item-in {
    from { opacity:0; transform: translateY(10px); }
    to   { opacity:1; transform: translateY(0);    }
}

/* ── CSS Variables ───────────────────────────────────────────────────────── */
:root {
    --bg:          #06010f;
    --bg-surf:     rgba(255,255,255,0.05);
    --bg-card:     rgba(255,255,255,0.06);
    --bg-form:     rgba(255,255,255,0.04);
    --bg-inp:      rgba(139,92,246,0.10);
    --table-bg:    rgba(255,255,255,0.04);
    --table-head:  rgba(139,92,246,0.12);
    --acc:         #7c3aed;
    --acc-lt:      #c4b5fd;
    --acc-dim:     rgba(124,58,237,0.14);
    --acc-glow:    rgba(124,58,237,0.28);
    --green:       #10d98a;
    --green-dim:   rgba(16,217,138,0.14);
    --red:         #f26a6a;
    --red-dim:     rgba(242,106,106,0.14);
    --amber:       #f5a623;
    --amber-dim:   rgba(245,166,35,0.10);
    --violet:      #a78bfa;
    --violet-dim:  rgba(167,139,250,0.12);
    --bdr:         rgba(255,255,255,0.10);
    --bdr-md:      rgba(139,92,246,0.38);
    --txt:         #f0e8ff;
    --txt-mid:     rgba(220,200,255,0.55);
    --glass-bg:    rgba(255,255,255,0.06);
    --glass-blur:  blur(18px) saturate(160%);
}

/* ── Background aurora fisso sull'intera app ─────────────────────────────── */
html, body,
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(ellipse 90% 55% at 10% 15%, rgba(88,28,220,0.20) 0%, transparent 55%),
        radial-gradient(ellipse 65% 50% at 90% 80%, rgba(219,39,119,0.16) 0%, transparent 55%),
        radial-gradient(ellipse 75% 60% at 55% 45%, rgba(30,58,138,0.12) 0%, transparent 60%),
        #06010f !important;
    background-attachment: fixed !important;
    color: var(--txt);
    font-family: 'Plus Jakarta Sans', sans-serif;
}

/* ── Header glass ────────────────────────────────────────────────────────── */
[data-testid="stHeader"],
header[data-testid="stHeader"] {
    background: rgba(6,1,15,0.55) !important;
    backdrop-filter: blur(16px) saturate(140%) !important;
    -webkit-backdrop-filter: blur(16px) saturate(140%) !important;
    border-bottom: 1px solid rgba(139,92,246,0.18) !important;
    box-shadow: none !important;
}
[data-testid="stToolbar"],
header[data-testid="stHeader"] > div {
    background: transparent !important;
}

/* Decoration bar gradiente aurora */
[data-testid="stDecoration"] {
    background: linear-gradient(90deg, #7c3aed, #ec4899, #3b82f6, #7c3aed) !important;
    background-size: 200% auto !important;
    animation: aurora-shimmer 5s linear infinite !important;
    height: 2px !important;
}

/* ── Sidebar glass ───────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: rgba(255,255,255,0.04) !important;
    border-right: 1px solid rgba(255,255,255,0.09) !important;
    backdrop-filter: blur(22px) saturate(160%) !important;
    -webkit-backdrop-filter: blur(22px) saturate(160%) !important;
    box-shadow: 4px 0 40px rgba(0,0,0,0.35) !important;
}
[data-testid="stSidebar"]::before {
    content: '';
    display: block;
    height: 2px;
    background: linear-gradient(90deg, #7c3aed, #ec4899, #3b82f6, #7c3aed);
    background-size: 200% auto;
    animation: aurora-shimmer 5s linear infinite;
}
[data-testid="stSidebar"] [data-testid="stHeader"] {
    background: transparent !important;
    border-bottom: none !important;
    backdrop-filter: none !important;
}

/* ── Main content area ───────────────────────────────────────────────────── */
[data-testid="stMain"],
section[data-testid="stMain"] > div {
    background: transparent !important;
}

/* ── Scrollbar globale ───────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
    background: rgba(139,92,246,0.25);
    border-radius: 999px;
}
::-webkit-scrollbar-thumb:hover { background: rgba(139,92,246,0.45); }
"""

CSS_COMPONENTS = """
/* ── KPI CARD (st.metric) — glass ───────────────────────────────────────── */
div[data-testid="stMetric"] {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.11) !important;
    border-radius: 14px !important;
    padding: 16px 18px !important;
    backdrop-filter: blur(16px) saturate(150%) !important;
    -webkit-backdrop-filter: blur(16px) saturate(150%) !important;
    box-shadow: 0 4px 24px rgba(0,0,0,0.35), 0 1px 0 rgba(255,255,255,0.06) inset !important;
    transition: border-color .2s, box-shadow .2s !important;
    position: relative;
    overflow: hidden;
    text-align: center !important;
}
div[data-testid="stMetric"]:hover {
    border-color: rgba(139,92,246,0.38) !important;
    box-shadow: 0 4px 28px rgba(0,0,0,0.40), 0 0 20px rgba(124,58,237,0.12) !important;
}
div[data-testid="stMetric"]::after {
    content: '';
    position: absolute; bottom: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--acc), #ec4899, transparent);
    animation: aurora-shimmer 5s linear infinite;
    background-size: 200% auto;
}
div[data-testid="stMetric"] label {
    font-size: 0.72rem !important;
    font-weight: 700 !important;
    letter-spacing: 1.2px !important;
    text-transform: uppercase !important;
    color: rgba(220,200,255,0.55) !important;
    display: block !important;
    text-align: center !important;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 1.85rem !important;
    font-weight: 700 !important;
    color: #f0e8ff !important;
    display: block !important;
    text-align: center !important;
    width: 100% !important;
}
div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.72rem !important;
    display: block !important;
    text-align: center !important;
}

/* ── TAB — pill style ────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    border-bottom: 1px solid rgba(255,255,255,0.09) !important;
    border-radius: 12px !important;
    padding: 4px !important;
    gap: 2px !important;
    backdrop-filter: blur(12px) !important;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 9px !important;
    height: auto !important;
    background: transparent !important;
    color: rgba(220,200,255,0.50) !important;
    border: none !important;
    border-bottom: none !important;
    padding: 9px 28px !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-size: 0.88rem !important;
    font-weight: 600 !important;
    transition: background 0.2s, color 0.2s !important;
}
.stTabs [data-baseweb="tab"]:hover {
    background: rgba(139,92,246,0.10) !important;
    color: rgba(220,200,255,0.80) !important;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, rgba(124,58,237,0.60), rgba(236,72,153,0.42)) !important;
    color: #f0e8ff !important;
    border-bottom: none !important;
    box-shadow: 0 2px 12px rgba(124,58,237,0.30) !important;
}
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] {
    display: none !important;
    background: transparent !important;
    height: 0 !important;
}

/* ── PLOTLY — glass container ────────────────────────────────────────────── */
.stPlotlyChart > div {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    border-radius: 16px !important;
    padding: 8px !important;
    backdrop-filter: blur(12px) !important;
    box-shadow: 0 4px 24px rgba(0,0,0,0.35) !important;
}

/* ── DATAFRAME ───────────────────────────────────────────────────────────── */
.stDataFrame, .stTable {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    border-radius: 14px !important;
    overflow: hidden;
    backdrop-filter: blur(12px) !important;
}
[data-testid="stDataFrameResizable"] {
    border-radius: 14px !important;
    overflow: hidden !important;
}
.stDataFrame th {
    background: rgba(139,92,246,0.12) !important;
    color: rgba(220,200,255,0.70) !important;
    font-size: 0.64rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.9px !important;
    text-transform: uppercase !important;
    border-bottom: 1px solid rgba(139,92,246,0.22) !important;
}
.stDataFrame td {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-size: 0.78rem !important;
    line-height: 1.08 !important;
    background: rgba(255,255,255,0.03) !important;
    color: #f0e8ff !important;
    border-bottom: 1px solid rgba(255,255,255,0.06) !important;
}
.stDataFrame tr:hover td { background: rgba(139,92,246,0.07) !important; }

/* ── INPUT / SELECTBOX / TEXTAREA ────────────────────────────────────────── */
div[data-testid="stSelectbox"] [data-baseweb="select"] > div,
div[data-testid="stSelectbox"] [data-baseweb="select"] > div:hover,
div[data-testid="stTextInput"] > div > div,
div[data-testid="stNumberInput"] > div > div,
div[data-testid="stDateInput"] > div > div,
div[data-testid="stTextArea"] > div > div,
div[data-testid="stMultiSelect"] [data-baseweb="select"] > div {
    background: rgba(139,92,246,0.09) !important;
    border: 1px solid rgba(139,92,246,0.28) !important;
    color: #f0e8ff !important;
    border-radius: 10px !important;
    backdrop-filter: blur(10px) !important;
    transition: border-color .2s, box-shadow .2s !important;
}
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea,
div[data-testid="stNumberInput"] input {
    color: #f0e8ff !important;
    background: transparent !important;
}
div[data-testid="stTextInput"] input::placeholder,
div[data-testid="stTextArea"] textarea::placeholder {
    color: rgba(200,180,255,0.35) !important;
}
div[data-testid="stTextInput"] > div > div:focus-within,
div[data-testid="stTextArea"] > div > div:focus-within,
div[data-testid="stNumberInput"] > div > div:focus-within {
    border-color: rgba(139,92,246,0.65) !important;
    box-shadow: 0 0 0 3px rgba(124,58,237,0.18) !important;
}
div[data-testid="stNumberInput"],
div[data-testid="stNumberInput"] > div,
div[data-testid="stNumberInput"] > div > div,
div[data-testid="stNumberInput"] [data-baseweb="input"],
div[data-testid="stNumberInput"] [data-baseweb="base-input"] {
    background: rgba(139,92,246,0.09) !important;
    border-color: rgba(139,92,246,0.28) !important;
    border-radius: 10px !important;
}
div[data-testid="stNumberInput"] button {
    background: rgba(139,92,246,0.10) !important;
    border-color: rgba(139,92,246,0.28) !important;
    color: #c4b5fd !important;
}
div[data-testid="stNumberInput"] button:hover {
    background: rgba(139,92,246,0.22) !important;
}
[data-baseweb="popover"] [data-baseweb="menu"],
[data-baseweb="select"] [role="listbox"],
ul[data-baseweb="menu"] {
    background: rgba(15,5,35,0.92) !important;
    backdrop-filter: blur(20px) !important;
    border: 1px solid rgba(139,92,246,0.25) !important;
    border-radius: 12px !important;
}
[data-baseweb="option"]:hover { background: rgba(139,92,246,0.14) !important; }

/* ── CONTAINER CON BORDO ─────────────────────────────────────────────────── */
html body [data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    border-radius: 16px !important;
    padding: 24px !important;
    backdrop-filter: blur(16px) !important;
    box-shadow: 0 4px 32px rgba(0,0,0,0.40) !important;
}
html body [data-testid="stForm"] {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(139,92,246,0.20) !important;
    border-radius: 16px !important;
    padding: 20px !important;
    backdrop-filter: blur(16px) !important;
}
html body [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"],
html body [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stHorizontalBlock"],
html body [data-testid="stForm"] [data-testid="stVerticalBlock"] {
    background: transparent !important;
}
html body [data-testid="stVerticalBlockBorderWrapper"] .stMarkdown,
html body [data-testid="stVerticalBlockBorderWrapper"] .stMarkdown div,
[data-testid="stVerticalBlockBorderWrapper"] .stMarkdown div {
    background: transparent !important;
}

/* ── BOTTONI ─────────────────────────────────────────────────────────────── */
div.stButton > button[kind="primary"],
div.stButton > button[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #7c3aed 0%, #a855f7 45%, #ec4899 100%) !important;
    background-size: 200% auto !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 10px !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-weight: 700 !important;
    font-size: 0.85rem !important;
    letter-spacing: 0.02em !important;
    box-shadow: 0 4px 18px rgba(124,58,237,0.38) !important;
    transition: transform .15s, box-shadow .15s !important;
    filter: none !important;
}
div.stButton > button[kind="primary"]:hover,
div.stButton > button[data-testid="baseButton-primary"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 28px rgba(124,58,237,0.52) !important;
    filter: none !important;
}
div.stButton > button[kind="secondary"],
div.stButton > button[data-testid="baseButton-secondary"] {
    background: rgba(255,255,255,0.05) !important;
    color: rgba(220,200,255,0.70) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 10px !important;
    font-size: 0.85rem !important;
    transition: background .2s, border-color .2s, color .2s !important;
}
div.stButton > button[kind="secondary"]:hover,
div.stButton > button[data-testid="baseButton-secondary"]:hover {
    background: rgba(139,92,246,0.12) !important;
    border-color: rgba(139,92,246,0.45) !important;
    color: #e0d4ff !important;
}
html body [data-testid="stSidebar"] div.stButton > button {
    padding: 8px 14px !important; height: auto !important;
    min-height: 36px !important; line-height: 1 !important;
    font-size: 0.82rem !important; font-weight: 600 !important;
    border-radius: 10px !important; margin-top: 8px !important;
    background: rgba(242,106,106,0.10) !important; color: #f26a6a !important;
    border: 1px solid rgba(242,106,106,0.35) !important;
    transition: background .2s, border-color .2s !important;
    width: 100% !important; text-align: center !important;
}
html body [data-testid="stSidebar"] div.stButton > button:hover {
    background: rgba(242,106,106,0.20) !important;
    border-color: rgba(242,106,106,0.60) !important;
    color: #ff9b94 !important;
}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown p {
    color: rgba(220,200,255,0.60) !important;
    font-size: 0.78rem !important;
}
div.stFormSubmitButton > button {
    background: linear-gradient(135deg, #7c3aed 0%, #a855f7 45%, #ec4899 100%) !important;
    color: #fff !important; border: none !important;
    border-radius: 10px !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-weight: 700 !important; font-size: 0.85rem !important;
    box-shadow: 0 4px 18px rgba(124,58,237,0.38) !important;
    transition: transform .15s, box-shadow .15s !important;
}
div.stFormSubmitButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 28px rgba(124,58,237,0.52) !important;
}
[data-testid="stDownloadButton"] > button {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 10px !important; color: rgba(220,200,255,0.70) !important;
    font-size: 0.82rem !important;
}
[data-testid="stDownloadButton"] > button:hover {
    border-color: rgba(139,92,246,0.45) !important; color: #e0d4ff !important;
}

/* ── ALTRI COMPONENTI ────────────────────────────────────────────────────── */
[data-testid="stCheckbox"] label { color: rgba(220,200,255,0.65) !important; font-size: 0.82rem !important; }
[data-testid="stCheckbox"] span[aria-checked] { background: var(--acc) !important; border-color: var(--acc) !important; }
hr { border-color: rgba(255,255,255,0.10) !important; margin: 1rem 0 !important; }
.stCaption, [data-testid="stCaptionContainer"] { color: rgba(220,200,255,0.55) !important; font-size: 0.75rem !important; }
[data-testid="stExpander"] {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    border-radius: 12px !important;
    backdrop-filter: blur(12px) !important;
}
[data-testid="stExpander"]:hover { border-color: rgba(139,92,246,0.38) !important; }
[data-testid="stExpander"] summary {
    font-size: 0.82rem !important; font-weight: 600 !important;
    color: #f0e8ff !important;
    background: rgba(139,92,246,0.06) !important;
    border-radius: 12px 12px 0 0 !important;
}
[data-testid="stAlert"] {
    background: rgba(139,92,246,0.10) !important;
    border: 1px solid rgba(139,92,246,0.28) !important;
    border-radius: 10px !important; border-left-width: 3px !important;
    font-size: 0.82rem !important; backdrop-filter: blur(10px) !important;
    color: #ddd6fe !important;
}
h1, h2, h3, h4, h5, h6 {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    color: #f0e8ff !important; letter-spacing: -0.2px;
}
.block-container { padding-top: 1.2rem !important; padding-bottom: 1rem !important; }
.element-container { margin-bottom: 0rem; }

@media (max-width: 768px) {
    .block-container {
        padding-top: 0.9rem !important;
        padding-bottom: 1.1rem !important;
    }
    .element-container {
        margin-bottom: 0.45rem !important;
    }
    [data-testid="stHorizontalBlock"] > [data-testid="column"] {
        margin-bottom: 0.8rem !important;
    }
    [data-testid="stHorizontalBlock"] > [data-testid="column"]:last-child {
        margin-bottom: 0 !important;
    }
    div[data-testid="stMetric"] {
        margin-bottom: 0.8rem !important;
    }
    html body [data-testid="stVerticalBlockBorderWrapper"] {
        padding: 18px !important;
        margin-bottom: 0.9rem !important;
    }
}

/* ── CUSTOM CLASSES ──────────────────────────────────────────────────────── */
.section-title {
    font-size: 1.25rem; font-family: 'Plus Jakarta Sans', sans-serif;
    font-weight: 700; letter-spacing: -0.2px; color: #f0e8ff; margin-bottom: 0.3rem;
}
.panel-title {
    font-weight: 700; font-size: 1.05rem; color: rgba(220,200,255,0.65);
    margin: 0 0 0.6rem 0; letter-spacing: -0.1px;
}
.kpi-note { color: rgba(220,200,255,0.55); font-size: 0.78rem; }
.badge {
    display: inline-block; padding: 3px 10px; border-radius: 20px;
    font-size: 0.72rem; font-weight: 600; letter-spacing: 0.5px;
    text-transform: uppercase; font-family: 'JetBrains Mono', monospace;
    background: var(--acc-dim); color: var(--acc-lt); border: 1px solid rgba(124,58,237,0.30);
}
.badge-green { background: var(--green-dim); color: #10d98a; border-color: rgba(16,217,138,0.28); }
.badge-red   { background: var(--red-dim);   color: #f26a6a; border-color: rgba(242,106,106,0.28); }
.badge-blue  { background: var(--acc-dim);   color: var(--acc-lt); border-color: rgba(124,58,237,0.30); }
.badge-pink  { background: var(--violet-dim);color: #a78bfa; border-color: rgba(167,139,250,0.28); }
.side-title {
    font-weight: 700; font-size: 0.75rem; letter-spacing: 1.2px;
    text-transform: uppercase; color: rgba(220,200,255,0.55); margin: 1rem 0 0.4rem 0;
}
.side-chip {
    display: inline-block; padding: 4px 12px; border-radius: 20px;
    border: 1px solid rgba(124,58,237,0.35); color: var(--acc-lt);
    background: var(--acc-dim); font-weight: 600; font-size: 0.78rem;
    font-family: 'JetBrains Mono', monospace; margin-bottom: 0.5rem;
}
.side-residuo {
    background: rgba(255,255,255,0.05); border: 1px solid rgba(16,217,138,0.35);
    border-radius: 12px; padding: 10px 13px; text-align: center;
    color: var(--green); font-weight: 700; font-size: 1.1rem;
    font-family: 'JetBrains Mono', monospace; letter-spacing: 0.02em;
    backdrop-filter: blur(12px); box-shadow: 0 4px 16px rgba(0,0,0,0.25);
}
.side-residuo.neg { border-color: rgba(242,106,106,0.40); color: var(--red); }
.side-residuo .label {
    display: block; font-size: 0.65rem; letter-spacing: 1.5px;
    text-transform: uppercase; font-family: 'Plus Jakarta Sans', sans-serif;
    color: rgba(220,200,255,0.55); margin-bottom: 5px; font-weight: 600;
}
.side-residuo .pill {
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(16,217,138,0.14); border: 1px solid rgba(16,217,138,0.38);
    color: var(--green); padding: 5px 12px; border-radius: 20px;
    font-weight: 700; font-size: 1rem; font-family: 'JetBrains Mono', monospace;
}
.side-residuo.neg .pill {
    background: rgba(242,106,106,0.14); border-color: rgba(242,106,106,0.38); color: var(--red);
}
.progress-wrap { margin-top: 5px; }
.progress-track {
    width: 100%; height: 7px; background: rgba(255,255,255,0.07);
    border-radius: 999px; overflow: hidden;
}
.progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #7c3aed 0%, #ec4899 100%);
    border-radius: 999px;
}
"""

CSS_TAB_METRICS = """
/* Metric dentro i tab: compatto, allineato a sinistra */
[data-testid="stTabsTabPanel"] div[data-testid="stMetric"] {
    text-align: left !important;
    padding: 12px 16px !important;
}
[data-testid="stTabsTabPanel"] div[data-testid="stMetric"] label {
    font-size: 0.65rem !important;
    font-weight: 600 !important;
    letter-spacing: 1.1px !important;
    text-transform: uppercase !important;
    color: rgba(160,185,230,0.55) !important;
    text-align: left !important;
}
[data-testid="stTabsTabPanel"] div[data-testid="stMetric"] [data-testid="stMetricValue"],
[data-testid="stTabsTabPanel"] div[data-testid="stMetric"] [data-testid="stMetricValue"] * {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 1.65rem !important;
    font-weight: 600 !important;
    color: #ffffff !important;
    text-align: left !important;
}
[data-testid="stTabsTabPanel"] div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
    font-size: 0.72rem !important;
    text-align: left !important;
}
"""

CSS_REGISTRO = """
/* ── Radio toggle Uscita/Entrata ─────────────────────────────────────────── */
div[data-testid="stRadio"] > div[role="radiogroup"] {
    display: flex !important; flex-direction: row !important;
    align-items: center !important; gap: -16px !important;
    flex-wrap: nowrap !important; margin-left: -12px !important;
}
.reg-html-shell div[data-testid="stRadio"] > div[role="radiogroup"] {
    margin-left: -25px !important; gap: -18px !important;
}
div[data-testid="stRadio"] > div[role="radiogroup"] > label {
    border-radius: 8px !important; padding: 6px 14px !important;
    transition: background .15s !important; margin: 0 !important; white-space: nowrap !important;
}
div[data-testid="stRadio"] > div[role="radiogroup"] > label:first-child:has(input:checked) {
    background: rgba(242,106,106,0.16) !important; color: #f26a6a !important;
    box-shadow: inset 0 0 0 1px rgba(242,106,106,0.20) !important;
}
div[data-testid="stRadio"] > div[role="radiogroup"] > label:last-child:has(input:checked) {
    background: rgba(16,217,138,0.15) !important; color: #10d98a !important;
    box-shadow: inset 0 0 0 1px rgba(16,217,138,0.18) !important;
}
div[data-testid="stRadio"] > div[role="radiogroup"]:has(label:nth-child(3)) > label:nth-child(1):has(input:checked) {
    background: rgba(139,92,246,0.16) !important; color: #c4b5fd !important;
}
div[data-testid="stRadio"] > div[role="radiogroup"]:has(label:nth-child(3)) > label:nth-child(2):has(input:checked) {
    background: rgba(242,106,106,0.16) !important; color: #f26a6a !important;
}
div[data-testid="stRadio"] > div[role="radiogroup"]:has(label:nth-child(3)) > label:nth-child(3):has(input:checked) {
    background: rgba(16,217,138,0.15) !important; color: #10d98a !important;
}

/* ── Tabelle HTML scrollabili — glass ────────────────────────────────────── */
.reg-html-shell {
    border: 1px solid rgba(139,92,246,0.22);
    border-radius: 14px; overflow: hidden;
    background: rgba(255,255,255,0.04);
    backdrop-filter: blur(14px);
    margin-bottom: 0;
}
.reg-html-bar {
    display: flex; align-items: center; justify-content: space-between;
    gap: 12px; padding: 10px 16px;
    background: rgba(139,92,246,0.08);
    border-bottom: 1px solid rgba(139,92,246,0.18);
}
.reg-html-bar-title {
    font-size: 0.68rem; font-weight: 700; letter-spacing: 1.2px;
    text-transform: uppercase; color: rgba(220,200,255,0.55);
}
.reg-html-bar-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem; color: #c4b5fd; white-space: nowrap;
}
.reg-html-scroll {
    overflow-x: auto;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    overscroll-behavior-x: contain;
    background: rgba(255,255,255,0.02);
}
.reg-html-scroll::-webkit-scrollbar { width: 6px; }
.reg-html-scroll::-webkit-scrollbar-track { background: transparent; }
.reg-html-scroll::-webkit-scrollbar-thumb {
    background: rgba(139,92,246,0.25); border-radius: 999px;
}
.reg-html-table {
    width: max-content;
    min-width: 100%;
    border-collapse: collapse;
    table-layout: auto; background: transparent;
}
.reg-html-table thead th {
    position: sticky; top: 0; z-index: 2;
    padding: 10px 14px;
    background: rgba(139,92,246,0.10);
    color: rgba(220,200,255,0.60);
    font-size: 0.68rem; font-weight: 700; letter-spacing: 1px;
    text-transform: uppercase;
    border-bottom: 1px solid rgba(139,92,246,0.20);
    white-space: nowrap;
}
.reg-html-table tbody tr { background: transparent; transition: background 0.1s; }
.reg-html-table tbody tr:hover { background: rgba(139,92,246,0.07); }
.reg-html-table tbody td {
    padding: 14px 14px; background: transparent;
    color: #f0e8ff; font-size: 0.875rem; line-height: 1.3;
    border-bottom: 1px solid rgba(255,255,255,0.05); vertical-align: middle;
}
.reg-html-shell.reg-html-compact .reg-html-bar {
    padding: 8px 14px;
}
.reg-html-shell.reg-html-compact .reg-html-bar-title {
    font-size: 0.62rem;
    letter-spacing: 1.05px;
}
.reg-html-shell.reg-html-compact .reg-html-table thead th {
    padding: 8px 12px;
    font-size: 0.62rem;
    letter-spacing: 0.85px;
}
.reg-html-shell.reg-html-compact .reg-html-table tbody td {
    padding: 11px 12px;
    font-size: 0.82rem;
}
.reg-html-shell.reg-html-fin-summary .reg-html-table tbody td:first-child {
    max-width: 110px;
}
.reg-html-shell.reg-html-fin-summary .reg-html-scroll {
    overflow-x: hidden;
}
.reg-html-shell.reg-html-fin-summary .reg-html-table {
    width: 100% !important;
    min-width: 0 !important;
    table-layout: fixed !important;
}
.reg-html-shell.reg-html-fin-summary .reg-html-table thead th,
.reg-html-shell.reg-html-fin-summary .reg-html-table tbody td {
    overflow: hidden;
    text-overflow: ellipsis;
}
.reg-html-shell .reg-html-table tbody tr td:nth-child(2) { color: #f0e8ff !important; }
.reg-html-table tbody tr:last-child td { border-bottom: none; }
.reg-html-empty {
    padding: 24px 16px !important; text-align: center !important;
    color: rgba(220,200,255,0.45) !important; font-size: 0.875rem !important;
}
.reg-chip {
    display: inline-flex; align-items: center; justify-content: center;
    padding: 3px 11px; border-radius: 999px; font-size: 0.72rem;
    font-weight: 700; letter-spacing: 0.4px; white-space: nowrap; line-height: 1.6;
}
.reg-del-row-btn div.stButton > button {
    background: rgba(242,106,106,0.10) !important; color: #f26a6a !important;
    border: 1px solid rgba(242,106,106,0.28) !important;
    border-radius: 8px !important; font-size: 0.8rem !important;
    font-weight: 600 !important; padding: 6px 14px !important;
    min-height: 35px !important; height: auto !important;
    line-height: 1 !important; transition: background .15s !important;
}
.reg-del-row-btn div.stButton > button:hover {
    background: rgba(242,106,106,0.20) !important;
}

@media (max-width: 768px) {
    .reg-html-bar {
        flex-wrap: wrap;
        align-items: flex-start;
    }
}
"""

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# CSS_LOGIN — Aurora / Glassmorphism  (v3: full fix)
# ---------------------------------------------------------------------------
CSS_LOGIN = """

/* ─── Header completamente trasparente nella pagina login ────────────────── */
body:has(.login-aurora-bg) [data-testid="stHeader"],
body:has(.login-aurora-bg) header[data-testid="stHeader"] {
    background: transparent !important;
    backdrop-filter: none !important;
    -webkit-backdrop-filter: none !important;
    border-bottom: none !important;
    box-shadow: none !important;
}
body:has(.login-aurora-bg) [data-testid="stToolbar"],
body:has(.login-aurora-bg) [data-testid="stDecoration"] {
    background: transparent !important;
    display: none !important;
}
/* ─── Login posizionato in alto ──────────────────────────────────────────── */
body:has(.login-aurora-bg) .block-container {
    padding-top: 1.2rem !important;
    padding-bottom: 0.8rem !important;
}
body:has(.login-aurora-bg) [data-testid="stMain"] > div:first-child {
    padding-top: 0 !important;
}
body:has(.login-aurora-bg) [data-testid="stAppViewContainer"] > section {
    padding-top: 0 !important;
}


/* ─── Sidebar nascosta ───────────────────────────────────────────────────── */
body:has(.login-aurora-bg) [data-testid="stSidebar"],
body:has(.login-aurora-bg) [data-testid="collapsedControl"] {
    display: none !important;
}

/* ─── Sfondo aurora login (orbs iniettati via HTML) ─────────────────────── */
.login-aurora-bg {
    position: fixed; inset: 0; z-index: 0; pointer-events: none;
    background:
        radial-gradient(ellipse 80% 50% at 15% 20%, rgba(88,28,220,0.22) 0%, transparent 60%),
        radial-gradient(ellipse 60% 45% at 85% 75%, rgba(219,39,119,0.18) 0%, transparent 55%),
        radial-gradient(ellipse 70% 55% at 50% 50%, rgba(30,58,138,0.15) 0%, transparent 65%),
        #06010f;
    overflow: hidden;
}
.login-aurora-bg::after {
    content: ''; position: absolute; inset: 0;
    background-image: radial-gradient(rgba(255,255,255,0.05) 1px, transparent 1px);
    background-size: 28px 28px; pointer-events: none;
}
.login-orb {
    position: absolute; border-radius: 50%;
    filter: blur(60px); pointer-events: none; will-change: transform;
}
.login-orb-1 {
    width:520px; height:520px; top:-130px; left:-110px;
    background: radial-gradient(circle, rgba(139,92,246,0.55) 0%, transparent 65%);
    animation: aurora-float-a 10s ease-in-out infinite;
}
.login-orb-2 {
    width:440px; height:440px; bottom:-110px; right:-90px;
    background: radial-gradient(circle, rgba(236,72,153,0.45) 0%, transparent 65%);
    animation: aurora-float-b 13s ease-in-out infinite;
}
.login-orb-3 {
    width:320px; height:320px; top:38%; left:42%;
    background: radial-gradient(circle, rgba(59,130,246,0.28) 0%, transparent 65%);
    animation: aurora-float-c 8s ease-in-out infinite;
}

/* ─── CARD — colonna centrale di Streamlit ───────────────────────────────── */
body:has(.login-aurora-bg)
  [data-testid="stMain"]
  [data-testid="stHorizontalBlock"]
  [data-testid="column"]:nth-child(2)
  > [data-testid="stVerticalBlock"] {
    position: relative; z-index: 10;
    background: rgba(255,255,255,0.055) !important;
    border: 1px solid rgba(255,255,255,0.13) !important;
    border-radius: 24px !important;
    padding: 2.8rem 2.2rem 2.4rem !important;
    backdrop-filter: blur(24px) saturate(160%) !important;
    -webkit-backdrop-filter: blur(24px) saturate(160%) !important;
    box-shadow:
        0 32px 80px rgba(0,0,0,0.60),
        0  1px  0   rgba(255,255,255,0.08) inset,
        0 -1px  0   rgba(255,255,255,0.04) inset !important;
    animation: login-card-in 0.65s cubic-bezier(0.22,1,0.36,1) both !important;
    overflow: hidden;
}
body:has(.login-aurora-bg)
  [data-testid="stMain"]
  [data-testid="stHorizontalBlock"]
  [data-testid="column"]:nth-child(2)
  > [data-testid="stVerticalBlock"]::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
    border-radius: 24px 24px 0 0;
    background: linear-gradient(90deg, #7c3aed, #ec4899, #3b82f6, #7c3aed);
    background-size: 200% auto;
    animation: aurora-shimmer 4s linear infinite;
    z-index: 2;
}
body:has(.login-aurora-bg) [data-testid="column"]:nth-child(2) > [data-testid="stVerticalBlock"] > * {
    animation: login-item-in 0.5s ease both;
}
body:has(.login-aurora-bg) [data-testid="column"]:nth-child(2) > [data-testid="stVerticalBlock"] > *:nth-child(1) { animation-delay:.08s; }
body:has(.login-aurora-bg) [data-testid="column"]:nth-child(2) > [data-testid="stVerticalBlock"] > *:nth-child(2) { animation-delay:.14s; }
body:has(.login-aurora-bg) [data-testid="column"]:nth-child(2) > [data-testid="stVerticalBlock"] > *:nth-child(3) { animation-delay:.20s; }
body:has(.login-aurora-bg) [data-testid="column"]:nth-child(2) > [data-testid="stVerticalBlock"] > *:nth-child(4) { animation-delay:.26s; }
body:has(.login-aurora-bg) [data-testid="column"]:nth-child(2) > [data-testid="stVerticalBlock"] > *:nth-child(5) { animation-delay:.31s; }

/* ─── HTML statico del login (logo, badge, heading) ─────────────────────── */
.login-logo-row {
    display: flex; align-items: center; gap: 13px; margin-bottom: 1.2rem;
}
.login-logo-icon {
    width: 50px; height: 50px; border-radius: 14px; flex-shrink: 0;
    background: linear-gradient(135deg, #7c3aed 0%, #ec4899 100%);
    display: flex; align-items: center; justify-content: center;
    font-size: 24px;
    box-shadow: 0 6px 24px rgba(139,92,246,0.45);
    animation: pulse-ring 3.5s ease infinite;
}
.login-logo-name {
    font-size: 1.35rem !important; font-weight: 700 !important;
    color: #f0e8ff !important; margin: 0 !important; padding: 0 !important;
    line-height: 1.2 !important; letter-spacing: -0.01em !important;
}
.login-logo-tagline {
    font-size: 0.82rem !important;
    color: rgba(220,200,255,0.45) !important;
    margin: 2px 0 0 !important; padding: 0 !important;
}
.login-status-badge {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 0.74rem; font-weight: 600;
    padding: 4px 13px; border-radius: 20px;
    background: rgba(139,92,246,0.14); color: #c4b5fd;
    border: 1px solid rgba(139,92,246,0.30);
    margin-bottom: 1.2rem; letter-spacing: 0.03em;
}
.login-status-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: #a78bfa; animation: badge-breathe 2.2s ease-in-out infinite;
}
.login-heading {
    font-size: 1.75rem !important; font-weight: 700 !important;
    color: #f0e8ff !important; letter-spacing: -0.02em !important;
    margin: 0 0 4px !important; padding: 0 !important; line-height: 1.15 !important;
}
.login-subheading {
    font-size: 0.92rem !important;
    color: rgba(200,180,255,0.50) !important;
    margin: 0 0 1.2rem !important; padding: 0 !important;
}

/* ─── TAB LOGIN — pill, spaziosi ─────────────────────────────────────────── */
body:has(.login-aurora-bg) .stTabs [data-baseweb="tab-list"] {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    border-bottom: 1px solid rgba(255,255,255,0.10) !important;
    border-radius: 12px !important;
    padding: 4px !important;
    gap: 2px !important;
    margin-bottom: 1.4rem !important;
}
body:has(.login-aurora-bg) .stTabs [data-baseweb="tab"] {
    border-radius: 9px !important;
    font-size: 0.92rem !important;
    font-weight: 600 !important;
    padding: 10px 32px !important;
    height: auto !important;
    color: rgba(200,180,255,0.48) !important;
    border-bottom: none !important;
    border: none !important;
    background: transparent !important;
    transition: background 0.2s, color 0.2s !important;
}
body:has(.login-aurora-bg) .stTabs [data-baseweb="tab"]:hover {
    background: rgba(139,92,246,0.10) !important;
    color: rgba(220,200,255,0.80) !important;
}
body:has(.login-aurora-bg) .stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, rgba(124,58,237,0.62), rgba(236,72,153,0.44)) !important;
    color: #f0e8ff !important;
    border-bottom: none !important;
    box-shadow: 0 2px 14px rgba(124,58,237,0.32) !important;
}
body:has(.login-aurora-bg) .stTabs [data-baseweb="tab-highlight"],
body:has(.login-aurora-bg) .stTabs [data-baseweb="tab-border"] {
    display: none !important; background: transparent !important; height: 0 !important;
}

/* ─── Label input LOGIN ──────────────────────────────────────────────────── */
body:has(.login-aurora-bg) [data-testid="stTextInput"] label p {
    font-size: 0.78rem !important; font-weight: 600 !important;
    letter-spacing: 0.09em !important; text-transform: uppercase !important;
    color: rgba(200,180,255,0.58) !important;
}

/* ─── Input LOGIN — viola più visibile ───────────────────────────────────── */
body:has(.login-aurora-bg) [data-testid="stTextInput"] > div > div {
    background: rgba(139,92,246,0.13) !important;
    border: 1px solid rgba(139,92,246,0.38) !important;
    border-radius: 11px !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
}
body:has(.login-aurora-bg) [data-testid="stTextInput"] input {
    color: #f0e8ff !important;
    font-size: 0.92rem !important;
    background: transparent !important;
}
body:has(.login-aurora-bg) [data-testid="stTextInput"] input::placeholder {
    color: rgba(200,180,255,0.32) !important;
}
body:has(.login-aurora-bg) [data-testid="stTextInput"] > div > div:focus-within {
    border-color: rgba(139,92,246,0.70) !important;
    box-shadow: 0 0 0 3px rgba(124,58,237,0.20) !important;
    background: rgba(139,92,246,0.18) !important;
}
body:has(.login-aurora-bg) [data-testid="stTextInput"] button {
    color: rgba(200,180,255,0.55) !important; background: transparent !important;
}

/* ─── Bottone Accedi ─────────────────────────────────────────────────────── */
body:has(.login-aurora-bg) div.stButton > button[kind="primary"],
body:has(.login-aurora-bg) div.stButton > button[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #7c3aed 0%, #a855f7 45%, #ec4899 100%) !important;
    background-size: 200% auto !important;
    border: none !important; border-radius: 12px !important;
    color: #fff !important; font-weight: 700 !important;
    font-size: 0.95rem !important; letter-spacing: 0.03em !important;
    box-shadow: 0 6px 28px rgba(124,58,237,0.42) !important;
    transition: transform 0.15s, box-shadow 0.15s !important;
    filter: none !important;
}
body:has(.login-aurora-bg) div.stButton > button[kind="primary"]:hover,
body:has(.login-aurora-bg) div.stButton > button[data-testid="baseButton-primary"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 10px 36px rgba(124,58,237,0.58) !important;
    filter: none !important;
}

/* ─── Bottoni secondari login ────────────────────────────────────────────── */
body:has(.login-aurora-bg) div.stButton > button[kind="secondary"],
body:has(.login-aurora-bg) div.stButton > button[data-testid="baseButton-secondary"] {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.13) !important;
    border-radius: 12px !important; color: rgba(200,180,255,0.68) !important;
    font-size: 0.88rem !important;
}
body:has(.login-aurora-bg) div.stButton > button[kind="secondary"]:hover,
body:has(.login-aurora-bg) div.stButton > button[data-testid="baseButton-secondary"]:hover {
    background: rgba(139,92,246,0.14) !important;
    border-color: rgba(139,92,246,0.50) !important; color: #e0d4ff !important;
}

body:has(.login-aurora-bg)
  div[data-testid="stElementContainer"]:has(.pb-google-oauth-anchor) {
    display: none !important;
    height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
}
body:has(.login-aurora-bg)
  div[data-testid="stElementContainer"]:has(.pb-google-oauth-anchor)
  + div[data-testid="stElementContainer"] {
    margin-top: 0.2rem !important;
    min-height: 58px !important;
    height: 58px !important;
    display: block !important;
    overflow: visible !important;
}
body:has(.login-aurora-bg)
  div[data-testid="stElementContainer"]:has(.pb-google-oauth-anchor)
  + div[data-testid="stElementContainer"] > div {
    min-height: 58px !important;
    height: 58px !important;
    display: block !important;
    overflow: visible !important;
}
body:has(.login-aurora-bg)
  div[data-testid="stElementContainer"]:has(.pb-google-oauth-anchor)
  + div[data-testid="stElementContainer"]
  iframe.stCustomComponentV1[data-testid="stCustomComponentV1"] {
    width: 100% !important;
    min-height: 58px !important;
    height: 58px !important;
    border: none !important;
    border-radius: 12px !important;
    overflow: hidden !important;
    background: transparent !important;
    display: block !important;
}

/* ─── Divider e alert ────────────────────────────────────────────────────── */
body:has(.login-aurora-bg) [data-testid="stDivider"] hr,
body:has(.login-aurora-bg) hr {
    border-color: rgba(255,255,255,0.10) !important;
}
body:has(.login-aurora-bg) [data-testid="stAlert"] {
    background: rgba(139,92,246,0.10) !important;
    border: 1px solid rgba(139,92,246,0.28) !important;
    border-radius: 10px !important; color: #ddd6fe !important;
}
"""

CSS_ALL = CSS_BASE + CSS_COMPONENTS + CSS_TAB_METRICS + CSS_REGISTRO + CSS_LOGIN
