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

:root {
    --bg:          #07090F;
    --bg-surf:     #0c1120;
    --bg-card:     #0c1120;
    --bg-form:     #0F1628;
    --bg-inp:      #0a1020;
    --table-bg:    #3D2837;
    --table-head:  #1A2741;
    --acc:         #4f8ef0;
    --acc-lt:      #82b4f7;
    --acc-dim:     rgba(79,142,240,0.12);
    --acc-glow:    rgba(79,142,240,0.22);
    --green:       #2fdd96;
    --green-dim:   rgba(47,221,150,0.14);
    --red:         #ff7c73;
    --red-dim:     rgba(255,124,115,0.14);
    --amber:       #f5a623;
    --amber-dim:   rgba(245,166,35,0.10);
    --violet:      #9b74f5;
    --violet-dim:  rgba(155,116,245,0.10);
    --bdr:         rgba(92,118,178,0.20);
    --bdr-md:      rgba(112,143,215,0.34);
    --txt:         #ededed;
    --txt-mid:     #ededed;
}

html, body,
[data-testid="stAppViewContainer"],
[data-testid="stHeader"] {
    background-color: var(--bg) !important;
    background-image:
        radial-gradient(ellipse 100% 60% at 70% -10%, rgba(79,142,240,0.07) 0%, transparent 55%),
        radial-gradient(ellipse 60% 40% at 5% 90%,   rgba(155,116,245,0.04) 0%, transparent 50%);
    color: var(--txt);
    font-family: 'Plus Jakarta Sans', sans-serif;
}

[data-testid="stHeader"] {
    border-bottom: none !important;
    background: #07090F !important;
    backdrop-filter: none !important;
}

[data-testid="stToolbar"],
header[data-testid="stHeader"] > div {
    background: #07090F !important;
}

[data-testid="stSidebar"] {
    background: var(--bg-surf) !important;
    border-right: 1px solid var(--bdr) !important;
    box-shadow: 4px 0 30px rgba(0,0,0,0.35);
}
[data-testid="stSidebar"]::before {
    content: '';
    display: block;
    height: 3px;
    background: linear-gradient(90deg, var(--acc) 0%, #fa598e 60%, transparent 100%);
}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown p {
    color: var(--txt-mid) !important;
    font-size: 0.78rem !important;
}

html body [data-testid="stSidebar"] div.stButton > button {
    padding: 5px 14px !important;
    height: auto !important;
    min-height: 24px !important;
    line-height: 1 !important;
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    border-radius: 5px !important;
    margin-top: 4px !important;
    background-color: rgba(255,124,115,0.14) !important;
    color: #ff7c73 !important;
    border: 1px solid rgba(242,106,106,0.35) !important;
    transition: background .15s !important;
}
html body [data-testid="stSidebar"] div.stButton > button:hover {
    background-color: rgba(242,106,106,0.28) !important;
}

h1, h2, h3, h4, h5, h6 {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    color: var(--txt) !important;
    letter-spacing: -0.2px;
}

.block-container {
    padding-top: 1.6rem !important;
    padding-bottom: 1rem !important;
}
.element-container { margin-bottom: 0rem; }
"""

CSS_COMPONENTS = """
/* ── KPI CARD (st.metric) ── */
div[data-testid="stMetric"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--bdr) !important;
    border-radius: 10px !important;
    padding: 14px 18px !important;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4), 0 1px 0 rgba(79,142,240,0.06) inset !important;
    transition: box-shadow .2s, border-color .2s !important;
    position: relative;
    overflow: hidden;
    text-align: center !important;
}
div[data-testid="stMetric"]:hover { border-color: var(--bdr-md) !important; }
div[data-testid="stMetric"]::after {
    content: '';
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--acc), transparent);
}
div[data-testid="stMetric"] label {
    font-size: 0.68rem !important;
    font-weight: 700 !important;
    letter-spacing: 1.2px !important;
    text-transform: uppercase !important;
    color: var(--txt-mid) !important;
    display: block !important;
    text-align: center !important;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 1.65rem !important;
    font-weight: 700 !important;
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

/* ── TAB ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 2px !important;
    background: transparent !important;
    border-bottom: 1px solid var(--bdr) !important;
}
.stTabs [data-baseweb="tab"] {
    height: 44px;
    background-color: transparent !important;
    color: var(--txt-mid) !important;
    border-radius: 0 !important;
    padding: 8px 20px !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    transition: color .2s, border-color .2s !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: var(--txt) !important;
    background: rgba(79,142,240,0.04) !important;
}
.stTabs [aria-selected="true"] {
    color: var(--acc-lt) !important;
    border-bottom: 2px solid var(--acc) !important;
    background: rgba(79,142,240,0.06) !important;
}

/* ── PLOTLY ── */
.stPlotlyChart > div {
    background: var(--bg-card) !important;
    border: 1px solid var(--bdr) !important;
    border-radius: 14px !important;
    padding: 6px !important;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4) !important;
}

