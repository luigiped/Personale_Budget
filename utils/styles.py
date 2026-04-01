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
    --bg:          #090E1B;
    --bg-surf:     #0c1120;
    --bg-card:     #0c1120;
    --bg-form:     #090E1B;
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
    background: #090E1B !important;
    backdrop-filter: none !important;
}

[data-testid="stToolbar"],
header[data-testid="stHeader"] > div {
    background: #090E1B !important;
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
    padding: 8px 14px !important;
    height: auto !important;
    min-height: 36px !important;
    line-height: 1 !important;
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    border-radius: 10px !important;
    margin-top: 8px !important;
    background-color: rgba(255,124,115,0.10) !important;
    color: #ff7c73 !important;
    border: 1px solid rgba(242,106,106,0.40) !important;
    transition: background .2s, border-color .2s !important;
    width: 100% !important;
    text-align: center !important;
    letter-spacing: 0.3px !important;
}
html body [data-testid="stSidebar"] div.stButton > button:hover {
    background-color: rgba(242,106,106,0.22) !important;
    border-color: rgba(242,106,106,0.65) !important;
    color: #ff9b94 !important;
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
    font-size: 0.9rem !important;
    font-weight: 700 !important;
    letter-spacing: 1.2px !important;
    text-transform: uppercase !important;
    color: var(--txt-mid) !important;
    display: block !important;
    text-align: center !important;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 1.9rem !important;
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
/* FIX SOLO per il selectbox Frequenza */
div[data-testid="stSelectbox"] [data-baseweb="select"]:has(input[aria-label*="Frequenza"]) > div {
    background-color: #090E1B !important;
    border: 1px solid var(--bdr) !important;
    color: var(--txt) !important;
}

}
/* ── NUMBER INPUT — pulsanti +/- e wrapper ── */
div[data-testid="stNumberInput"],
div[data-testid="stNumberInput"] > div,
div[data-testid="stNumberInput"] > div > div,
div[data-testid="stNumberInput"] [data-baseweb="input"],
div[data-testid="stNumberInput"] [data-baseweb="base-input"] {
    background-color: #090E1B !important;
    border-color: var(--bdr) !important;
    border-radius: 8px !important;
}
div[data-testid="stNumberInput"] input {
    background-color: #090E1B !important;
    color: var(--txt) !important;
}
div[data-testid="stNumberInput"] button {
    background-color: #090E1B !important;
    border-color: var(--bdr) !important;
    color: #82b4f7 !important;
}
div[data-testid="stNumberInput"] button:hover {
    background-color: rgba(79,142,240,0.12) !important;
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
    background-color: #090E1B !important;
    border: 1px solid rgba(92,118,178,0.28) !important;
    border-radius: 14px !important;
    padding: 24px !important;
    box-shadow: 0 4px 28px rgba(0,0,0,0.5) !important;
}
html body [data-testid="stForm"] {
    background-color: #090E1B !important;
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
/* Radio toggle Uscita/Entrata */
div[data-testid="stRadio"] > div[role="radiogroup"] {
    display: flex !important;
    flex-direction: row !important;
    align-items: center !important;
    gap: -16px !important;
    flex-wrap: nowrap !important;
    margin-left: -12px !important;
}
.reg-html-shell div[data-testid="stRadio"] > div[role="radiogroup"] {
    margin-left: -25px !important;
    gap: -18px !important;
}


div[data-testid="stRadio"] > div[role="radiogroup"] > label {
    border-radius: 8px !important;
    padding: 6px 14px !important;
    transition: background .15s !important;
    margin: 0 !important;
    white-space: nowrap !important;
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
    table-layout: auto;
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
.reg-html-shell .reg-html-table tbody tr td:nth-child(2) {
    color: #DDE6F5 !important;
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

# ---------------------------------------------------------------------------
# CSS_LOGIN — Aurora / Glassmorphism  (fix v2: column-targeting, no div wrap)
# ---------------------------------------------------------------------------
CSS_LOGIN = """

/* ─── Keyframes ──────────────────────────────────────────────────────────── */
@keyframes aurora-float-a {
    0%,100% { transform: scale(1)    translate(0px, 0px);   }
    33%      { transform: scale(1.08) translate(22px,-28px); }
    66%      { transform: scale(0.95) translate(-10px,18px); }
}
@keyframes aurora-float-b {
    0%,100% { transform: scale(1)    translate(0px,0px);   }
    33%      { transform: scale(0.92) translate(-20px,24px); }
    66%      { transform: scale(1.06) translate(16px,-14px); }
}
@keyframes aurora-float-c {
    0%,100% { transform: scale(1)    translate(0px,0px);  }
    50%      { transform: scale(1.12) translate(18px,12px); }
}
@keyframes login-card-in {
    from { opacity:0; transform: translateY(28px) scale(0.97); }
    to   { opacity:1; transform: translateY(0)    scale(1);    }
}
@keyframes login-item-in {
    from { opacity:0; transform: translateY(10px); }
    to   { opacity:1; transform: translateY(0);    }
}
@keyframes aurora-shimmer {
    0%   { background-position: 200% center; }
    100% { background-position:-200% center; }
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

/* ─── Header / toolbar — colore aurora ──────────────────────────────────── */
body:has(.login-aurora-bg) [data-testid="stHeader"],
body:has(.login-aurora-bg) header[data-testid="stHeader"] {
    background: rgba(6,1,15,0.82) !important;
    backdrop-filter: blur(12px) !important;
    border-bottom: 1px solid rgba(139,92,246,0.18) !important;
}
body:has(.login-aurora-bg) [data-testid="stToolbar"],
body:has(.login-aurora-bg) [data-testid="stDecoration"] {
    background: transparent !important;
}

/* ─── Sidebar nascosta nella pagina login ────────────────────────────────── */
body:has(.login-aurora-bg) [data-testid="stSidebar"],
body:has(.login-aurora-bg) [data-testid="collapsedControl"] {
    display: none !important;
}

/* ─── Sfondo aurora fullscreen ───────────────────────────────────────────── */
.login-aurora-bg {
    position: fixed;
    inset: 0;
    z-index: 0;
    background:
        radial-gradient(ellipse 80% 50% at 15% 20%, rgba(88,28,220,0.22) 0%, transparent 60%),
        radial-gradient(ellipse 60% 45% at 85% 75%, rgba(219,39,119,0.18) 0%, transparent 55%),
        radial-gradient(ellipse 70% 55% at 50% 50%, rgba(30,58,138,0.15) 0%, transparent 65%),
        #06010f;
    overflow: hidden;
    pointer-events: none;
}
.login-aurora-bg::after {
    content: '';
    position: absolute; inset: 0;
    background-image: radial-gradient(rgba(255,255,255,0.05) 1px, transparent 1px);
    background-size: 28px 28px;
    pointer-events: none;
}

/* ─── Blob animati ────────────────────────────────────────────────────────── */
.login-orb {
    position: absolute;
    border-radius: 50%;
    filter: blur(60px);
    pointer-events: none;
    will-change: transform;
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

/* ─── CARD: si targettizza la colonna centrale di Streamlit ──────────────── */
/*  st.columns([1, 1.4, 1])  →  :nth-child(2)                               */
body:has(.login-aurora-bg)
  [data-testid="stMain"]
  [data-testid="stHorizontalBlock"]
  [data-testid="column"]:nth-child(2)
  > [data-testid="stVerticalBlock"] {
    position: relative;
    z-index: 10;
    background: rgba(255,255,255,0.055) !important;
    border: 1px solid rgba(255,255,255,0.13) !important;
    border-radius: 24px !important;
    padding: 2.4rem 2rem 2rem !important;
    backdrop-filter: blur(24px) saturate(160%) !important;
    -webkit-backdrop-filter: blur(24px) saturate(160%) !important;
    box-shadow:
        0 32px 80px rgba(0,0,0,0.60),
        0  1px  0   rgba(255,255,255,0.08) inset,
        0 -1px  0   rgba(255,255,255,0.04) inset !important;
    animation: login-card-in 0.65s cubic-bezier(0.22,1,0.36,1) both !important;
    overflow: hidden;
}
/* Striscia gradiente animata in cima alla card */
body:has(.login-aurora-bg)
  [data-testid="stMain"]
  [data-testid="stHorizontalBlock"]
  [data-testid="column"]:nth-child(2)
  > [data-testid="stVerticalBlock"]::before {
    content: '';
    display: block;
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    border-radius: 24px 24px 0 0;
    background: linear-gradient(90deg, #7c3aed, #ec4899, #3b82f6, #7c3aed);
    background-size: 200% auto;
    animation: aurora-shimmer 4s linear infinite;
    z-index: 2;
}

/* Stagger fade-in degli elementi della card */
body:has(.login-aurora-bg)
  [data-testid="stMain"]
  [data-testid="stHorizontalBlock"]
  [data-testid="column"]:nth-child(2)
  > [data-testid="stVerticalBlock"]
  > * {
    animation: login-item-in 0.5s ease both;
}
body:has(.login-aurora-bg) [data-testid="column"]:nth-child(2) > [data-testid="stVerticalBlock"] > *:nth-child(1) { animation-delay:.08s; }
body:has(.login-aurora-bg) [data-testid="column"]:nth-child(2) > [data-testid="stVerticalBlock"] > *:nth-child(2) { animation-delay:.14s; }
body:has(.login-aurora-bg) [data-testid="column"]:nth-child(2) > [data-testid="stVerticalBlock"] > *:nth-child(3) { animation-delay:.20s; }
body:has(.login-aurora-bg) [data-testid="column"]:nth-child(2) > [data-testid="stVerticalBlock"] > *:nth-child(4) { animation-delay:.25s; }
body:has(.login-aurora-bg) [data-testid="column"]:nth-child(2) > [data-testid="stVerticalBlock"] > *:nth-child(5) { animation-delay:.29s; }
body:has(.login-aurora-bg) [data-testid="column"]:nth-child(2) > [data-testid="stVerticalBlock"] > *:nth-child(6) { animation-delay:.33s; }

/* ─── Logo / badge / heading — testi ─────────────────────────────────────── */
.login-logo-row {
    display: flex; align-items: center; gap: 13px;
    margin-bottom: 1.4rem;
}
.login-logo-icon {
    width:46px; height:46px; border-radius:13px; flex-shrink:0;
    background: linear-gradient(135deg, #7c3aed 0%, #ec4899 100%);
    display:flex; align-items:center; justify-content:center;
    font-size:22px;
    box-shadow: 0 6px 24px rgba(139,92,246,0.45);
    animation: pulse-ring 3.5s ease infinite;
}
.login-logo-name {
    font-size: 1.18rem !important; font-weight: 700 !important;
    color: #f0e8ff !important;
    margin: 0 !important; padding: 0 !important; line-height: 1.2 !important;
    letter-spacing: -0.01em !important;
}
.login-logo-tagline {
    font-size: 0.74rem !important;
    color: rgba(220,200,255,0.45) !important;
    margin: 2px 0 0 !important; padding: 0 !important;
}
.login-status-badge {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 0.70rem; font-weight: 600;
    padding: 3px 12px; border-radius: 20px;
    background: rgba(139,92,246,0.14);
    color: #c4b5fd;
    border: 1px solid rgba(139,92,246,0.30);
    margin-bottom: 1.2rem; letter-spacing: 0.03em;
}
.login-status-dot {
    width:6px; height:6px; border-radius:50%;
    background:#a78bfa;
    animation: badge-breathe 2.2s ease-in-out infinite;
}
.login-heading {
    font-size: 1.55rem !important; font-weight: 700 !important;
    color: #f0e8ff !important; letter-spacing: -0.02em !important;
    margin: 0 0 3px !important; padding: 0 !important; line-height: 1.15 !important;
}
.login-subheading {
    font-size: 0.81rem !important;
    color: rgba(200,180,255,0.48) !important;
    margin: 0 0 1.2rem !important; padding: 0 !important;
}

/* ─── TAB — pill style (alta specificità per battere CSS_BASE) ────────────── */
body:has(.login-aurora-bg) .stTabs [data-baseweb="tab-list"] {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    border-bottom: 1px solid rgba(255,255,255,0.10) !important;
    border-radius: 10px !important;
    padding: 3px !important;
    gap: 2px !important;
    margin-bottom: 1.2rem !important;
}
body:has(.login-aurora-bg) .stTabs [data-baseweb="tab"] {
    border-radius: 8px !important;
    font-size: 0.83rem !important;
    font-weight: 600 !important;
    padding: 6px 20px !important;
    height: auto !important;
    color: rgba(200,180,255,0.48) !important;
    border-bottom: none !important;
    border: none !important;
    background: transparent !important;
    transition: background 0.2s, color 0.2s !important;
}
body:has(.login-aurora-bg) .stTabs [data-baseweb="tab"]:hover {
    background: rgba(139,92,246,0.08) !important;
    color: rgba(220,200,255,0.75) !important;
}
body:has(.login-aurora-bg) .stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, rgba(124,58,237,0.60), rgba(236,72,153,0.42)) !important;
    color: #f0e8ff !important;
    border-bottom: none !important;
    box-shadow: 0 2px 12px rgba(139,92,246,0.30) !important;
}
/* Nasconde la barra rossa/blu underline default */
body:has(.login-aurora-bg) .stTabs [data-baseweb="tab-highlight"],
body:has(.login-aurora-bg) .stTabs [data-baseweb="tab-border"] {
    display: none !important;
    background: transparent !important;
    height: 0 !important;
}

/* ─── Label input ─────────────────────────────────────────────────────────── */
body:has(.login-aurora-bg) [data-testid="stTextInput"] label p {
    font-size: 0.72rem !important; font-weight: 600 !important;
    letter-spacing: 0.09em !important; text-transform: uppercase !important;
    color: rgba(200,180,255,0.55) !important;
}

/* ─── Input field ─────────────────────────────────────────────────────────── */
body:has(.login-aurora-bg) [data-testid="stTextInput"] > div > div,
body:has(.login-aurora-bg) [data-testid="stTextInput"] input {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 10px !important;
    color: #f0e8ff !important;
    font-size: 0.88rem !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
}
body:has(.login-aurora-bg) [data-testid="stTextInput"] input::placeholder {
    color: rgba(200,180,255,0.28) !important;
}
body:has(.login-aurora-bg) [data-testid="stTextInput"] input:focus {
    border-color: rgba(139,92,246,0.65) !important;
    box-shadow: 0 0 0 3px rgba(139,92,246,0.18) !important;
    background: rgba(255,255,255,0.09) !important;
}
body:has(.login-aurora-bg) [data-testid="stTextInput"] button {
    color: rgba(200,180,255,0.50) !important;
    background: transparent !important;
}

/* ─── Bottone primario "Accedi" ───────────────────────────────────────────── */
body:has(.login-aurora-bg) div.stButton > button[kind="primary"],
body:has(.login-aurora-bg) div.stButton > button[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #7c3aed 0%, #a855f7 45%, #ec4899 100%) !important;
    background-size: 200% auto !important;
    border: none !important;
    border-radius: 11px !important;
    color: #fff !important;
    font-weight: 700 !important;
    font-size: 0.88rem !important;
    letter-spacing: 0.03em !important;
    box-shadow: 0 6px 28px rgba(139,92,246,0.42) !important;
    transition: transform 0.15s, box-shadow 0.15s !important;
    filter: none !important;
}
body:has(.login-aurora-bg) div.stButton > button[kind="primary"]:hover,
body:has(.login-aurora-bg) div.stButton > button[data-testid="baseButton-primary"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 10px 36px rgba(139,92,246,0.58) !important;
    filter: none !important;
}

/* ─── Bottoni secondari (Google, Password dimenticata) ────────────────────── */
body:has(.login-aurora-bg) div.stButton > button[kind="secondary"],
body:has(.login-aurora-bg) div.stButton > button[data-testid="baseButton-secondary"] {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.13) !important;
    border-radius: 11px !important;
    color: rgba(200,180,255,0.68) !important;
    font-size: 0.83rem !important;
}
body:has(.login-aurora-bg) div.stButton > button[kind="secondary"]:hover,
body:has(.login-aurora-bg) div.stButton > button[data-testid="baseButton-secondary"]:hover {
    background: rgba(139,92,246,0.13) !important;
    border-color: rgba(139,92,246,0.48) !important;
    color: #e0d4ff !important;
}

/* ─── Divider ─────────────────────────────────────────────────────────────── */
body:has(.login-aurora-bg) [data-testid="stDivider"] hr,
body:has(.login-aurora-bg) hr {
    border-color: rgba(255,255,255,0.10) !important;
}

/* ─── Alert / warning ────────────────────────────────────────────────────── */
body:has(.login-aurora-bg) [data-testid="stAlert"] {
    background: rgba(139,92,246,0.10) !important;
    border: 1px solid rgba(139,92,246,0.28) !important;
    border-radius: 10px !important;
    color: #ddd6fe !important;
}
"""

# Tutto il CSS in un unico blocco (uso rapido in Streamlit)
CSS_ALL = CSS_BASE + CSS_COMPONENTS + CSS_TAB_METRICS + CSS_REGISTRO + CSS_LOGIN