/* ── DATAFRAME ── */
.stDataFrame, .stTable {
    background: var(--table-bg) !important;
    border: 1px solid var(--bdr) !important;
    border-radius: 14px !important;
    overflow: hidden;
}
[data-testid="stDataFrameResizable"] {
    border-radius: 14px !important;
    overflow: hidden !important;
}
.stDataFrame th {
    background: var(--table-head) !important;
    color: #7f92b9 !important;
    font-size: 0.64rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.9px !important;
    text-transform: uppercase !important;
    border-bottom: 1px solid rgba(128,160,232,0.34) !important;
}
.stDataFrame td {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-size: 0.78rem !important;
    line-height: 1.08 !important;
    background: var(--table-bg) !important;
    border-bottom: 1px solid rgba(128,160,232,0.28) !important;
}
.stDataFrame tr:hover td { background: rgba(79,142,240,0.06) !important; }

/* ── INPUT / SELECTBOX / TEXTAREA ── */
div[data-testid="stSelectbox"] [data-baseweb="select"] > div,
div[data-testid="stSelectbox"] [data-baseweb="select"] > div:hover,
div[data-testid="stTextInput"] > div > div,
div[data-testid="stNumberInput"] > div > div,
div[data-testid="stDateInput"] > div > div,
div[data-testid="stTextArea"] > div > div,
div[data-testid="stMultiSelect"] [data-baseweb="select"] > div {
    background-color: #090E1B !important;
    border: 1px solid var(--bdr) !important;
    color: var(--txt) !important;
    transition: border-color .2s !important;
}
[data-baseweb="popover"] [data-baseweb="menu"],
[data-baseweb="select"] [role="listbox"],
ul[data-baseweb="menu"] {
    background-color: #090E1B !important;
    border: 1px solid var(--bdr) !important;
}
[data-baseweb="option"]:hover {
    background-color: rgba(79,142,240,0.12) !important;
}

/* ── CONTAINER CON BORDO ── */
html body [data-testid="stVerticalBlockBorderWrapper"] {
    background-color: #0F1628 !important;
    border: 1px solid rgba(92,118,178,0.28) !important;
    border-radius: 14px !important;
    padding: 24px !important;
    box-shadow: 0 4px 28px rgba(0,0,0,0.5) !important;
}
html body [data-testid="stForm"] {
    background-color: #0F1628 !important;
    border: 1px solid rgba(92,118,178,0.28) !important;
    border-radius: 14px !important;
    padding: 20px !important;
}
html body [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"],
html body [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stHorizontalBlock"],
html body [data-testid="stForm"] [data-testid="stVerticalBlock"] {
    background-color: transparent !important;
}
html body [data-testid="stVerticalBlockBorderWrapper"] .stMarkdown,
html body [data-testid="stVerticalBlockBorderWrapper"] .stMarkdown div,
[data-testid="stVerticalBlockBorderWrapper"] .stMarkdown div {
    background-color: transparent !important;
}

/* ── BOTTONI ── */
div.stButton > button[kind="primary"],
div.stButton > button[data-testid="baseButton-primary"] {
    background: var(--acc) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.82rem !important;
    letter-spacing: 0.2px !important;
    box-shadow: 0 4px 14px rgba(79,142,240,0.32) !important;
    transition: filter .2s, transform .15s !important;
}
div.stButton > button[kind="primary"]:hover {
    filter: brightness(1.12) !important;
    transform: translateY(-1px) !important;
}
div.stButton > button[kind="secondary"],
div.stButton > button[data-testid="baseButton-secondary"] {
    background: transparent !important;
    color: var(--txt-mid) !important;
    border: 1px solid var(--bdr) !important;
    border-radius: 8px !important;
    font-size: 0.82rem !important;
    transition: border-color .2s, color .2s !important;
}
div.stButton > button[kind="secondary"]:hover {
    border-color: var(--bdr-md) !important;
    color: var(--txt) !important;
}
div.stFormSubmitButton > button {
    background: var(--acc) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.82rem !important;
    box-shadow: 0 4px 14px rgba(79,142,240,0.32) !important;
    transition: filter .2s, transform .15s !important;
}
div.stFormSubmitButton > button:hover {
    filter: brightness(1.12) !important;
    transform: translateY(-1px) !important;
}
[data-testid="stDownloadButton"] > button {
    background: transparent !important;
    border: 1px solid var(--bdr) !important;
    border-radius: 8px !important;
    color: var(--txt) !important;
    font-size: 0.82rem !important;
}
[data-testid="stDownloadButton"] > button:hover {
    border-color: var(--bdr-md) !important;
}

/* ── ALTRI COMPONENTI ── */
[data-testid="stCheckbox"] label {
    color: var(--txt-mid) !important;
    font-size: 0.8rem !important;
}
[data-testid="stCheckbox"] span[aria-checked] {
    background: var(--acc) !important;
    border-color: var(--acc) !important;
}
hr { border-color: var(--bdr) !important; margin: 1rem 0 !important; }
.stCaption, [data-testid="stCaptionContainer"] {
    color: var(--txt) !important;
    font-size: 0.75rem !important;
}
[data-testid="stExpander"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--bdr) !important;
    border-radius: 10px !important;
}
[data-testid="stExpander"]:hover { border-color: var(--bdr-md) !important; }
[data-testid="stExpander"] summary {
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    color: var(--txt) !important;
    background: rgba(79,142,240,0.04) !important;
    border-radius: 10px 10px 0 0 !important;
}
[data-testid="stAlert"] {
    border-radius: 9px !important;
    border-left-width: 3px !important;
    font-size: 0.82rem !important;
}

/* ── CUSTOM CLASSES ── */
.section-title {
    font-size: 1.25rem;
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-weight: bold;
    letter-spacing: -0.2px;
    color: var(--txt);
    margin-bottom: 0.3rem;
}
.panel-title {
    font-weight: 700;
    font-size: 19px;
    color: var(--txt-mid);
    margin: 0 0 0.6rem 0;
    letter-spacing: -0.1px;
}
.kpi-note { color: var(--txt-mid); font-size: 0.78rem; }

.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    font-family: 'JetBrains Mono', monospace;
    background: var(--acc-dim);
    color: var(--acc-lt);
    border: 1px solid rgba(79,142,240,0.28);
}
.badge-green { background: var(--green-dim); color: #10d98a; border-color: rgba(16,217,138,0.25); }
.badge-red   { background: var(--red-dim);   color: #f26a6a; border-color: rgba(242,106,106,0.25); }
.badge-blue  { background: var(--acc-dim);   color: var(--acc-lt); border-color: rgba(79,142,240,0.28); }
.badge-pink  { background: var(--violet-dim);color: #9b74f5; border-color: rgba(155,116,245,0.25); }

/* Sidebar residuo mese */
.side-title {
    font-weight: 700; font-size: 0.75rem; letter-spacing: 1.2px;
    text-transform: uppercase; color: var(--txt-mid); margin: 1rem 0 0.4rem 0;
}
.side-chip {
    display: inline-block; padding: 4px 12px; border-radius: 20px;
    border: 1px solid rgba(79,142,240,0.3); color: var(--acc-lt);
    background: var(--acc-dim); font-weight: 600; font-size: 0.78rem;
    font-family: 'JetBrains Mono', monospace; margin-bottom: 0.5rem;
}
.side-residuo {
    background: var(--bg-card); border: 1px solid rgba(16,217,138,0.35);
    border-radius: 10px; padding: 10px 13px; text-align: center;
    color: var(--green); font-weight: 700; font-size: 1.1rem;
    font-family: 'JetBrains Mono', monospace; letter-spacing: 0.02em;
    box-shadow: 0 4px 16px rgba(0,0,0,0.3);
}
.side-residuo.neg { border-color: rgba(242,106,106,0.4); color: var(--red); }
.side-residuo .label {
    display: block; font-size: 0.65rem; letter-spacing: 1.5px;
    text-transform: uppercase; font-family: 'Plus Jakarta Sans', sans-serif;
    color: var(--txt-mid); margin-bottom: 5px; font-weight: 600;
}
.side-residuo .pill {
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(16,217,138,0.15); border: 1px solid rgba(16,217,138,0.4);
    color: var(--green); padding: 5px 12px; border-radius: 20px;
    font-weight: 700; font-size: 1rem; font-family: 'JetBrains Mono', monospace;
}
.side-residuo.neg .pill {
    background: rgba(242,106,106,0.15); border-color: rgba(242,106,106,0.4); color: var(--red);
}

/* Progress bar */
.progress-wrap { margin-top: 5px; }
.progress-track {
    width: 100%; height: 8px; background: rgba(255,255,255,0.07);
    border-radius: 999px; overflow: hidden;
}
.progress-fill {
    height: 100%; background: linear-gradient(90deg, var(--green) 0%, #34d399 100%);
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
    font-size: 1.25rem !important;
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
/* Radio toggle Uscita/Entrata */
div[data-testid="stRadio"] > div[role="radiogroup"] > label {
    border-radius: 8px !important;
    padding: 6px 14px !important;
    transition: background .15s !important;
}
div[data-testid="stRadio"] > div[role="radiogroup"] > label:first-child:has(input:checked) {
    background: rgba(255,124,115,0.16) !important;
    color: #EF696A !important;
    box-shadow: inset 0 0 0 1px rgba(255,124,115,0.16) !important;
}
div[data-testid="stRadio"] > div[role="radiogroup"] > label:last-child:has(input:checked) {
    background: rgba(47,221,150,0.15) !important;
    color: #42e7a7 !important;
    box-shadow: inset 0 0 0 1px rgba(47,221,150,0.14) !important;
}
div[data-testid="stRadio"] > div[role="radiogroup"]:has(label:nth-child(3)) > label:nth-child(1):has(input:checked) {
    background: rgba(79,142,240,0.14) !important;
    color: #8db8ff !important;
}
div[data-testid="stRadio"] > div[role="radiogroup"]:has(label:nth-child(3)) > label:nth-child(2):has(input:checked) {
    background: rgba(255,124,115,0.16) !important;
    color: #EF696A !important;
}
div[data-testid="stRadio"] > div[role="radiogroup"]:has(label:nth-child(3)) > label:nth-child(3):has(input:checked) {
    background: rgba(47,221,150,0.15) !important;
    color: #42e7a7 !important;
}

/* Tabelle HTML scrollabili */
.reg-html-shell {
    border: 1px solid rgba(79,142,240,0.15);
    border-radius: 14px;
    overflow: hidden;
    background: #0c1120;
    margin-bottom: 0;
}
.reg-html-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 16px;
    background: rgba(79,142,240,0.05);
    border-bottom: 1px solid rgba(79,142,240,0.12);
}
.reg-html-bar-title {
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: #5a6f8c;
}
.reg-html-bar-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem;
    color: #82b4f7;
    white-space: nowrap;
}
.reg-html-scroll {
    overflow-y: auto;
    overflow-x: hidden;
    background: #0c1120;
}
.reg-html-scroll::-webkit-scrollbar { width: 6px; }
.reg-html-scroll::-webkit-scrollbar-track { background: transparent; }
.reg-html-scroll::-webkit-scrollbar-thumb {
    background: rgba(79,142,240,0.18);
    border-radius: 999px;
}
.reg-html-table {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
    background: #0c1120;
}
.reg-html-table thead th {
    position: sticky;
    top: 0;
    z-index: 2;
    padding: 10px 14px;
    background: #0c1120;
    color: #5a6f8c;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
    border-bottom: 1px solid rgba(79,142,240,0.12);
    white-space: nowrap;
}
.reg-html-table tbody tr { background: #0c1120; transition: background 0.1s; }
.reg-html-table tbody tr:hover { background: rgba(79,142,240,0.04); }
.reg-html-table tbody td {
    padding: 14px 14px;
    background: transparent;
    color: #dde6f5;
    font-size: 0.875rem;
    line-height: 1.3;
    border-bottom: 1px solid rgba(79,142,240,0.07);
    vertical-align: middle;
}
.reg-html-table tbody tr:last-child td { border-bottom: none; }
.reg-html-empty {
    padding: 24px 16px !important;
    text-align: center !important;
    color: #5a6f8c !important;
    font-size: 0.875rem !important;
}
.reg-chip {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 3px 11px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.4px;
    white-space: nowrap;
    line-height: 1.6;
}
.reg-del-row-btn div.stButton > button {
    background: rgba(242,106,106,0.10) !important;
    color: #f26a6a !important;
    border: 1px solid rgba(242,106,106,0.25) !important;
    border-radius: 8px !important;
    font-size: 0.8rem !important;
    font-weight: 600 !important;
    padding: 6px 14px !important;
    min-height: 35px !important;
    height: auto !important;
    line-height: 1 !important;
    transition: background .15s !important;
}
.reg-del-row-btn div.stButton > button:hover {
    background: rgba(242,106,106,0.18) !important;
}
"""

# Tutto il CSS in un unico blocco (uso rapido in Streamlit)
CSS_ALL = CSS_BASE + CSS_COMPONENTS + CSS_TAB_METRICS + CSS_REGISTRO