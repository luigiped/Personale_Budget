# streamlit run interfaccia.py
#per abilitare login e registrazione cambiare in secrets la chiave, da demo only a normal.
import time
import streamlit as st
import pandas as pd
import Database as db
import logiche as log
from datetime import date, datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
import re
import base64
import json
import os
from html import escape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from streamlit_oauth import OAuth2Component
except Exception:
    OAuth2Component = None

from config_runtime import (
    IS_CLOUD_RUN,
    IS_DEMO,
    default_base_url,
    export_runtime_env,
    load_google_oauth_credentials,
    get_secret,
    auth_access_mode,
)

export_runtime_env()
client_id, client_secret = load_google_oauth_credentials()
APP_BASE_URL = default_base_url()

DEMO_USER_EMAIL = None
DEMO_USER_PASSWORD = None
if IS_DEMO:
    try:
        DEMO_USER_EMAIL = get_secret("DEMO_USER_EMAIL")
        DEMO_USER_PASSWORD = get_secret("DEMO_USER_PASSWORD")
    except Exception:
        pass
DEMO_USER_EMAIL_NORM = str(DEMO_USER_EMAIL or "").strip().lower() if DEMO_USER_EMAIL else None

# ── Auth manager ───────────────────────────────────────────────────────────────
from auth_manager import (
    get_session_user,
    create_new_session,
    clear_session,
    create_demo_session,
    login_email_password,
    register_demo_user,
)
# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Dashboard Personal Budget", layout="wide", page_icon="💰")

# --- CONTROLLO ACCESSO ---
AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

def _infer_base_url_from_headers():
    try:
        headers = st.context.headers
    except Exception:
        return None
    if not headers:
        return None
    host = headers.get("x-forwarded-host") or headers.get("host")
    proto = headers.get("x-forwarded-proto") or "https"
    if not host:
        return None
    return f"{proto}://{host}".rstrip("/")


def _resolve_redirect_uri():
    if IS_CLOUD_RUN:
        inferred = _infer_base_url_from_headers()
        if inferred:
            return inferred
        if APP_BASE_URL:
            return APP_BASE_URL.rstrip("/")
        return None
    if APP_BASE_URL:
        return APP_BASE_URL.rstrip("/")
    return "http://localhost:8080"


def _decode_id_token_email(id_token):
    if not id_token:
        return None
    try:
        if isinstance(id_token, (bytes, bytearray)):
            data = json.loads(id_token.decode("utf-8"))
            email = data.get("email")
            return str(email).strip().lower() if email else None
        if isinstance(id_token, str) and "." not in id_token:
            data = json.loads(id_token)
            email = data.get("email")
            return str(email).strip().lower() if email else None
        if not isinstance(id_token, str):
            return None
        parts = id_token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        raw = base64.urlsafe_b64decode((payload + padding).encode("utf-8")).decode("utf-8")
        data = json.loads(raw)
        email = data.get("email")
        return str(email).strip().lower() if email else None
    except Exception:
        return None


def _fetch_google_userinfo_email(access_token):
    if not access_token:
        return None
    req = Request(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {str(access_token).strip()}"},
        method="GET",
    )
    try:
        with urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            email = payload.get("email")
            return str(email).strip().lower() if email else None
    except (HTTPError, URLError, TimeoutError, Exception):
        return None


def _require_login():
    mode = auth_access_mode()
    user_email = get_session_user()
    if user_email:
        user_norm = str(user_email).strip().lower()
        if mode == "normal":
            return user_email
        if mode == "demo_only" and DEMO_USER_EMAIL_NORM and user_norm == DEMO_USER_EMAIL_NORM:
            return user_email
        clear_session()
        if mode == "closed":
            st.warning("Accesso temporaneamente disabilitato per manutenzione.")
        else:
            st.info("Modalità demo attiva: accesso utenti temporaneamente disabilitato.")

    st.markdown("""
        <style>
        .login-spacer { height: 8vh; }
        .login-title {
            margin: 0 0 0.4rem 0;
            font-size: 2rem;
            letter-spacing: 0.03em;
            color: #e6eef9;
            font-family: "Space Grotesk", sans-serif;
            font-weight: 700;
            text-align: center;
        }
        .login-subtitle {
            margin: 0 0 1.5rem 0;
            color: rgba(230,238,249,0.7);
            font-size: 0.95rem;
            text-align: center;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<div class='login-spacer'></div>", unsafe_allow_html=True)
    _, center, _ = st.columns([1, 1.4, 1])

    with center:
        st.markdown("<h1 class='login-title'>💰 Personal Budget</h1>", unsafe_allow_html=True)
        st.markdown(
            "<p class='login-subtitle'>Accedi per esplorare la dashboard</p>",
            unsafe_allow_html=True,
        )

        if mode == "closed":
            st.warning("Accesso disabilitato. Riprova quando il servizio sarà riattivato.")
        elif IS_DEMO:
            user_flows_disabled = mode == "demo_only"
            tab_login, tab_register, tab_demo = st.tabs(["🔑 Accedi", "📝 Registrati", "🚀 Demo"])

            with tab_login:
                if user_flows_disabled:
                    st.info("Login utenti temporaneamente disattivato. Usa la tab Demo.")
                email_in = st.text_input("Email", key="login_email", disabled=user_flows_disabled)
                pwd_in = st.text_input("Password", type="password", key="login_pwd", disabled=user_flows_disabled)
                if st.button("Accedi", use_container_width=True, key="btn_login", disabled=user_flows_disabled):
                    if email_in and pwd_in:
                        ok, msg = login_email_password(email_in, pwd_in)
                        if ok:
                            st.success("Accesso effettuato!")
                            st.rerun()
                        else:
                            st.error(msg)
                    else:
                        st.warning("Inserisci email e password.")

            with tab_register:
                if user_flows_disabled:
                    st.info("Registrazione temporaneamente disattivata. Usa la tab Demo.")
                nome_reg = st.text_input("Nome ", key="reg_nome", disabled=user_flows_disabled)
                email_reg = st.text_input("Email", key="reg_email", disabled=user_flows_disabled)
                pwd_reg = st.text_input("Password", type="password", key="reg_pwd", disabled=user_flows_disabled)
                pwd_reg2 = st.text_input("Conferma password", type="password", key="reg_pwd2", disabled=user_flows_disabled)
                if st.button("Registrati", use_container_width=True, key="btn_register", disabled=user_flows_disabled):
                    if not email_reg or not pwd_reg:
                        st.warning("Compila email e password.")
                    elif pwd_reg != pwd_reg2:
                        st.error("Le password non coincidono.")
                    else:
                        ok, msg = register_demo_user(email_reg, pwd_reg, nome_reg)
                        if ok:
                            st.success("Registrazione completata! Ora accedi dalla tab 'Accedi'.")
                        else:
                            st.error(msg)

            with tab_demo:
                st.markdown(
                    "<p style='color:rgba(230,238,249,0.7); font-size:0.9rem;'>"
                    "Esplora tutte le funzionalità con dati di esempio. Nessuna registrazione richiesta.</p>",
                    unsafe_allow_html=True,
                )
                if user_flows_disabled:
                    st.caption("Modalità demo_only attiva: disponibile solo accesso demo.")
                if st.button("▶ Entra in modalità Demo", use_container_width=True, key="btn_demo"):
                    if DEMO_USER_EMAIL:
                        ok = create_demo_session(DEMO_USER_EMAIL)
                        if ok:
                            st.session_state["is_demo_guest"] = True
                            st.rerun()
                    else:
                        st.error("Credenziali demo non configurate nei secrets.")

        else:
            if mode == "demo_only":
                st.warning("Modalità demo_only attiva ma APP_ENV non è demo.")
                st.stop()
            if OAuth2Component is None:
                st.error("Modulo mancante: installa `streamlit-oauth`.")
                st.stop()
            if not client_id or not client_secret:
                st.error("Credenziali OAuth mancanti.")
                st.stop()

            login_clicked = st.button(
                "Accedi con Google", key="google_login_custom", use_container_width=True
            )
            oauth2 = OAuth2Component(
                client_id, client_secret, AUTHORIZE_URL, TOKEN_URL, TOKEN_URL, ""
            )
            if login_clicked:
                st.session_state["oauth_auto_click"] = True
                st.rerun()

            auto_click = bool(st.session_state.pop("oauth_auto_click", False))
            redirect_uri = _resolve_redirect_uri()
            if not redirect_uri:
                st.error("APP_BASE_URL non configurato.")
                st.stop()

            result = oauth2.authorize_button(
                name="Accedi con Google",
                scope="openid email profile",
                redirect_uri=redirect_uri,
                key="google_login_hidden",
                auto_click=auto_click,
                use_container_width=True,
                extras_params={"prompt": "select_account"},
            )
            if result:
                id_token = result.get("id_token")
                if not id_token and isinstance(result.get("token"), dict):
                    id_token = result["token"].get("id_token")
                email_google = _decode_id_token_email(id_token)
                if not email_google:
                    access_token = result.get("access_token")
                    if not access_token and isinstance(result.get("token"), dict):
                        access_token = result["token"].get("access_token")
                    email_google = _fetch_google_userinfo_email(access_token)
                if create_new_session(email_google):
                    try:
                        st.query_params.clear()
                    except Exception:
                        pass
                    st.success("Accesso autorizzato.")
                    st.rerun()
                if not email_google:
                    st.error("Impossibile leggere l'email dal profilo Google.")

    st.stop()


# --- CSS PERSONALIZZATO (Nuovo tema) ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500&display=swap');

:root {
    --bg:          #07090F; /* sfondo principale */
    --bg-surf:     #0c1120;
    --bg-card:     #0c1120; /* sfondo card e grafici */
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

/* ── BASE ── */
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
/*l'header in corrispondenza Deploy Streamlit */
[data-testid="stHeader"] {
    border-bottom: none !important;
    background: #07090F !important;
    backdrop-filter: none !important;
}
/* Toolbar con i pulsanti Deploy ecc. */
[data-testid="stToolbar"],
header[data-testid="stHeader"] > div {
    background: #07090F !important;
}

/* ── SIDEBAR ── */
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
/* Bottone Logout nella sidebar */
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

/* ── TIPOGRAFIA ── */
h1, h2, h3, h4, h5, h6 {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    color: var(--txt) !important;
    letter-spacing: -0.2px;
}

/* ── BLOCK CONTAINER ── */
.block-container {
    padding-top: 1.6rem !important;
    padding-bottom: 1rem !important;
}
.element-container { margin-bottom: 0rem; }

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
div[data-testid="stMetric"]:hover {
    border-color: var(--bdr-md) !important;
}
/* barra colorata in fondo a ciascuna KPI */
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
.js-plotly-plot .xtick text,
.js-plotly-plot .ytick text,
.js-plotly-plot .g-xtitle text,
.js-plotly-plot .g-ytitle text {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-weight: 700 !important;
}

/* ── DATAFRAME / TABLE ── */
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
/* header colonne dataframe */
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
/* righe hover */
.stDataFrame tr:hover td { background: rgba(79,142,240,0.06) !important; }

/* ── 1. INPUT, SELECTBOX, TEXTAREA ── */
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
/* Dropdown option list delle selectbox */
[data-baseweb="popover"] [data-baseweb="menu"],
[data-baseweb="select"] [role="listbox"],
ul[data-baseweb="menu"] {
    background-color: #090E1B !important;
    border: 1px solid var(--bdr) !important;
}
[data-baseweb="option"]:hover {
    background-color: rgba(79,142,240,0.12) !important;
}

/* ── CONTAINER con bordo (form, card, ecc.) ── */
/* Specificità alta: html body prefix per battere gli stili inline di Streamlit */
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
/* Blocchi interni → trasparenti per evitare doppio sfondo */
html body [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"],
html body [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stHorizontalBlock"],
html body [data-testid="stForm"] [data-testid="stVerticalBlock"] {
    background-color: transparent !important;
}
/* Markup e testo interni → trasparenti */
html body [data-testid="stVerticalBlockBorderWrapper"] .stMarkdown,
html body [data-testid="stVerticalBlockBorderWrapper"] .stMarkdown div {
    background-color: transparent !important;
}

/* ── PULSANTI PRINCIPALI ── */
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

/* ── DOWNLOAD BUTTON ── */
[data-testid="stDownloadButton"] > button {
    background: transparent !important;
    border: 1px solid var(--bdr) !important;
    border-radius: 8px !important;
    color: var(--txt) !important;
    font-size: 0.82rem !important;
}
[data-testid="stDownloadButton"] > button:hover {
    border-color: var(--bdr-md) !important;
    color: var(--txt) !important;
}

/* ── CHECKBOX ── */
[data-testid="stCheckbox"] label {
    color: var(--txt-mid) !important;
    font-size: 0.8rem !important;
}
[data-testid="stCheckbox"] span[aria-checked] {
    background: var(--acc) !important;
    border-color: var(--acc) !important;
}

/* ── DIVIDER ── */
hr {
    border-color: var(--bdr) !important;
    margin: 1rem 0 !important;
}

/* ── CAPTION / HELPER TEXT ── */
.stCaption, [data-testid="stCaptionContainer"] {
    color: var(--txt) !important;
    font-size: 0.75rem !important;
}

/* ── EXPANDER ── */
[data-testid="stExpander"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--bdr) !important;
    border-radius: 10px !important;
}
[data-testid="stExpander"]:hover {
    border-color: var(--bdr-md) !important;
}
[data-testid="stExpander"] summary {
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    color: var(--txt) !important;
    background: rgba(79,142,240,0.04) !important;
    border-radius: 10px 10px 0 0 !important;
}

/* ── ALERT / INFO / WARNING / SUCCESS ── */
[data-testid="stAlert"] {
    border-radius: 9px !important;
    border-left-width: 3px !important;
    font-size: 0.82rem !important;
}

/* ── CUSTOM CLASSES (badge, chip, section-title) ── */
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

/* sidebar residuo mese */
.side-title {
    font-weight: 700;
    font-size: 0.75rem;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: var(--txt-mid);
    margin: 1rem 0 0.4rem 0;
}
.side-chip {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    border: 1px solid rgba(79,142,240,0.3);
    color: var(--acc-lt);
    background: var(--acc-dim);
    font-weight: 600;
    font-size: 0.78rem;
    font-family: 'JetBrains Mono', monospace;
    margin-bottom: 0.5rem;
}
.side-residuo {
    background: var(--bg-card);
    border: 1px solid rgba(16,217,138,0.35);
    border-radius: 10px;
    padding: 10px 13px;
    text-align: center;
    color: var(--green);
    font-weight: 700;
    font-size: 1.1rem;
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: 0.02em;
    box-shadow: 0 4px 16px rgba(0,0,0,0.3);
}
.side-residuo.neg { border-color: rgba(242,106,106,0.4); color: var(--red); }
.side-residuo .label {
    display: block;
    font-size: 0.65rem;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    font-family: 'Plus Jakarta Sans', sans-serif;
    color: var(--txt-mid);
    margin-bottom: 5px;
    font-weight: 600;
}
.side-residuo .pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(16,217,138,0.15);
    border: 1px solid rgba(16,217,138,0.4);
    color: var(--green);
    padding: 5px 12px;
    border-radius: 20px;
    font-weight: 700;
    font-size: 1rem;
    font-family: 'JetBrains Mono', monospace;
}
.side-residuo.neg .pill {
    background: rgba(242,106,106,0.15);
    border-color: rgba(242,106,106,0.4);
    color: var(--red);
}

/* progress bar */
.progress-wrap { margin-top: 5px; }
.progress-track {
    width: 100%;
    height: 8px;
    background: rgba(255,255,255,0.07);
    border-radius: 999px;
    overflow: hidden;
}
.progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--green) 0%, #34d399 100%);
    border-radius: 999px;
}
/* ── FIX INTERNO: testi e markup dentro i container rimangono trasparenti ── */
[data-testid="stVerticalBlockBorderWrapper"] .stMarkdown div {
    background-color: transparent !important;
}

/* ── FORM submit button full width ── */
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
</style>
""", unsafe_allow_html=True)

# --- RESET KPI DENTRO I TAB (Patrimonio, Analisi, ecc.) ---
# I 4 KPI principali ora sono HTML custom → nessun colore da iniettare su st.metric.
# Qui resettiamo le metric dentro i tab allo stile compatto desiderato.
st.markdown("""
<style>
/* ── Metric dentro i tab: stile compatto, bianco, allineato a sinistra ── */
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
/* Rimuove il centramento globale dentro i tab */
[data-testid="stTabsTabPanel"] div[data-testid="stMetric"] {
    text-align: left !important;
}
</style>
""", unsafe_allow_html=True)

# --- AVVIO APP ---
@st.cache_resource
def _ensure_db_ready():
    db.inizializza_db()
    return True


_ensure_db_ready()
try:
    db.pulisci_sessioni_scadute()
except Exception:
    pass

AUTH_USER_EMAIL = _require_login()
user_email = AUTH_USER_EMAIL
# Banner demo_only: visibile solo quando accede l'account demo.
is_demo_account = False
if IS_DEMO:
    current_email_norm = str(AUTH_USER_EMAIL or "").strip().lower()
    demo_email_norm = str(DEMO_USER_EMAIL or "").strip().lower()
    is_demo_account = bool(demo_email_norm and current_email_norm == demo_email_norm)
    st.session_state["is_demo_guest"] = is_demo_account
    if is_demo_account:
        st.info(
            "👁️ **Modalità Demo** — Stai esplorando l'app con dati di esempio. ",
            icon="ℹ️",
        )
    
NOME_DISPLAY = AUTH_USER_EMAIL.split('@')[0].upper()  # default sicuro
if not IS_DEMO:
    # In produzione leggiamo il nome dalla whitelist
    try:
        with db.connetti_db() as conn:
            res = pd.read_sql(
                "SELECT nome_utente FROM whitelist WHERE email = %s",
                conn,
                params=(AUTH_USER_EMAIL,),   # query parametrizzata, no injection
            )
            if not res.empty and res['nome_utente'].iloc[0]:
                NOME_DISPLAY = res['nome_utente'].iloc[0]
    except Exception:
        pass  # se la whitelist non esiste o la query fallisce, usiamo il default
else:
    # In demo: per account reale leggiamo da utenti_registrati; per account demo da utenti_demo.
    try:
        if is_demo_account:
            with db.connetti_db() as conn:
                res = pd.read_sql(
                    "SELECT nome_utente FROM utenti_demo WHERE email = %s",
                    conn,
                    params=(AUTH_USER_EMAIL,),
                )
                if not res.empty and res['nome_utente'].iloc[0]:
                    NOME_DISPLAY = res['nome_utente'].iloc[0].upper()
        else:
            with db.connetti_db() as conn:
                res = pd.read_sql(
                    "SELECT nome_utente FROM utenti_registrati WHERE email = %s",
                    conn,
                    params=(AUTH_USER_EMAIL,),
                )
                if not res.empty and res['nome_utente'].iloc[0]:
                    NOME_DISPLAY = res['nome_utente'].iloc[0].upper()
    except Exception:
        pass

# --- CARICAMENTO DATI ---
df_mov = db.carica_dati(user_email)
if df_mov.empty:
    st.warning("Nessun movimento trovato nel database. Utilizza il Tab Registro per aggiungere movimenti.")

df_mov.columns = [c.capitalize() for c in df_mov.columns]
if "Data" in df_mov:
    # Garantisce dtype datetime anche con DataFrame vuoto o dati sporchi.
    df_mov["Data"] = pd.to_datetime(df_mov["Data"], errors="coerce")
else:
    df_mov["Data"] = pd.Series(pd.NaT, index=df_mov.index, dtype="datetime64[ns]")
if "Tipo" in df_mov:
    df_mov["Tipo"] = df_mov["Tipo"].astype(str).str.upper().str.strip()
    df_mov["Tipo"] = df_mov["Tipo"].replace({
        "ENTRATE": "ENTRATA",
        "USCITE": "USCITA",
    })
if "Categoria" in df_mov:
    df_mov["Categoria"] = df_mov["Categoria"].astype(str).str.upper().str.strip()

def _load_settings_df():
    try:
        with db.connetti_db() as conn_local:
            df = pd.read_sql(
                "SELECT chiave, valore_numerico, valore_testo "
                "FROM asset_settings WHERE user_email = %s",
                conn_local,
                params=(user_email,),
            )
        if df.empty:
            return pd.DataFrame(columns=["valore_numerico", "valore_testo"]).set_index(pd.Index([]))
        df = df.drop_duplicates(subset=["chiave"], keep="last")
        return df.set_index("chiave")
    except Exception:
        return pd.DataFrame(columns=["valore_numerico", "valore_testo"]).set_index(pd.Index([]))


def _save_settings_batch(num_payload=None, txt_payload=None):
    num_payload = num_payload or {}
    txt_payload = txt_payload or {}
    if not user_email:
        return False, "Utente non autenticato."
    try:
        with db.connetti_db() as conn_local:
            cur = conn_local.cursor()
            upsert_q = """
                INSERT INTO asset_settings (chiave, user_email, valore_numerico, valore_testo)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (chiave, user_email) DO UPDATE SET
                    valore_numerico = EXCLUDED.valore_numerico,
                    valore_testo = EXCLUDED.valore_testo
            """
            for key, value in num_payload.items():
                cur.execute(upsert_q, (str(key), user_email, float(value) if value is not None else None, None))
            for key, value in txt_payload.items():
                cur.execute(upsert_q, (str(key), user_email, None, str(value) if value is not None else ""))
            cur.close()
        return True, ""
    except Exception as e:
        return False, str(e)


def _verify_settings_batch(settings_df, num_payload=None, txt_payload=None):
    num_payload = num_payload or {}
    txt_payload = txt_payload or {}
    errors = []
    for key, expected in num_payload.items():
        if key not in settings_df.index:
            errors.append(f"{key}: chiave non trovata")
            continue
        actual = settings_df.loc[key, "valore_numerico"]
        if pd.isna(actual):
            errors.append(f"{key}: valore numerico nullo")
            continue
        if abs(float(actual) - float(expected)) > 1e-6:
            errors.append(f"{key}: atteso {expected}, trovato {actual}")
    for key, expected in txt_payload.items():
        if key not in settings_df.index:
            errors.append(f"{key}: chiave non trovata")
            continue
        actual = settings_df.loc[key, "valore_testo"]
        actual_s = "" if pd.isna(actual) else str(actual)
        expected_s = "" if expected is None else str(expected)
        if actual_s != expected_s:
            errors.append(f"{key}: atteso '{expected_s}', trovato '{actual_s}'")
    return errors


settings = _load_settings_df()
df_fin_db = db.carica_finanziamenti(user_email)

# Defaults automatici (solo se mancanti)
anno_default = datetime.now().year
anno_prev_default = anno_default - 1
defaults_num = {
    "obiettivo_risparmio_perc": 30.0,
    "saldo_fineco": 25995.0,
    "saldo_revolut": 2400.0,
    "pac_quote": 0.0,
    "pac_capitale_investito": 0.0,
    "pac_versamento_mensile": 80.0,
    "pac_rendimento_stimato": 7.0,
    "fondo_quote": 0.0,
    "fondo_capitale_investito": 0.0,
    "fondo_versamento_mensile": 50.0,
    "fondo_valore_quota": 7.28,
    "fondo_rendimento_stimato": 5.0,
    "aliquota_irpef": 0.26,
    f"saldo_iniziale_{anno_default}": 26482.0,
    f"risparmio_precedente_{anno_prev_default}": 5657.0,
    "budget_mensile_base": 1600.0,
}
updated = False
for k, v in defaults_num.items():
    if k not in settings.index or pd.isna(settings.loc[k, "valore_numerico"]):
        db.imposta_parametro(k, valore_num=v, valore_txt=None, user_email=user_email)
        updated = True

defaults_txt = {
    "pac_ticker": "VNGA80",
}
for k, v in defaults_txt.items():
    if k not in settings.index or pd.isna(settings.loc[k, "valore_testo"]):
        db.imposta_parametro(k, valore_num=None, valore_txt=v, user_email=user_email)
        updated = True

if updated:
    settings = _load_settings_df()

# --- HELPERS ---
MONTH_NAMES = {
    1: "GENNAIO", 2: "FEBBRAIO", 3: "MARZO", 4: "APRILE", 5: "MAGGIO", 6: "GIUGNO",
    7: "LUGLIO", 8: "AGOSTO", 9: "SETTEMBRE", 10: "OTTOBRE", 11: "NOVEMBRE", 12: "DICEMBRE",
}
MONTH_SHORT = {
    1: "Gen", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mag", 6: "Giu",
    7: "Lug", 8: "Ago", 9: "Set", 10: "Ott", 11: "Nov", 12: "Dic",
}
COLOR_SEQ = ["#facc15", "#60a5fa", "#34d399", "#fb7185", "#a78bfa", "#f472b6", "#22c55e"]

def s_num(key, default=0.0):
    try:
        val = settings.loc[key, "valore_numerico"]
        return float(val) if pd.notna(val) else default
    except Exception:
        return default

def s_txt(key, default=""):
    try:
        val = settings.loc[key, "valore_testo"]
        return str(val) if pd.notna(val) else default
    except Exception:
        return default


def s_num_candidates(keys, default=0.0):
    for key in keys:
        try:
            val = settings.loc[key, "valore_numerico"]
            if pd.notna(val):
                return float(val)
        except Exception:
            continue
    return default

PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}

def format_eur(value, decimals=0, signed=False):
    if value is None:
        return ""
    try:
        val = float(value)
    except Exception:
        return ""
    sign = "-" if signed and val < 0 else ""
    val = abs(val) if signed else val
    s = f"{val:,.{decimals}f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    if decimals == 0:
        s = s.split(",")[0]
    return f"{sign}€ {s}"

def eur0(value, signed=False):
    return format_eur(value, decimals=0, signed=signed)

def eur2(value, signed=False):
    return format_eur(value, decimals=2, signed=signed)

def hex_to_rgba(hex_color, alpha=None):
    """
    Converte HEX (6 o 8 cifre) in colore Plotly.
    - 6 cifre: usa alpha passato (default 0.1).
    - 8 cifre: usa alpha incorporato se non specificato.
    """
    raw = str(hex_color or "").strip().lstrip("#")
    try:
        if len(raw) == 8:
            r = int(raw[0:2], 16)
            g = int(raw[2:4], 16)
            b = int(raw[4:6], 16)
            a_embedded = round(int(raw[6:8], 16) / 255, 2)
            a = a_embedded if alpha is None else alpha
            return f"rgba({r},{g},{b},{a})"
        if len(raw) == 6:
            r = int(raw[0:2], 16)
            g = int(raw[2:4], 16)
            b = int(raw[4:6], 16)
            a = 0.1 if alpha is None else alpha
            return f"rgba({r},{g},{b},{a})"
    except Exception:
        pass
    fallback_alpha = 0.1 if alpha is None else alpha
    return f"rgba(255,255,255,{fallback_alpha})"

def style_df_currency(df, currency_cols):
    if df is None or df.empty:
        return df
    fmt = {}
    for col in currency_cols:
        if col in df.columns:
            fmt[col] = lambda x: format_eur(x, decimals=2)
    if not fmt:
        return df
    return df.style.format(fmt)


def style_calendario_scadenze(df):
    """Evidenzia righe calendario con i colori semantici del nuovo tema."""
    if df is None or df.empty:
        return df

    sty = style_df_currency(df, ["Importo"])
    if not hasattr(sty, "apply"):
        return sty

    def _row_style(row):
        stato = str(row.get("Stato", "")).upper()
        if "PAGATO" in stato:
            return [
                "background-color: rgba(16,217,138,0.09);"
                "border-left: 3px solid #10d98a;"
                for _ in row
            ]
        if "IN SCADENZA" in stato:
            return [
                "background-color: rgba(245,166,35,0.09);"
                "border-left: 3px solid #f5a623;"
                for _ in row
            ]
        if "DA PAGARE" in stato:
            return [
                "background-color: rgba(242,106,106,0.08);"
                "border-left: 3px solid #f26a6a;"
                for _ in row
            ]
        return ["" for _ in row]

    return sty.apply(_row_style, axis=1)

def style_finanziamento(df):
    if df is None or df.empty:
        return df
    fmt = {}
    if "Rata" in df.columns:
        fmt["Rata"] = lambda x: format_eur(x, decimals=2)
    if "Residuo" in df.columns:
        fmt["Residuo"] = lambda x: format_eur(x, decimals=2)
    if "% Completato" in df.columns:
        fmt["% Completato"] = lambda x: f"{x:.1f}%"
    if not fmt:
        return df
    return df.style.format(fmt)

def _fin_match_pattern(nome_fin):
    if not nome_fin:
        return None
    raw = str(nome_fin).strip()
    tokens = [raw]
    if "." in raw:
        tokens.append(raw.split(".")[-1])
    tokens.append(re.sub(r"^fin\\.?\\s*", "", raw, flags=re.I))
    # Aggiunge i token testuali (es. "Prestito Auto" -> "Prestito", "Auto")
    for t in re.split(r"[\s\-_/.]+", raw):
        t = t.strip()
        if len(t) >= 3:
            tokens.append(t)
    tokens = [t.strip() for t in tokens if t and t.strip()]
    tokens = list(dict.fromkeys(tokens))
    if not tokens:
        return None
    return "|".join(re.escape(t) for t in tokens)

def _mesi_pagati_da_mov(df_mov, nome_fin, rata, data_inizio=None):
    if df_mov is None or df_mov.empty:
        return None
    needed = {"Tipo", "Dettaglio", "Note", "Importo", "Data"}
    if not needed.issubset(set(df_mov.columns)):
        return None
    pattern = _fin_match_pattern(nome_fin)
    if not pattern:
        return None
    tipo = df_mov["Tipo"].astype(str).str.upper().str.strip()
    mask = (tipo == "USCITA") & (
        df_mov["Dettaglio"].astype(str).str.contains(pattern, case=False, na=False) |
        df_mov["Note"].astype(str).str.contains(pattern, case=False, na=False)
    )
    df = df_mov[mask].copy()
    if df.empty:
        return None
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df[df["Data"].notna()].copy()
    if df.empty:
        return None
    # Considera solo movimenti dal primo giorno di inizio finanziamento
    if data_inizio is not None:
        inizio = pd.to_datetime(data_inizio, errors="coerce")
        if pd.notna(inizio):
            df = df[df["Data"] >= inizio]
            if df.empty:
                return None
    rata_abs = abs(float(rata)) if rata is not None else 0.0
    if rata_abs > 0:
        tol = max(1.0, rata_abs * 0.25)
        df = df[df["Importo"].abs().between(rata_abs - tol, rata_abs + tol)]
    if df.empty:
        return None
    # Conteggio rate pagate reali: una riga movimento ~= una rata pagata.
    return int(len(df))

def style_fig(fig, title=None, height=300, show_legend=True):
    layout_kwargs = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family="'Plus Jakarta Sans', sans-serif",
            color="#dde6f5",
            size=12,
        ),
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="left",   x=0,
            font=dict(size=11, color="#5a6f8c"),
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
            font=dict(size=13, color="#dde6f5", family="'Plus Jakarta Sans', sans-serif"),
        )
    else:
        layout_kwargs["title_text"] = ""
    fig.update_layout(**layout_kwargs)
    fig.update_xaxes(
        showgrid=True,
        gridcolor="rgba(79,142,240,0.08)",
        zeroline=False,
        tickfont=dict(size=11, color="#7a8db3", family="'Plus Jakarta Sans', sans-serif"),
    )
    fig.update_yaxes(
        showgrid=False,
        gridcolor="rgba(79,142,240,0.08)",
        zeroline=False,
        tickfont=dict(size=11, color="#7a8db3", family="'Plus Jakarta Sans', sans-serif"),
    )
    return fig
def render_calendario_html(df):
    """Renderizza il calendario spese ricorrenti come tabella HTML stilizzata."""
    if df is None or df.empty:
        return "<p style='color:#5a6f8c;font-size:0.82rem;'>Nessuna spesa prevista.</p>"

    def _chip_stato(stato):
        s = str(stato).upper()
        if "PAGATO" in s:
            return ("<span style='display:inline-flex;align-items:center;gap:4px;"
                    "padding:3px 10px;border-radius:20px;font-size:0.72rem;font-weight:700;"
                    "background:rgba(16,217,138,0.12);color:#10d98a;"
                    "border:1px solid rgba(16,217,138,0.3);'>"
                    "<span style='width:5px;height:5px;border-radius:50%;"
                    "background:#10d98a;display:inline-block;'></span>"
                    " ✓ Pagato</span>")
        if "IN SCADENZA" in s:
            return ("<span style='display:inline-flex;align-items:center;gap:4px;"
                    "padding:3px 10px;border-radius:20px;font-size:0.72rem;font-weight:700;"
                    "background:rgba(245,166,35,0.12);color:#f5a623;"
                    "border:1px solid rgba(245,166,35,0.3);'>"
                    "<span style='width:5px;height:5px;border-radius:50%;"
                    "background:#f5a623;display:inline-block;'></span>"
                    " ⚠ In scadenza</span>")
        return ("<span style='display:inline-flex;align-items:center;gap:4px;"
                "padding:3px 10px;border-radius:20px;font-size:0.72rem;font-weight:700;"
                "background:rgba(242,106,106,0.10);color:#f26a6a;"
                "border:1px solid rgba(242,106,106,0.25);'>"
                "<span style='width:5px;height:5px;border-radius:50%;"
                "background:#f26a6a;display:inline-block;'></span>"
                " Da pagare</span>")

    def _chip_freq(freq):
        return (f"<span style='display:inline-flex;align-items:center;"
                f"padding:3px 9px;border-radius:20px;font-size:0.72rem;font-weight:600;"
                f"background:rgba(79,142,240,0.10);color:#82b4f7;"
                f"border:1px solid rgba(79,142,240,0.25);'>{freq}</span>")

    def _row_bg(stato):
        s = str(stato).upper()
        if "PAGATO" in s:
            return "background:rgba(16,217,138,0.07);border-left:3px solid #10d98a;"
        if "IN SCADENZA" in s:
            return "background:rgba(245,166,35,0.07);border-left:3px solid #f5a623;"
        return "background:rgba(242,106,106,0.06);border-left:3px solid #f26a6a;"

    cols = ["Spesa Prevista", "Importo", "Giorno Previsto",
            "Data Fine Prevista", "Stato", "Frequenza"]

    header_cells = "".join(
        f"<th style='padding:8px 13px;font-size:0.68rem;font-weight:700;"
        f"letter-spacing:1px;text-transform:uppercase;color:#5a6f8c;"
        f"text-align:left;background:rgba(0,0,0,0.18);"
        f"border-bottom:1px solid rgba(79,142,240,0.12);white-space:nowrap;'>{c}</th>"
        for c in cols
    )

    rows_html = ""
    for _, row in df.iterrows():
        stato_val = str(row.get("Stato", ""))
        bg = _row_bg(stato_val)
        importo_fmt = format_eur(row.get("Importo", 0), decimals=2)
        giorno = int(row.get("Giorno Previsto", 0))
        cells = [
            f"<td style='padding:10px 13px;font-size:0.85rem;color:#dde6f5;'>{row.get('Spesa Prevista','')}</td>",
            f"<td style='padding:10px 13px;font-family:\"JetBrains Mono\",monospace;font-size:0.82rem;color:#f26a6a;'>{importo_fmt}</td>",
            f"<td style='padding:10px 13px;font-family:\"JetBrains Mono\",monospace;font-size:0.82rem;color:#5a6f8c;'>{giorno}</td>",
            f"<td style='padding:10px 13px;font-size:0.82rem;color:#5a6f8c;'>{row.get('Data Fine Prevista','')}</td>",
            f"<td style='padding:10px 13px;'>{_chip_stato(stato_val)}</td>",
            f"<td style='padding:10px 13px;'>{_chip_freq(str(row.get('Frequenza','Mensile')))}</td>",
        ]
        rows_html += (
            f"<tr style='{bg}border-bottom:1px solid rgba(79,142,240,0.05);'>"
            + "".join(cells) + "</tr>"
        )

    totale = format_eur(df["Importo"].sum(), decimals=2)
    n = df.shape[0]

    return f"""
<div style="border:1px solid rgba(79,142,240,0.12);border-radius:9px;overflow:hidden;margin-top:4px;">
  <div style="display:flex;align-items:center;justify-content:space-between;
              padding:9px 14px;background:rgba(79,142,240,0.04);
              border-bottom:1px solid rgba(79,142,240,0.12);">
    <span style="font-size:0.68rem;font-weight:700;letter-spacing:1.2px;
                 text-transform:uppercase;color:#5a6f8c;">
      Spese pianificate — {n} voci
    </span>
    <span style="font-family:'JetBrains Mono',monospace;font-size:0.82rem;color:#82b4f7;">
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

def _chip(label, color, bg, border, size="0.72rem", padding="3px 11px", weight=700):
    return (
        f"<span class='reg-chip' style='background:{bg};color:{color};"
        f"border:1px solid {border};font-size:{size};font-weight:{weight};"
        f"padding:{padding};'>{escape(str(label))}</span>"
    )

def _th(txt, align="left"):
    justify = {"left": "flex-start", "center": "center", "right": "flex-end"}.get(align, "flex-start")
    return (
        f"<div style='min-height:36px;display:flex;align-items:center;justify-content:{justify};"
        f"padding:8px 6px;font-size:0.68rem;font-weight:700;letter-spacing:1px;"
        f"text-transform:uppercase;color:#7a8db3;text-align:{align};background:var(--table-bg);"
        f"border-bottom:1px solid rgba(128,160,232,0.34);'>{escape(str(txt))}</div>"
    )

def _td(txt, mono=False, color="#dde6f5", size="0.92rem", align="left", weight=500, border=True):
    justify = {"left": "flex-start", "center": "center", "right": "flex-end"}.get(align, "flex-start")
    font = "font-family:'JetBrains Mono',monospace;" if mono else "font-family:'Plus Jakarta Sans',sans-serif;"
    border_css = "1px solid rgba(128,160,232,0.28)" if border else "none"
    return (
        f"<div style='min-height:58px;display:flex;align-items:center;justify-content:{justify};"
        f"padding:10px 6px;font-size:{size};font-weight:{weight};line-height:1.18;"
        f"text-align:{align};background:var(--table-bg);{font}color:{color};border-bottom:{border_css};'>{txt}</div>"
    )

def _tipo_chip(tipo):
    tipo_norm = str(tipo or "").strip().upper()
    if tipo_norm == "ENTRATA":
        return _chip("ENTRATA", "#10d98a", "rgba(16,217,138,0.12)", "rgba(16,217,138,0.28)")
    return _chip("USCITA", "#f26a6a", "rgba(242,106,106,0.12)", "rgba(242,106,106,0.28)")

def _reg_table_td(content, align="left", color="#dde6f5", mono=False, weight=400, nowrap=True, title=None):
    font = "font-family:'JetBrains Mono',monospace;font-size:0.78rem;" if mono else "font-family:'Plus Jakarta Sans',sans-serif;font-size:0.875rem;"
    white = "white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" if nowrap else "white-space:normal;"
    title_attr = f" title='{escape(str(title))}'" if title else ""
    return (
        f"<td style='text-align:{align};color:{color};"
        f"font-weight:{weight};{font}{white}'{title_attr}>{content}</td>"
    )

def _reg_table_row(cells):
    return "<tr>" + "".join(cells) + "</tr>"

def _reg_table_colgroup(widths):
    total = float(sum(widths) or 1)
    return "".join(
        f"<col style='width:{(w / total) * 100:.4f}%;'>"
        for w in widths
    )

def _reg_table_th(label, align="left"):
    return f"<th style='text-align:{align};'>{escape(str(label))}</th>"

def _render_reg_scroll_table(title, right_html, columns, widths, rows_html, height_px=320, empty_message="Nessun dato disponibile."):
    if not rows_html:
        rows_html = [
            f"<tr><td class='reg-html-empty' colspan='{len(columns)}'>{escape(empty_message)}</td></tr>"
        ]
    headers = "".join(_reg_table_th(label, align) for label, align in columns)
    return f"""
<div class="reg-html-shell">
  <div class="reg-html-bar">
    <span class="reg-html-bar-title">{escape(str(title))}</span>
    <span class="reg-html-bar-value">{right_html}</span>
  </div>
  <div class="reg-html-scroll" style="max-height:{int(height_px)}px;">
    <table class="reg-html-table">
      <colgroup>{_reg_table_colgroup(widths)}</colgroup>
      <thead><tr>{headers}</tr></thead>
      <tbody>{''.join(rows_html)}</tbody>
    </table>
  </div>
</div>
"""

def show_chart(fig, height=300, show_legend=True):
    fig.update_traces(textfont=dict(size=12))
    st.plotly_chart(style_fig(fig, height=height, show_legend=show_legend), use_container_width=True, config=PLOTLY_CONFIG)

def badge(text, variant=""):
    cls = f"badge {variant}".strip()
    return f"<span class='{cls}'>{text}</span>"
def _fmt_num_it(value, decimals=2):
    """Formatta un numero con separatore italiano."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    s = f"{v:,.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")

def _dialog_elimina_movimento(mov_id, label):
    st.warning("Stai per eliminare il seguente movimento:")
    st.markdown(f"**{label}**")
    st.markdown("Questa operazione è **irreversibile**. Vuoi procedere?")
    c1, c2 = st.columns(2)
    if c1.button("🗑️ Sì, elimina", use_container_width=True, type="primary"):
        db.elimina_movimento(mov_id, user_email)
        db.carica_dati.clear()
        st.session_state["_success_mov_ts"] = datetime.now().timestamp()
        st.rerun()
    if c2.button("Annulla", use_container_width=True):
        st.rerun()

def _dialog_elimina_ricorrente(spesa_id, descrizione):
    st.warning("Stai per eliminare la seguente spesa ricorrente:")
    st.markdown(f"**{descrizione}**")
    st.markdown("Questa operazione è **irreversibile**. Vuoi procedere?")
    c1, c2 = st.columns(2)
    if c1.button("🗑️ Sì, elimina", use_container_width=True, type="primary"):
        db.elimina_spesa_ricorrente(spesa_id, user_email)
        db.carica_spese_ricorrenti.clear()
        st.session_state["_success_ric_ts"] = datetime.now().timestamp()
        st.rerun()
    if c2.button("Annulla", use_container_width=True):
        st.rerun()

def _dialog_elimina_finanziamento(nome):
    st.warning("Stai per eliminare il seguente finanziamento:")
    st.markdown(f"**{nome}**")
    st.markdown("Questa operazione è **irreversibile**. Vuoi procedere?")
    c1, c2 = st.columns(2)
    if c1.button("🗑️ Sì, elimina", use_container_width=True, type="primary"):
        db.elimina_finanziamento(nome, user_email)
        db.carica_finanziamenti.clear()
        st.session_state["_success_fin_ts"] = datetime.now().timestamp()
        st.rerun()
    if c2.button("Annulla", use_container_width=True):
        st.rerun()

# --- SIDEBAR DI CONTROLLO ---
st.sidebar.image("https://www.dropbox.com/scl/fi/hw4minjcf7zow3cbthozn/Screenshot-2026-02-12-alle-23.11.51.png?rlkey=lfxfvev6mtxeq6n5lwx7l6t8f&st=dckyjooz&raw=1", width=90)
st.sidebar.markdown(f"""
    <div style="line-height: 1.5; margin-top: 8px;">
        <span style="font-size: 0.85rem; color: #ffffff; font-weight: bold;">Accesso effettuato:</span>
        <span style="font-size: 0.85rem; color: #60a5fa; font-weight: bold; word-break: break-all; margin-left: 5px;">{AUTH_USER_EMAIL}</span>
    </div>
    """, unsafe_allow_html=True)
if st.sidebar.button("Logout"):
    clear_session()
    st.rerun()
st.sidebar.title("Parametri")

# --- SALDO REALE ---
allineamento = s_num("allineamento_saldo", 0.0)
saldo_calcolato = df_mov[df_mov["Tipo"] == "ENTRATA"]["Importo"].sum() - df_mov[df_mov["Tipo"] == "USCITA"]["Importo"].sum()
saldo_reale = saldo_calcolato + allineamento

if not df_mov.empty:
    anni_disponibili = sorted(df_mov["Data"].dt.year.unique())
else:
    anni_disponibili = [datetime.now().year]

def_anno = anni_disponibili.index(datetime.now().year) if datetime.now().year in anni_disponibili else len(anni_disponibili) - 1
anno_sel = st.sidebar.selectbox("Anno di analisi", anni_disponibili, index=def_anno)
mese_sel = st.sidebar.slider("Mese", 1, 12, datetime.now().month)

with st.sidebar.expander("Impostazioni rapide", expanded=False):
    prev_year = anno_sel - 1
    risp_prev_key = f"risparmio_precedente_{prev_year}"
    saldo_iniziale_key = f"saldo_iniziale_{anno_sel}"
    risp_prev_candidates = [
        risp_prev_key,
        f"risparmio_precedente_{anno_sel}",
        f"risparmio precedente_{anno_sel}",
        f"risparmio precedente_{prev_year}",
    ]
    saldo_iniziale_candidates = [
        saldo_iniziale_key,
        f"saldo iniziale_{anno_sel}",
    ]
    if "quick_settings_saved_msg" in st.session_state:
        st.success(st.session_state.pop("quick_settings_saved_msg"))
    if "quick_settings_saved_err" in st.session_state:
        st.error(st.session_state.pop("quick_settings_saved_err"))
    last_saved_txt = s_txt("quick_settings_last_saved_at", "")
    if last_saved_txt:
        st.caption(f"Ultimo salvataggio: {last_saved_txt}")

    with st.form("quick_settings_form", clear_on_submit=False):
        target_perc = st.number_input(
            f"Incremento risparmio % (vs {prev_year})",
            min_value=0.0,
            max_value=100.0,
            value=s_num("obiettivo_risparmio_perc", 30.0),
            step=1.0,
        )
        risp_prev = st.number_input(
            f"Risparmio anno precedente ({prev_year}) €",
            min_value=0.0,
            value=s_num_candidates(risp_prev_candidates, 0.0),
            step=100.0,
        )
        saldo_iniziale_set = st.number_input(
            f"Saldo iniziale {anno_sel} (€)",
            min_value=0.0,
            value=s_num_candidates(saldo_iniziale_candidates, 0.0),
            step=100.0,
        )
        budget_base_set = st.number_input(
            "Budget mensile base (€)",
            min_value=0.0,
            value=s_num("budget_mensile_base", 0.0),
            step=50.0,
        )
        saldo_fineco_set = st.number_input(
            "Saldo Fineco (€)",
            min_value=0.0,
            value=s_num("saldo_fineco", 25995.0),
            step=50.0,
        )
        saldo_revolut_set = st.number_input(
            "Saldo Revolut (€)",
            min_value=0.0,
            value=s_num("saldo_revolut", 2400.0),
            step=50.0,
        )
        pac_vers_set = st.number_input(
            "Versamento PAC mensile (€)",
            min_value=0.0,
            value=s_num("pac_versamento_mensile", 80.0),
            step=10.0,
        )
        pac_quote_set = st.number_input(
            "Quote PAC possedute oggi (#)",
            min_value=0,
            value=int(round(s_num("pac_quote", 0.0))),
            step=1,
        )
        pac_capitale_base_set = st.number_input(
            "Capitale PAC base iniziale (€)",
            min_value=0.0,
            value=s_num("pac_capitale_investito", 0.0),
            step=50.0,
            help="Valore base storico; il modello somma poi i versamenti PAC letti dal registro.",
        )
        pac_ticker_set = st.text_input(
            "Ticker PAC (Yahoo)",
            value=s_txt("pac_ticker", "VNGA80"),
            help="Se non funziona prova VNGA80.MI o V80A.DE",
        )
        fondo_quote_set = st.number_input(
            "Quote Fondo possedute oggi (#)",
            min_value=0.0,
            value=s_num("fondo_quote", 0.0),
            step=1.0,
            format="%.2f",
        )
        fondo_capitale_base_set = st.number_input(
            "Capitale Fondo base iniziale (€)",
            min_value=0.0,
            value=s_num("fondo_capitale_investito", 0.0),
            step=50.0,
            help="Valore base storico; il modello somma poi i versamenti Fondo letti dal registro.",
        )
        fondo_vers_set = st.number_input(
            "Versamento Fondo pensione mensile (€)",
            min_value=0.0,
            value=s_num("fondo_versamento_mensile", 50.0),
            step=10.0,
        )
        fondo_quota_set = st.number_input(
            "Valore quota Fondo (€)",
            min_value=0.0,
            value=s_num("fondo_valore_quota", 7.28),
            step=0.01,
            format="%.2f",
        )

        fondo_snapshot_set = st.date_input(
            "Data ultimo estratto Fondo",
            value=pd.to_datetime(s_txt("fondo_data_snapshot", str(date.today()))).date(),
            help="Data dell'ultimo estratto conto ufficiale del fondo. Le quote e il capitale base si riferiscono a questa data.",
        )
        fondo_tfr_set = st.number_input(
            "TFR versato dopo estratto (€)",
            min_value=0.0,
            value=s_num("fondo_tfr_versato_anno", 0.0),
            step=50.0,
            help="TFR versato dal datore di lavoro DOPO la data dell'ultimo estratto. Aggiornalo manualmente ogni mese.",
        )

        aliq_irpef_set = st.number_input(
            "Aliquota IRPEF (0-1)",
            min_value=0.0,
            max_value=1.0,
            value=s_num("aliquota_irpef", 0.26),
            step=0.01,
            format="%.2f",
        )
        pac_rend_set = st.number_input(
            "Rendimento PAC stimato (%)",
            min_value=0.0,
            max_value=20.0,
            value=s_num("pac_rendimento_stimato", 7.0),
            step=0.5,
        )
        fondo_rend_set = st.number_input(
            "Rendimento Fondo stimato (%)",
            min_value=0.0,
            max_value=20.0,
            value=s_num("fondo_rendimento_stimato", 5.0),
            step=0.5,
        )
        salva_quick = st.form_submit_button("Salva impostazioni")

    if salva_quick:
        numeric_payload = {
            "obiettivo_risparmio_perc": float(target_perc),
            risp_prev_key: float(risp_prev),
            saldo_iniziale_key: float(saldo_iniziale_set),
            "budget_mensile_base": float(budget_base_set),
            "saldo_fineco": float(saldo_fineco_set),
            "saldo_revolut": float(saldo_revolut_set),
            "pac_quote": float(pac_quote_set),
            "pac_capitale_investito": float(pac_capitale_base_set),
            "pac_versamento_mensile": float(pac_vers_set),
            "fondo_quote": float(fondo_quote_set),
            "fondo_capitale_investito": float(fondo_capitale_base_set),
            "fondo_versamento_mensile": float(fondo_vers_set),
            "fondo_valore_quota": float(fondo_quota_set),
            "aliquota_irpef": float(aliq_irpef_set),
            "pac_rendimento_stimato": float(pac_rend_set),
            "fondo_rendimento_stimato": float(fondo_rend_set),
            "fondo_tfr_versato_anno": float(fondo_tfr_set),
        }
        text_payload = {
            "pac_ticker": str(pac_ticker_set).strip(),
            "fondo_data_snapshot": str(fondo_snapshot_set),
        }
        ok_save, err_msg = _save_settings_batch(numeric_payload, text_payload)
        if not ok_save:
            st.session_state["quick_settings_saved_err"] = f"Salvataggio fallito: {err_msg}"
            st.rerun()
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        ok_meta, err_meta = _save_settings_batch({}, {"quick_settings_last_saved_at": timestamp})
        if not ok_meta:
            st.session_state["quick_settings_saved_err"] = f"Salvataggio metadata fallito: {err_meta}"
            st.rerun()
        settings = _load_settings_df()
        verify_errors = _verify_settings_batch(settings, numeric_payload, text_payload | {"quick_settings_last_saved_at": timestamp})
        if verify_errors:
            st.session_state["quick_settings_saved_err"] = (
                "Dati non allineati dopo il salvataggio: " + "; ".join(verify_errors[:4])
            )
            st.rerun()
        st.session_state["quick_settings_saved_msg"] = f"Impostazioni salvate alle {timestamp}."
        st.rerun()

# Parametri PAC/Fondo correnti da sidebar (effetto immediato in UI anche prima del salvataggio)
target_perc_corrente = float(target_perc)
risp_prev_corrente = float(risp_prev)
budget_base_corrente = float(budget_base_set)
pac_quote_corrente = int(pac_quote_set)
pac_capitale_base_corrente = float(pac_capitale_base_set)
pac_vers_corrente = float(pac_vers_set)
pac_rend_corrente = float(pac_rend_set)
pac_ticker_corrente = str(pac_ticker_set).strip()
fondo_quote_corrente = float(fondo_quote_set)
fondo_capitale_base_corrente = float(fondo_capitale_base_set)
fondo_vers_corrente = float(fondo_vers_set)
fondo_valore_quota_corrente = float(fondo_quota_set)
fondo_rend_corrente = float(fondo_rend_set)
aliquota_irpef_corrente = float(aliq_irpef_set)

# Pre-calcolo budget per sidebar e HOME
budget_base = budget_base_corrente
df_budget = log.budget_spese_annuale(df_mov, anno_sel, budget_base)

# Pannello residuo mese in sidebar
st.sidebar.markdown("<div class='side-title'>Residuo mese</div>", unsafe_allow_html=True)
st.sidebar.markdown(f"<div class='side-chip'>{MONTH_SHORT.get(mese_sel, mese_sel)}</div>", unsafe_allow_html=True)
if not df_budget.empty:
    mese_short = MONTH_SHORT.get(mese_sel, str(mese_sel))
    df_res = df_budget[df_budget["Mese"] == mese_short][["Categoria", "Speso", "Residuo", "BudgetCategoria"]]
    if not df_res.empty:
        residuo_tot = df_res["Residuo"].sum()
        cls = "side-residuo neg" if residuo_tot < 0 else "side-residuo"
        arrow = "↓" if residuo_tot < 0 else "↑"
        st.sidebar.markdown(
            f"<div class='{cls}'><span class='label'>Residuo</span><span class='pill'>{arrow} {eur2(residuo_tot, signed=True)}</span></div>",
            unsafe_allow_html=True,
        )
else:
    st.sidebar.caption("Nessun dato budget disponibile.")

# --- HEADER TITOLO ---
st.markdown(
    f"<div style='font-family:\"Plus Jakarta Sans\",sans-serif; font-size:0.95rem; "
    f"font-weight:700; letter-spacing:2px; text-transform:uppercase; "
    f"color:#5a6f8c; margin-bottom:10px;'>"
    f"{NOME_DISPLAY} — {MONTH_NAMES.get(mese_sel, mese_sel)} {anno_sel}"
    f"</div>",
    unsafe_allow_html=True,
)

# --- KPI SUPERIORI ---
saldo_iniziale = s_num_candidates(
    [f"saldo_iniziale_{anno_sel}", f"saldo iniziale_{anno_sel}"], 0.0
)
saldo_disponibile = log.saldo_disponibile_da_inizio(df_mov, anno_sel, mese_sel, saldo_iniziale)
kpi = log.calcola_kpi_dashboard(df_mov, mese_sel, anno_sel)

def _kpi_card(label, value, color, glow_color):
    """Renderizza una KPI card HTML con glow effect."""
    return f"""
<div style="
    background:#0c1120;
    border:1px solid rgba(92,118,178,0.20);
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
    text-transform:uppercase;color:rgba(180,200,240,0.55);
    margin-bottom:8px;font-family:'Plus Jakarta Sans',sans-serif;
  ">{label}</div>
  <div style="
    font-family:'JetBrains Mono',monospace;
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

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(_kpi_card("Saldo Disponibile", eur2(saldo_disponibile), "#5ce488", "rgba(92,228,136,0.18)"), unsafe_allow_html=True)
with c2:
    st.markdown(_kpi_card("Uscite Mese", eur2(kpi["uscite_mese"]), "#fa598e", "rgba(250,89,142,0.18)"), unsafe_allow_html=True)
with c3:
    st.markdown(_kpi_card("Risparmio Mese", eur2(kpi["risparmio_mese"]), "#5ce488", "rgba(92,228,136,0.18)"), unsafe_allow_html=True)
with c4:
    st.markdown(_kpi_card("Tasso Risparmio", f"{kpi['tasso_risparmio']}%", "#9b7fe8", "rgba(155,127,232,0.18)"), unsafe_allow_html=True)

st.divider()
# --- DATI FILTRATI ---
mask_mese = (df_mov["Data"].dt.month == mese_sel) & (df_mov["Data"].dt.year == anno_sel)
df_mese = df_mov[mask_mese].copy()
df_anno = df_mov[df_mov["Data"].dt.year == anno_sel].copy()

# --- TAB INTERFACCIA ---
tab_home, tab_charts, tab_assets, tab_debts, tab_admin = st.tabs([
    "🏠 HOME", "📈 ANALISI", "💰 PATRIMONIO", "🔗 DEBITI", "📝 REGISTRO"
])

# --- TAB 1: HOME ---
with tab_home:
    st.markdown("<div class='section-title'>HOME</div>", unsafe_allow_html=True)

    mesi = list(MONTH_SHORT.values())

    c1, c2 = st.columns([1.35, 1.2])

    with c1:
        st.markdown("<div class='panel-title'>📊 Budget di spesa (50/30/20)</div>", unsafe_allow_html=True)
        if not df_budget.empty:
            cat_order = list(log.PERCENTUALI_BUDGET.keys())
            colors = {
                "NECESSITÀ":    ("#4f8ef0", "#1d3a6e"),
                "SVAGO":        ("#f472b6", "#6d2040"),
                "INVESTIMENTI": ("#10d98a", "#0a4a36"),
            }

            fig_budget = go.Figure()
            for cat in cat_order:
                df_cat = df_budget[df_budget["Categoria"] == cat].set_index("Mese").reindex(mesi)
                if df_cat.empty:
                    continue
                
                budget_cat = df_cat["BudgetCategoria"].fillna(budget_base * log.PERCENTUALI_BUDGET[cat])
                speso = df_cat["Speso"].fillna(0)
                
                # --- LOGICA PER IL GRAFICO "PULITO" ---
                # 1. Residuo (parte chiara): compare solo se abbiamo speso meno del budget
                residuo = (budget_cat - speso).clip(lower=0)
                
                # 2. Spesa nel budget (parte scura): la spesa effettiva fino al limite del budget
                spesa_nel_budget = speso.where(speso <= budget_cat, budget_cat)
                
                # 3. Extra (parte rossa): quanto abbiamo sforato oltre il budget
                extra_budget = (speso - budget_cat).clip(lower=0)

                # BARRA A: RESIDUO (Colore Chiaro - a sinistra nella sezione)
                fig_budget.add_bar(
                    x=residuo,
                    y=mesi,
                    orientation="h",
                    name=f"Residuo {cat}",
                    marker=dict(color=colors.get(cat)[0], line=dict(color="rgba(0,0,0,0.35)", width=1)),
                    text=[eur0(v) if v > 0 else "" for v in residuo],
                    texttemplate="<b>%{text}</b>",
                    textposition="auto",
                    insidetextanchor="middle",
                    textfont=dict(color="#0b1020", size=12),
                    hovertemplate=f"{cat} Residuo: € %{{x:.0f}}<extra></extra>",
                )

                # BARRA B: SPESA NEL BUDGET (Colore Scuro - a destra nella sezione)
                fig_budget.add_bar(
                    x=spesa_nel_budget,
                    y=mesi,
                    orientation="h",
                    name=f"Spesa {cat}",
                    marker=dict(color=colors.get(cat)[1], line=dict(color="rgba(0,0,0,0.35)", width=1)),
                    text=[eur0(v) if v > 0 else "" for v in spesa_nel_budget],
                    texttemplate="<b>%{text}</b>",
                    textposition="auto",
                    insidetextanchor="middle",
                    textfont=dict(color="#ffffff", size=14),
                    hovertemplate=f"Spesa {cat}: € %{{x:.0f}}<extra></extra>",
                )

                # BARRA C: EXTRA BUDGET (Rosso - compare solo se sfori)
                fig_budget.add_bar(
                    x=extra_budget,
                    y=mesi,
                    orientation="h",
                    name=f"EXTRA {cat}",
                    marker=dict(color="#e74c3c", line=dict(color="#c0392b", width=1)),
                    text=[f"⚠ {eur0(v)}" if v > 0 else "" for v in extra_budget],
                    texttemplate="<b>%{text}</b>",
                    textposition="auto",
                    textfont=dict(color="#000000", size=12, weight="bold"),
                    hovertemplate=f"SFORATO {cat}: € %{{x:.2f}}<extra></extra>",
                )

            fig_budget.update_layout(barmode="stack", showlegend=False)
            fig_budget.update_yaxes(categoryorder="array", categoryarray=mesi, autorange="reversed", tickfont=dict(size=14))
            fig_budget.update_xaxes(tickprefix="€ ", tickfont=dict(size=14), tickformat=".0f")

            show_chart(fig_budget, height=420, show_legend=False)
        else:
            st.info("Imposta 'budget_mensile_base' o registra spese per vedere il grafico.")

    with c2:
        st.markdown("<div class='panel-title'>📂 Dettaglio spese per categoria</div>", unsafe_allow_html=True)
        df_uscite_mese = df_mese[df_mese["Tipo"] == "USCITA"].copy()
        det = log.dettaglio_spese(df_uscite_mese)
        if not det.empty:
            det = det.copy()
            det["Etichetta"] = det["Importo"].map(eur0)
            fig_det = px.bar(
                det,
                x="Dettaglio",
                y="Importo",
                color="Dettaglio",
                text="Etichetta",
                color_discrete_sequence=COLOR_SEQ,
            )
            fig_det.update_layout(showlegend=False)
            fig_det.update_xaxes(tickangle=-35)
            fig_det.update_traces(
                texttemplate="<b>%{text}</b>",
                textposition="auto",
                textfont=dict(size=14, color="#ffffff", weight="bold"),
                marker_cornerradius=6,
                insidetextanchor="middle",
            )
            fig_det.update_yaxes(tickprefix="€ ", tickformat=",.0f")
            show_chart(fig_det, height=420, show_legend=False)
        else:
            st.info("Nessuna spesa nel mese selezionato.")

    st.markdown("<div class='panel-title'>📅 Calendario spese ricorrenti</div>", unsafe_allow_html=True)
    df_fin_per_cal = df_fin_db.rename(columns={
        "nome": "Nome Finanziamento",
        "capitale_iniziale": "Capitale",
        "taeg": "TAEG",
        "durata_mesi": "Durata",
        "data_inizio": "Data Inizio",
        "giorno_scadenza": "Giorno Scadenza",
        "rate_pagate": "Rate Pagate",
    })
    df_ric = db.carica_spese_ricorrenti(user_email)
    if not df_ric.empty:
        df_ric = df_ric.rename(columns={
            "descrizione": "Descrizione",
            "importo": "Importo",
            "giorno_scadenza": "Giorno Scadenza",
            "frequenza_mesi": "Frequenza",
            "data_inizio": "Data Inizio",
            "data_fine": "Data Fine",
        })

    calcoli_scadenze_cache = {}

    def _calcolo_scadenze_mese(mese_ref, anno_ref):
        key = (int(anno_ref), int(mese_ref))
        if key not in calcoli_scadenze_cache:
            calcoli_scadenze_cache[key] = log.calcolo_spese_ricorrenti(
                df_ric, df_fin_per_cal, df_mov, mese_ref, anno_ref
            )
        return calcoli_scadenze_cache[key]

    cal = _calcolo_scadenze_mese(mese_sel, anno_sel)
    if not cal.empty:
        # In HOME mostriamo tutte le spese previste del mese selezionato:
        # ricorrenti + rate finanziamenti.
        cal_mese = cal.copy()
        if not cal_mese.empty:
            nascondi_pagate = st.checkbox(
                "Nascondi movimenti pagati del mese",
                value=False,
                key=f"hide_paid_{anno_sel}_{mese_sel}",
            )
            cal_view = cal_mese.copy()
            if nascondi_pagate:
                cal_view = cal_view[~cal_view["Stato"].astype(str).str.contains("PAGATO", case=False, na=False)].copy()

            tabella_ric = cal_view.copy()
            if "Giorno Previsto" not in tabella_ric.columns:
                tabella_ric["Giorno Previsto"] = pd.to_datetime(tabella_ric["Data"], errors="coerce").dt.day
            tabella_ric["Giorno Previsto"] = pd.to_numeric(tabella_ric["Giorno Previsto"], errors="coerce").fillna(0).astype(int)

            if "Data Fine Prevista" not in tabella_ric.columns:
                tabella_ric["Data Fine Prevista"] = None
            dt_fine = pd.to_datetime(tabella_ric["Data Fine Prevista"], errors="coerce")
            tabella_ric["Data Fine Prevista"] = dt_fine.dt.strftime("%d/%m/%Y").fillna("Nessuna")

            if "Frequenza" not in tabella_ric.columns:
                tabella_ric["Frequenza"] = "Mensile"

            tabella_ric = tabella_ric[
                ["Spesa", "Importo", "Giorno Previsto", "Data Fine Prevista", "Stato", "Frequenza"]
            ].rename(columns={"Spesa": "Spesa Prevista"})
            
            # Legenda colori
            st.markdown(f"""
<div style="display:flex;align-items:center;justify-content:flex-end;
            gap:16px;margin-bottom:6px;flex-wrap:wrap;">
  <span style="font-size:0.68rem;font-weight:700;letter-spacing:1.2px;
               text-transform:uppercase;color:#5a6f8c;">Legenda:</span>
  <span style="display:flex;align-items:center;gap:5px;font-size:0.78rem;">
    <span style="width:9px;height:9px;border-radius:2px;
                 background:rgba(16,217,138,0.28);border:1px solid #10d98a;
                 display:inline-block;"></span>
    <span style="color:#10d98a;font-weight:600;">Pagato</span>
  </span>
  <span style="display:flex;align-items:center;gap:5px;font-size:0.78rem;">
    <span style="width:9px;height:9px;border-radius:2px;
                 background:rgba(245,166,35,0.28);border:1px solid #f5a623;
                 display:inline-block;"></span>
    <span style="color:#f5a623;font-weight:600;">In scadenza</span>
  </span>
  <span style="display:flex;align-items:center;gap:5px;font-size:0.78rem;">
    <span style="width:9px;height:9px;border-radius:2px;
                 background:rgba(242,106,106,0.22);border:1px solid #f26a6a;
                 display:inline-block;"></span>
    <span style="color:#f26a6a;font-weight:600;">Da pagare</span>
  </span>
</div>
""", unsafe_allow_html=True)
            
            # Tabella HTML custom
            st.markdown(render_calendario_html(tabella_ric), unsafe_allow_html=True)
            # Alert scadenze vicine solo per spese ricorrenti non pagate.
            # Calcolo indipendente dal mese selezionato per coprire il cambio mese.
            oggi = date.today()
            giorni_alert = 2
            window_alert = [oggi + timedelta(days=i) for i in range(giorni_alert + 1)]
            coppie_alert = sorted({(d.year, d.month) for d in window_alert})
            frames_alert = []
            for y_a, m_a in coppie_alert:
                cal_a = _calcolo_scadenze_mese(m_a, y_a)
                if cal_a is not None and not cal_a.empty:
                    frames_alert.append(cal_a)
            if frames_alert:
                base_alert_df = pd.concat(frames_alert, ignore_index=True)
            else:
                base_alert_df = pd.DataFrame()

            alert_df = log.alert_scadenze_ricorrenti(
                base_alert_df,
                giorni_preavviso=giorni_alert,
                oggi=oggi,
            )
            alert_df = alert_df[alert_df["Giorni Alla Scadenza"] == 2].copy()
            if not alert_df.empty:
                st.warning(
                    f"Hai {len(alert_df)} spese ricorrenti in scadenza."
                )
                st.dataframe(
                    style_df_currency(alert_df[["Spesa", "Importo", "Data", "Giorni Alla Scadenza"]], ["Importo"]),
                    use_container_width=True,
                    hide_index=True,
                )

        else:
            st.info("Nessuna spesa prevista per il mese selezionato.")
    else:
        st.info("Nessuna scadenza prevista per questo mese.")

# --- TAB 2: ANALISI ---
with tab_charts:
    st.markdown("<div class='section-title'>ANALISI</div>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1], gap="large")

    with c1:
        st.markdown("<div class='panel-title'>🎯 Obiettivo risparmio</div>", unsafe_allow_html=True) 
        prev_year = anno_sel - 1
        risp_prev = risp_prev_corrente
        target_perc = target_perc_corrente
        entrate_annue = df_anno[df_anno["Tipo"] == "ENTRATA"]["Importo"].sum()
        uscite_annue = df_anno[df_anno["Tipo"] == "USCITA"]["Importo"].abs().sum()
        risp_corrente = entrate_annue - uscite_annue
        target_corrente = risp_prev * (1 + target_perc / 100) if risp_prev > 0 else 0

        if risp_prev > 0:
            accumulo = max(risp_corrente, 0)
            mancante = max(target_corrente - accumulo, 0)
            y_prev = 1
            y_curr = 0

            fig_obj = go.Figure()

            # ── Barra 2025 — verde ──
            fig_obj.add_bar(
                x=[risp_prev],
                y=[y_prev],
                orientation="h",
                width=0.46,
                name=str(prev_year),
                marker_color="#10d98a",
                marker_line=dict(color="rgba(0,0,0,0.2)", width=1),
                marker_cornerradius=6,
                text=[eur0(risp_prev)],
                texttemplate="<b>%{text}</b>",
                textposition="inside",
                insidetextanchor="middle",
                textfont=dict(color="#07090f", size=13),
            )

            # ── Barra 2026 ── con overlay: prima sfondo rosso, poi viola sopra
            if mancante > 0:
                # Sfondo rosso (barra più lunga = target completo)
                fig_obj.add_bar(
                    x=[accumulo + mancante],
                    y=[y_curr],
                    orientation="h",
                    width=0.46,
                    name="Mancante al target",
                    marker_color="rgba(242,106,106,0.30)",
                    marker_line=dict(color="rgba(242,106,106,0.5)", width=1),
                    marker_cornerradius=6,
                    hoverinfo="skip",
                    showlegend=True,
                )

            # Barra viola (parte accumulata, sovrapposta sopra)
            fig_obj.add_bar(
                x=[accumulo],
                y=[y_curr],
                orientation="h",
                width=0.46,
                name=f"{anno_sel} accumulato",
                marker_color="#9b74f5",
                marker_line=dict(color="rgba(0,0,0,0.2)", width=1),
                marker_cornerradius=6,
                text=[eur0(accumulo, signed=True)],
                texttemplate="<b>%{text}</b>",
                textposition="inside",
                insidetextanchor="middle",
                textfont=dict(color="#ffffff", size=13),
                showlegend=False,
            )
            if mancante > 0:
                centro_mancante = accumulo + mancante / 2
                fig_obj.add_trace(go.Scatter(
                    x=[centro_mancante],
                    y=[y_curr],
                    mode="text",
                    text=[eur0(mancante)],
                    textfont=dict(color="#f26a6a", size=12, weight="bold"),
                    textposition="middle center",
                    showlegend=False,
                    hoverinfo="skip",
                ))

            # ── Valori a destra ──
            fig_obj.add_trace(go.Scatter(
                x=[risp_prev],
                y=[y_prev],
                mode="text",
                text=[eur0(risp_prev)],
                textposition="middle right",
                textfont=dict(color="#5a6f8c", size=12),
                showlegend=False,
            ))
            fig_obj.update_layout(
                barmode="overlay",
                showlegend=True,
                margin=dict(l=50, r=80, t=40, b=30),
                annotations=[
                    dict(
                        text=f"<b>Target +{target_perc:.0f}%</b>",
                        x=1, y=1.18,
                        xref="paper", yref="paper",
                        showarrow=False,
                        align="center",
                        font=dict(size=12, color="#07090f", weight="bold"),
                        bgcolor="#f5a623",
                        bordercolor="rgba(0,0,0,0)",
                        borderpad=8,
                    )
                ],
                legend=dict(
                    orientation="h",
                    yanchor="bottom", y=1.02,
                    xanchor="left", x=0,
                    font=dict(size=11, color="#5a6f8c"),
                    bgcolor="rgba(0,0,0,0)",
                ),
            )
            fig_obj.update_yaxes(
                tickvals=[y_prev, y_curr],
                ticktext=[str(prev_year), str(anno_sel)],
                range=[-0.6, 1.6],
                autorange=False,
            )
            max_x = max(risp_prev, accumulo + mancante)
            fig_obj.update_xaxes(
                tickprefix="€ ",
                tickformat=",.0f",
                range=[0, max_x * 1.22],
            )
            show_chart(fig_obj, height=280, show_legend=True)
            
        else:
            st.info(f"Imposta il risparmio dell'anno precedente ({prev_year}) nelle impostazioni rapide.")
        
    with c2:
        st.markdown("<div class='panel-title'>📈 Andamento entrate</div>", unsafe_allow_html=True)
    
        entrate = log.analizza_entrate(df_mov, anno_sel)
        if not entrate.empty:
            fig_ent = go.Figure()
            mesi = entrate["Mese"].tolist()
            vals = entrate["Importo"].tolist()
            max_y = max(vals) if vals else 0
            cap = [v * 0.12 for v in vals]

            fig_ent.add_bar(
                x=mesi,
                y=vals,
                marker_color="#10d98a",
                marker_line=dict(color="rgba(0,0,0,0.5)", width=1),
                marker_cornerradius=6,
                text=[eur0(v) for v in vals],
                texttemplate="<b>%{text}</b>",
                textposition="auto",
                insidetextanchor="middle",
                name="Entrate",
            )
            fig_ent.update_layout(bargap=0.30)
            fig_ent.update_yaxes(tickprefix="€ ", tickformat=",.0f", range=[0, max_y * 1.80])
            show_chart(fig_ent, height=300, show_legend=False)
        else:
            st.info("Nessuna entrata disponibile per l'anno selezionato.")

    st.markdown("<div class='panel-title'>🔮 Previsione saldo</div>", unsafe_allow_html=True)

    saldo_iniziale = s_num_candidates([f"saldo_iniziale_{anno_sel}", f"saldo iniziale_{anno_sel}"], 0.0)
    df_prev = log.previsione_saldo(
        df_mov,
        anno_sel,
        saldo_iniziale=saldo_iniziale,
        mese_riferimento=mese_sel,
    )

    if not df_prev.empty:
        fig_prev = px.area(
            df_prev,
            x="Mese",
            y="Saldo",
            color="Tipo",
            color_discrete_sequence=["#4f8ef0", "#f5a623"],
        )

        fig_prev.update_layout(
            separators=".,",
            margin=dict(l=70, r=10, t=40, b=40),
            legend=dict(
                orientation="h",
                xanchor="left", x=0,
                yanchor="bottom", y=1.02,
                title=None,
                bgcolor="rgba(0,0,0,0)",
                borderwidth=0,
                font=dict(size=11, color="#5a6f8c"),
            ),
            hovermode="x unified",
        )

        for trace in fig_prev.data:
            mask = df_prev["Tipo"] == trace.name
            valori = df_prev.loc[mask, "Saldo"].tolist()
            trace.update(
                mode="lines+markers+text",
                text=[eur0(v, signed=True) for v in valori],
                texttemplate="<b>%{text}</b>",
                textposition="top center",
                hovertemplate="<b>%{x}</b><br>Saldo: € %{y:,.2f}<extra></extra>",
            )

        max_y = df_prev["Saldo"].max()
        min_y = df_prev["Saldo"].min()
        pad = max(1, (max_y - min_y) * 0.1)

        fig_prev.update_yaxes(
            tickprefix="€ ",
            tickformat=",.0f",
            range=[min_y - pad, max_y + pad],
        )

        fig_prev.update_traces(textfont=dict(size=12))
        style_fig(fig_prev, height=320, show_legend=True)
        fig_prev.update_layout(
            legend=dict(
                orientation="h",
                xanchor="left", x=0,
                yanchor="bottom", y=1.02,
                title=None,
                bgcolor="rgba(0,0,0,0)",
                borderwidth=0,
                font=dict(size=11, color="#5a6f8c"),
            ),
            margin=dict(l=70, r=10, t=50, b=40),
        )
        st.plotly_chart(fig_prev, use_container_width=True, config=PLOTLY_CONFIG)

    else:
        st.info("Dati insufficienti per la previsione saldo.")

# --- TAB 3: PATRIMONIO ---
with tab_assets:
    st.markdown("<div class='section-title'>PATRIMONIO</div>", unsafe_allow_html=True)
    valore_pac_attuale = s_num("pac_capitale_investito", 0.0)
    valore_fondo_attuale = s_num("fondo_capitale_investito", 0.0)
    capitale_pac_attuale = s_num("pac_capitale_investito", 0.0)
    capitale_fondo_attuale = s_num("fondo_capitale_investito", 0.0)

    # --- PAC ---
    pac_title_col, pac_badge_col = st.columns([3, 2])
    with pac_title_col:
        st.markdown("<div class='panel-title'>📈 PAC — Piano di Accumulo</div>", unsafe_allow_html=True)
    with pac_badge_col:
        pac_badge_slot = st.empty()
    
    # 1. INPUT SETTINGS (Prende i dati dal tuo DB e dai selettori rapidi)
    tic = pac_ticker_corrente if pac_ticker_corrente else s_txt("pac_ticker", "")
    

    # Dati provenienti dal database (già aggregati per ticker)
    q_pac = pac_quote_corrente          # Quote possedute oggi (input rapido)
    inv_pac = pac_capitale_base_corrente  # Capitale base iniziale da impostazioni rapide
    
    # Impostazioni per la proiezione futura
    pac_vers = pac_vers_corrente
    pac_rend = pac_rend_corrente
    if tic and q_pac >= 0:
        # I versamenti reali PAC vengono letti direttamente dal registro movimenti.
        res_pac = log.analisi_pac(
            ticker=tic, 
            quote_base=q_pac, 
            capitale_base=inv_pac, 
            versamento_mensile_proiezione=pac_vers, 
            rendimento_annuo_stimato=pac_rend,
            df_transazioni=df_mov,
            anno_corrente=anno_sel,
        )
        
        s = res_pac["Sintesi"]
        valore_pac_attuale = s["Valore Attuale"]
        capitale_pac_attuale = s["Capitale Investito"]

        # Badge ticker allineato al titolo PAC
        badge_text = f"Ticker {tic} | {s['Quote_Totali']} Quote Totali"
        pac_badge_slot.markdown(
            f"<div style='text-align:right'>{badge(badge_text, 'badge-red')}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""<div style="display:flex;align-items:center;gap:10px;padding:9px 13px;
                border-radius:8px;font-size:0.88rem;color:#5a6f8c;margin-bottom:12px;
                background:rgba(16,217,138,0.05);border:1px solid rgba(16,217,138,0.2);">
                <span style="color:#10d98a;">●</span>
                Versamento mensile: <strong style="color:#dde6f5;margin:0 4px;">{eur2(pac_vers)}</strong>
                &nbsp;|&nbsp;
                Rendimento annuo stimato: <strong style="color:#10d98a;margin:0 4px;">{pac_rend:.2f}%</strong>
            </div>""",
            unsafe_allow_html=True,
        )
        

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Valore attuale", eur2(s["Valore Attuale"]))
        k2.metric("Rendimento", eur2(s["P&L"], signed=True), f"{s['P&L %']}%")
        k3.metric("Tasse plusvalenze", eur2(s["Imposte"]))
        k4.metric("Netto smobilizzo", eur2(s["Netto"]))
        st.markdown(
            f"""<div style="display:flex;align-items:baseline;justify-content:space-between;margin:4px 0 8px 0;">
        <div class='panel-title' style='margin:0;'> Proiezione PAC </div>
        <span style="font-family:'JetBrains Mono',monospace;font-size:0.78rem;
                    color:#5a6f8c;letter-spacing:0.2px;">
            Versamento PAC da registro ({anno_sel}): <strong style="color:#82b4f7;">{eur2(s.get('Versato_Reale_Registro_Anno', s['Versato_Reale_Registro']))}</strong>
        </span>
        </div>""",
    unsafe_allow_html=True,
)
        # --- GRAFICO AGGIORNATO ---
        df_pac = res_pac["Grafico_Proiezione"]
        
        fig_pac = go.Figure()
        serie = [
            ("Proiezione Stimata", "#34d399", "tozeroy"), # Curva esponenziale
            ("Capitale Versato", "#60a5fa", "tozeroy"),   # Linea versamenti
            ("Valore Netto", "#facc15", "none"),          # Linea post-tasse
        ]
        
        for name, color, fill in serie:
            fig_pac.add_trace(go.Scatter(
                x=df_pac["Mese"], 
                y=df_pac[name], 
                name=name,
                mode="lines",
                line=dict(color=color, width=3 if name == "Proiezione Stimata" else 2),
                fill=fill,
                fillcolor=hex_to_rgba(color, 0.1),
            ))
            df_tick = df_pac[df_pac["Mese"] % 12 == 0]
            fig_pac.add_trace(
                go.Scatter(
                    x=df_tick["Mese"],
                    y=df_tick[name],
                    mode="markers+text",
                    marker=dict(size=6, color=color, symbol="circle"),
                    text=[f"€{v/1000:.1f}k" for v in df_tick[name]],
                    textposition="top center",
                    textfont=dict(color=color, size=10),
                    showlegend=False,
                    hoverinfo="skip",
                )
            )

        fig_pac.update_layout(hovermode="x unified")
        style_fig(fig_pac, height=320, show_legend=True)
        
        # Sovrascrive DOPO style_fig
        fig_pac.update_layout(
            margin=dict(l=10, r=10, t=70, b=10),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.05,
                xanchor="left",
                x=0,
            )
        )
        fig_pac.update_traces(textfont=dict(size=12))
        st.plotly_chart(fig_pac, use_container_width=True, config=PLOTLY_CONFIG)
    else:
        pac_badge_slot.empty()
        st.info("Imposta 'Ticker' e 'Quote' nel registro per visualizzare l'analisi del PAC.")

    st.divider()

    # --- FONDO PENSIONE ---
    st.markdown("<div class='panel-title'>🏦 Fondo Pensione</div>", unsafe_allow_html=True)
    valore_quota = fondo_valore_quota_corrente
    q_fondo = fondo_quote_corrente
    inv_fondo = fondo_capitale_base_corrente
    vers_fondo = fondo_vers_corrente
    rendimento_fondo = fondo_rend_corrente
    aliquota_irpef = aliquota_irpef_corrente

    if valore_quota > 0 and q_fondo > 0:
        _fondo_snapshot_raw = s_txt("fondo_data_snapshot", str(date.today()))
        _fondo_snapshot = pd.to_datetime(_fondo_snapshot_raw, errors="coerce").date()
        _fondo_tfr = s_num("fondo_tfr_versato_anno", 0.0)

        res_fondo = log.analisi_fondo_pensione(
            valore_quota,
            q_fondo,
            inv_fondo,
            vers_fondo,
            rendimento_fondo,
            df_mov,
            anno_sel,
            aliquota_irpef=aliquota_irpef,
            anni=30,
            data_snapshot=_fondo_snapshot,
            tfr_versato_anno=_fondo_tfr,
        )
        valore_fondo_attuale = res_fondo["Sintesi"]["Valore Attuale"]
        capitale_fondo_attuale = res_fondo["Sintesi"]["Capitale Investito"]
        perc_fp = min(res_fondo["Avanzamento_Fiscale"]["Percentuale"] / 100, 1.0)
        f1, f2, f3 = st.columns(3)

        with f1:
            st.metric("Valore attuale", eur2(res_fondo["Sintesi"]["Valore Attuale"]))

        with f2:
    # Qui devi usare "Quote Attuali" e NON "Quote Finali"
            quote_da_mostrare = res_fondo["Sintesi"]["Quote Attuali"]
            st.metric("Quote possedute", f"{quote_da_mostrare:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

        with f3:
            st.metric(
        "Rendimento", 
        eur2(res_fondo["Sintesi"]["P&L"], signed=True), 
        f"{res_fondo['Sintesi']['P&L %']}%"
    )

        # Spazio prima della progress bar
        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

        # Progress Bar Layout
        st.markdown(
            f"<div style='font-size: 1.1rem; font-weight: bold; margin-bottom: 5px;'>"
            f"Avanzamento versamento ({res_fondo['Avanzamento_Fiscale']['Percentuale']}%)"
            f"</div>", 
            unsafe_allow_html=True
)
        st.markdown(
            f"""
            <div class='progress-wrap'>
              <div class='progress-track'>
                <div class='progress-fill' style='width:{perc_fp*100:.1f}%'></div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div style='font-size: 0.95rem; color: #5a6f8c; margin-top: 5px;'>"
            f"Versato anno: {eur2(res_fondo['Avanzamento_Fiscale']['Versato_Anno'])} | "
            f"Rimanente soglia: {eur2(res_fondo['Avanzamento_Fiscale']['Rimanente_Soglia'])}"
            f"</div>",
            unsafe_allow_html=True
)

        df_fondo = res_fondo["Grafico_Proiezione"].copy()
        mesi = df_fondo["Mese"].tolist()
        anni_tot = int(max(mesi) / 12)
        tickvals = [i * 12 for i in range(1, anni_tot + 1)]
        ticktext = [str(i) for i in range(1, anni_tot + 1)]

        fig_fondo = go.Figure()
        serie = [
            ("Proiezione Teorica", "#f472b6", "tozeroy"),
            ("Cap.Versato Cumu.", "#60a5fa", "tozeroy"),
            ("Valore Attuale Linea", "#facc15", "none"),
        ]
        for name, color, fill in serie:
            fig_fondo.add_trace(
                go.Scatter(
                    x=mesi,
                    y=df_fondo[name],
                    mode="lines",
                    line=dict(color=color, width=3 if name == "Proiezione Teorica" else 2, dash="dash" if name == "Valore Attuale Linea" else "solid"),
                    fill=fill,
                    fillcolor=hex_to_rgba(color, 0.08),
                    name=name.replace("Linea", ""),
                )
            )
            df_tick = df_fondo[df_fondo["Mese"] % 60 == 0] #serve per mostrare i marker solo ogni x mesi
            fig_fondo.add_trace(
                go.Scatter(
                    x=df_tick["Mese"],
                    y=df_tick[name],
                    mode="markers+text",
                    marker=dict(size=8, color=color, symbol="circle"),
                    text=[f"€{v/1000:.1f}k" for v in df_tick[name]],
                    textposition="top center",
                    textfont=dict(color=color, size=10),
                    showlegend=False,
                )
            )

        fig_fondo.update_xaxes(tickvals=tickvals, ticktext=ticktext)
        fig_fondo.update_yaxes(tickprefix="€ ", tickformat=",.0f")
        st.markdown(
        f"""<div style="display:flex;align-items:baseline;justify-content:space-between;margin:4px 0 8px 0;">
    <div class='panel-title' style='margin:0;'> Proiezione Fondo Pensione </div>
    <span style="font-family:'JetBrains Mono',monospace;font-size:0.78rem;
                color:#5a6f8c;letter-spacing:0.2px;">
        Proiezione 30 anni — rendimento stimato: <strong style="color:#82b4f7;">{rendimento_fondo:.2f}%</strong>
    </span>
    </div>""",
        unsafe_allow_html=True,
    )
        style_fig(fig_fondo, height=380, show_legend=True)
        fig_fondo.update_layout(
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="left",
                x=0.01,
                bgcolor="rgba(0,0,0,0)",
                borderwidth=0,
            ),
            margin=dict(l=10, r=10, t=60, b=10),
        )
        st.plotly_chart(fig_fondo, use_container_width=True, config=PLOTLY_CONFIG)
       
    else:
        st.info("Imposta valore iniziale del fonto ' e 'quote del fondo' in asset_settings.")

    st.divider()

    # --- PORTAFOGLIO / VERSAMENTI / VARIAZIONE ---
    r1, r2 = st.columns([1, 1])
    with r1:
        st.markdown("<div class='panel-title'>Composizione portafoglio</div>", unsafe_allow_html=True)
        saldo_fineco = float(saldo_disponibile)
        saldo_revolut = float(saldo_revolut_set)
        valore_pac = valore_pac_attuale
        valore_fondo = valore_fondo_attuale
        comp = log.composizione_portafoglio(saldo_fineco, saldo_revolut, valore_pac, valore_fondo)
        if comp:
            fig_comp = px.pie(
                comp["Dettaglio"],
                names="Asset",
                values="Valore",
                hole=0.35,
                color_discrete_sequence=COLOR_SEQ,
            )
            fig_comp.update_traces(
                textinfo="percent+label",
                textposition="inside",
                hovertemplate="<b>%{label}</b><br>€ %{value:,.2f}<br>%{percent}<extra></extra>",
                domain=dict(x=[1.0, 0.0], y=[1.0, 0.0]),  # ← rimpicciolisce la torta
            )
            fig_comp.update_layout(
                showlegend=False,
                margin=dict(l=10, r=10, t=10, b=10),
            )
            show_chart(fig_comp, height=300, show_legend=False)

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
            det = det.str.replace(r"\s+", " ", regex=True)
            # Consideriamo solo movimenti con dettaglio PAC o Fondo Pensione
            mask_pac = det.str.contains("PAC", na=False)
            mask_fondo = det.str.contains("FONDO", na=False) | det.str.contains("PENSION", na=False)
            df_inv = df_inv[mask_pac | mask_fondo].copy()
            if df_inv.empty:
                st.info("Nessun versamento PAC/Fondo trovato nel registro transazioni.")
            else:
                df_inv["Dettaglio"] = det.loc[df_inv.index].apply(
                    lambda x: "PAC" if "PAC" in x else "FONDO PENSIONE"
                )
                df_inv = df_inv.groupby(["Mese", "Dettaglio"])["Importo"].sum().abs().reset_index()

            mesi = list(MONTH_SHORT.values())
            pivot = df_inv.pivot_table(index="Mese", columns="Dettaglio", values="Importo", fill_value=0).reindex(mesi, fill_value=0)

            fig_vers = go.Figure()
            colors = {"PAC": "#EF4444", "FONDO PENSIONE": "#f472b6"}
            for col in pivot.columns:
                fig_vers.add_trace(
                    go.Scatter(
                        x=mesi,
                        y=pivot[col],
                        mode="lines+markers+text",
                        name=col.title(),
                        line=dict(shape="hvh", width=2, color=colors.get(col, None)),
                        fill="tozeroy",
                        text=[f"€ {v:,.0f}" if v > 0 else "" for v in pivot[col]],
                        textposition="top center",
                    )
                )
                style_fig(fig_vers, height=300, show_legend=True)
                fig_vers.update_layout(
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="left",
                    x=0.01,
                    bgcolor="rgba(0,0,0,0)",
                    borderwidth=0,
                ),
                margin=dict(l=10, r=10, t=60, b=10),
                yaxis=dict(range=[0, pivot.values.max() * 1.3]),
            )
            st.plotly_chart(fig_vers, use_container_width=True, config=PLOTLY_CONFIG)
        else:
            st.info("Nessun versamento registrato per l'anno selezionato.")

    st.markdown("<div class='panel-title'>📊 Variazione investimenti (anno precedente vs attuale)</div>", unsafe_allow_html=True)
    anno_precedente = int(anno_sel) - 1
    var_inv = log.variazione_investimenti(df_mov, anno_sel)
    investito_precedente = var_inv["Anno_Precedente"]
    investito_corrente = var_inv["Anno_Corrente"]
    if investito_precedente > 0 or investito_corrente > 0:
        anni_barre = [f"{anno_precedente}", f"{anno_sel}"]
        pac_vals = [var_inv["PAC_Anno_Precedente"], var_inv["PAC_Anno_Corrente"]]
        fondo_vals = [var_inv["Fondo_Anno_Precedente"], var_inv["Fondo_Anno_Corrente"]]

        fig_var = go.Figure()
        fig_var.add_bar(
            x=anni_barre,
            y=pac_vals,
            name="PAC",
            marker_color="#EF4444",
            text=[eur0(v) if v > 0 else "" for v in pac_vals],
            marker_cornerradius=6,
            textposition="inside",
            
            textfont=dict(color="#ffffff", size=12),
        )
        fig_var.add_bar(
            x=anni_barre,
            y=fondo_vals,
            name="Fondo Pensione",
            marker_color="#FDC82F",
            text=[eur0(v) if v > 0 else "" for v in fondo_vals],
            textposition="inside",
            marker_cornerradius=6,
            textfont=dict(color="#ffffff", size=12),
        )
        fig_var.update_layout(
            barmode="group",
            xaxis_title="Anno",
            yaxis_title="Totale versato",
            hovermode="x unified",
            bargap=0.28,
            bargroupgap=0.12,
        )
        fig_var.update_yaxes(
            tickprefix="€ ",
            tickformat=",.0f",
            anchor="x",
            side="left",
            ticklabelposition="inside",
        )

        style_fig(fig_var, height=300, show_legend=True)
        fig_var.update_layout(
            barmode="group",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="left",
                x=0.01,
                bgcolor="rgba(0,0,0,0)",
                borderwidth=0,
            ),
            margin=dict(l=10, r=10, t=60, b=10),
        )
        st.plotly_chart(fig_var, use_container_width=True, config=PLOTLY_CONFIG)
        
        delta = var_inv["Variazione_Assoluta"]
        perc = var_inv["Variazione_Perc"]
        st.caption(
            f"Totale anno {anno_precedente}: {eur2(investito_precedente)} | "
            f"Totale anno {anno_sel}: {eur2(investito_corrente)} | "
            f"Δ {eur2(delta, signed=True)} ({perc:+.1f}%)"
        )
    else:
        st.info(f"Nessun investimento trovato nel registro per {anno_precedente} e {anno_sel}.")

# --- TAB 4: DEBITI ---
# ===== FUNZIONE DI SUPPORTO PER COLORI =====
with tab_debts:
    st.markdown("<div class='section-title'>DEBITI</div>", unsafe_allow_html=True)
    # ===== COLORI TEMA WEB APP =====
    APP_BG = "#0f172a"        
    PANEL_BG = "#111827"      
    TEXT_COLOR = "#e5e7eb"
    # Colori tema finanziamenti
    COLOR_PAGATO       = "#10d98a"
    COLOR_RESIDUO      = "rgba(242,106,106,0.40)"
    COLOR_RESIDUO_pie  = "#f26a6a"
    COLOR_INT_PAGATI   = "#10d98a"
    COLOR_INT_RESIDUI  = "rgba(242,106,106,0.40)"   

    # INTERESSI
    COLOR_INT_PAGATI = "#34d399"
    # Trasformiamo l'esadecimale con opacità in RGBA
    COLOR_INT_RESIDUI = hex_to_rgba("#f26a6a66")

    fin_rows = []
    dettagli_rows = []
    totale_capitale = df_fin_db["capitale_iniziale"].sum()
    totale_residuo = 0.0
    interessi_pagati = 0.0
    interessi_totali = 0.0

    for _, f in df_fin_db.iterrows():
        dati_base = log.calcolo_finanziamento(
            f["capitale_iniziale"],
            f["taeg"],
            f["durata_mesi"],
            f["data_inizio"],
            f["giorno_scadenza"],
        )
        rate_pagate_db = int(f["rate_pagate"]) if "rate_pagate" in f.index and pd.notna(f["rate_pagate"]) else None
        rate_pagate_mov = _mesi_pagati_da_mov(df_mov, f["nome"], dati_base["rata"], data_inizio=f["data_inizio"])
        rate_pagate_cal = int(dati_base.get("mesi_pagati", 0))
        if rate_pagate_db is None and rate_pagate_mov is None and rate_pagate_cal <= 0:
            rate_pagate_eff = None
        else:
            vals = [v for v in [rate_pagate_db, rate_pagate_mov, rate_pagate_cal] if v is not None]
            rate_pagate_eff = max(vals) if vals else None

        dati = log.calcolo_finanziamento(
            f["capitale_iniziale"],
            f["taeg"],
            f["durata_mesi"],
            f["data_inizio"],
            f["giorno_scadenza"],
            rate_pagate_override=rate_pagate_eff,
        )

        pagato = max(dati["capitale_pagato"], 0)
        residuo = max(dati["debito_residuo"], 0)

        fin_rows.append({
            "Nome": f["nome"],
            "Pagato": pagato,
            "Residuo": residuo,
        })
        dettagli_rows.append({
            "Nome": f["nome"],
            "Rata": dati["rata"],
            "Residuo": dati["debito_residuo"],
            "% Completato": round(dati["percentuale_completato"], 1),
            "Mesi rim.": dati["mesi_rimanenti"],
        })

        totale_residuo += residuo
        interessi_pagati += dati["interessi_pagati"]
        interessi_totali += dati["interessi_totali"]

    df_prog = pd.DataFrame(fin_rows, columns=["Nome", "Pagato", "Residuo"])
    totale_pagato = max(0.0, totale_capitale - totale_residuo)
    interessi_residui = max(0.0, interessi_totali - interessi_pagati)

    c1, c2 = st.columns([1.4, 1], gap="large")

    with c1:
        if df_prog.empty:
            st.info("Nessun finanziamento presente. Aggiungilo nel tab Registro.")
        else:
            fig_prog = go.Figure()

            fig_prog.add_bar(
                y=df_prog["Nome"],
                x=df_prog["Pagato"],
                orientation="h",
                name="Totale pagato",
                marker_color=COLOR_PAGATO,   # ← COLORE PAGATO
                marker_cornerradius=6,
                text=df_prog["Pagato"].map(eur0),
                textposition="inside",
                insidetextanchor="middle",
                textfont=dict(
            color="#ffffff",   # ← COLORE ETICHETTE (BIANCO)
            size=13
        )
            )

            fig_prog.add_bar(
                y=df_prog["Nome"],
                x=df_prog["Residuo"],
                orientation="h",
                name="Debito residuo",
                marker_color=COLOR_RESIDUO,  # ← COLORE RESIDUO
                marker_cornerradius=6,
                text=df_prog["Residuo"].map(eur0),
                textposition="inside",
                insidetextanchor="middle",
                textfont=dict(
            color="#ffffff",   # ← COLORE ETICHETTE (BIANCO)
            size=13
        )
            )

            fig_prog.update_layout(barmode="stack")
            style_fig(fig_prog, height=320, show_legend=True)
            fig_prog.update_layout(
                title=dict(
                    text="FINANZIAMENTI",
                    x=0.5, xanchor="center",
                    font=dict(size=15, color="#dde6f5"),
                ),
                legend=dict(
                    orientation="h",
                    yanchor="bottom", y=0.97,
                    xanchor="left", x=0,
                    bgcolor="rgba(0,0,0,0)",
                    font=dict(size=11, color="#5a6f8c"),
                ),
                margin=dict(l=10, r=10, t=60, b=10),
                xaxis=dict(tickprefix="€ ", tickformat=",.0f"),
                separators=",.",
            )
            fig_prog.update_xaxes(showgrid=True)
            fig_prog.update_yaxes(showgrid=False)

            st.plotly_chart(fig_prog, use_container_width=True, config=PLOTLY_CONFIG)

    with c2:
        fig_pie = go.Figure(go.Pie(
            labels=["Pagato", "Residuo"],
            values=[totale_pagato, totale_residuo],
            hole=0.35,
            textinfo="percent",
            marker=dict(
                colors=[COLOR_PAGATO, COLOR_RESIDUO_pie]  # ← COLORI TORTA
            ),
            textfont=dict(
                color=TEXT_COLOR,
                size=15
            ),
            # Imposto il dominio verticale e orizzontale per ingrandire la torta
            domain=dict(x=[0, 1], y=[0.1, 0.90])
        ))

        style_fig(fig_pie, height=320, show_legend=True)
        fig_pie.update_layout(
            title=dict(
                text="POSIZIONE DEBITI",
                x=0.5, xanchor="center",
                font=dict(size=15, color="#dde6f5"),
            ),
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom", y=0.97,
                xanchor="left", x=0,
                bgcolor="rgba(0,0,0,0)",
                font=dict(size=11, color="#5a6f8c"),
            ),
            margin=dict(t=60, b=10, l=10, r=10),
            separators=",.",
        )

        st.plotly_chart(fig_pie, use_container_width=True, config=PLOTLY_CONFIG)

    c3, c4 = st.columns([1.4, 1], gap="large")

    with c3:
        fig_int = go.Figure()

        fig_int.add_bar(
            y=["Interessi"],
            x=[interessi_pagati],
            orientation="h",
            name="Quota interessi",
            marker_color=COLOR_INT_PAGATI,  # ← COLORE INTERESSI PAGATI
            marker_cornerradius=6,
            text=[eur0(interessi_pagati)],
            textposition="inside",
            insidetextanchor="middle",
            textfont=dict(
                color="#ffffff",   # ← COLORE ETICHETTE (BIANCO)
                size=13
            )
        )

        fig_int.add_bar(
            y=["Interessi"],
            x=[interessi_residui],
            orientation="h",
            name="Interessi residui",
            marker_color=COLOR_INT_RESIDUI, # ← COLORE INTERESSI RESIDUI
            marker_cornerradius=6,
            text=[eur0(interessi_residui)],
            textposition="inside",
            insidetextanchor="middle",
            textfont=dict(
                color="#ffffff",   # ← COLORE ETICHETTE (BIANCO)
                size=13
            )
        )

        fig_int.update_layout(barmode="stack")
        style_fig(fig_int, height=220, show_legend=True)
        fig_int.update_layout(
            title=dict(
                text="INTERESSI PAGATI",
                x=0.5, xanchor="center",
                font=dict(size=15, color="#dde6f5"),
            ),
            legend=dict(
                orientation="h",
                yanchor="bottom", y=0.97,
                xanchor="left", x=0,
                bgcolor="rgba(0,0,0,0)",
                font=dict(size=11, color="#5a6f8c"),
            ),
            margin=dict(l=10, r=10, t=60, b=10),
            xaxis=dict(tickprefix="€ ", tickformat=",.0f"),
            separators=",.",
        )
        fig_int.update_xaxes(showgrid=True)
        fig_int.update_yaxes(showgrid=False)

        st.plotly_chart(fig_int, use_container_width=True, config=PLOTLY_CONFIG)

    with c4:
        df_tabella = pd.DataFrame(
            dettagli_rows,
            columns=["Nome", "Rata", "Residuo", "% Completato", "Mesi rim."],
        )
        if df_tabella.empty:
            st.caption("Nessun finanziamento da mostrare.")
        else:
            debt_rows_html = []
            for _, row in df_tabella.iterrows():
                perc = float(str(row["% Completato"]).replace("%",""))
                perc_color = "#10d98a" if perc >= 50 else "#f5a623" if perc >= 25 else "#f26a6a"
                mesi = int(row["Mesi rim."])
                mesi_color = "#f26a6a" if mesi > 120 else "#f5a623" if mesi > 36 else "#10d98a"
                small_font_style = "font-size: 0.82rem; white-space: nowrap;"

                debt_rows_html.append(
                    _reg_table_row([
                        _reg_table_td(f"<span style='{small_font_style}'><strong>{escape(str(row['Nome']))}</strong></span>", color="#dde6f5", weight=600),
                        _reg_table_td(f"<span style='{small_font_style}'>{eur2(row['Rata'])}</span>", color="#f26a6a", mono=True, weight=600),
                        _reg_table_td(f"<span style='{small_font_style}'>{eur2(row['Residuo'])}</span>", color="#dde6f5", mono=True),
                        _reg_table_td(f"<span style='{small_font_style}'>{perc:.1f}%</span>", color=perc_color, mono=True, align="center"),
                        _reg_table_td(f"<span style='{small_font_style}'>{str(mesi)}</span>", color=mesi_color, mono=True, align="center"),
                    ])
                )
            st.markdown(
            _render_reg_scroll_table(
                title="Riepilogo finanziamenti",
                right_html="",
                columns=[
                    ("Nome",         "center"),
                    ("Rata",         "center"),  
                    ("Residuo",      "center"),  
                    ("% Compl.",     "center"),
                    ("Mesi",         "left"),
                ],
                widths=[1.4, 1.1, 1.5, 0.9, 0.7], 
                rows_html=debt_rows_html,
                height_px=230,
            ),
            unsafe_allow_html=True,
        )

# --- TAB 5: REGISTRO ---
with tab_admin:
    st.markdown("<div class='section-title'>Registro</div>", unsafe_allow_html=True)
 
    # ── NUOVA TRANSAZIONE ──
    # CSS aggiuntivo per i toggle Uscita/Entrata
    st.markdown("""
<style>
/* label campo sopra input */
div[data-testid="stVerticalBlock"] label[data-testid="stWidgetLabel"] p {
    font-size: 0.76rem !important;
    font-weight: 700 !important;
    letter-spacing: 1.15px !important;
    text-transform: uppercase !important;
    color: #7487ad !important;
}
/* ── Radio toggle Uscita/Entrata ── */
div[data-testid="stRadio"] > div[role="radiogroup"] {
    display: flex !important;
    flex-direction: row !important;
    gap: 0 !important;
    background: rgba(10,16,32,0.96) !important;
    border: 1px solid rgba(112,143,215,0.20) !important;
    border-radius: 14px !important;
    overflow: hidden !important;
    padding: 0px !important;
    width: 100% !important;
    min-height: 56px !important;
    box-shadow: inset 0 1px 0 rgba(14,217,138,0.20) !important;
}
div[data-testid="stRadio"] > div[role="radiogroup"] > label {
    flex: 1 !important;
    text-align: center !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    height: 56px !important;      
    min-height: 56px !important;  
    padding: 0px!important;     
    font-size: 0.82rem !important; 
    margin: 0 !important;
    font-weight: 700 !important;
    color: #7083a9 !important;
    cursor: pointer !important;
    transition: all 0.15s !important;
    border-right: 1px solid rgba(112,143,215,0.14) !important;
    background: transparent !important;
}
div[data-testid="stRadio"] > div[role="radiogroup"] > label > div:last-child {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 100% !important;
    height: 56px !important; 
    line-height: 1 !important;
    margin: 0 !important;
    padding: 0px!important;
}
div[data-testid="stRadio"] > div[role="radiogroup"] > label:last-child {
    border-right: none !important;
}
div[data-testid="stRadio"] > div[role="radiogroup"] > label > div:last-child {
    width: 100% !important;
    display: flex !important;
    justify-content: center !important;
}
/* Nascondi il pallino */
div[data-testid="stRadio"] > div[role="radiogroup"] > label > div:first-child {
    display: none !important;
}
/* radio a 2 opzioni: Uscita / Entrata */
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
/* radio a 3 opzioni: Tutte / Uscita / Entrata */
div[data-testid="stRadio"] > div[role="radiogroup"]:has(label:nth-child(3)) > label:nth-child(1):has(input:checked) {
    background: rgba(79,142,240,0.14) !important;
    color: #8db8ff !important;
    box-shadow: inset 0 0 0 1px rgba(79,142,240,0.16) !important;
}
div[data-testid="stRadio"] > div[role="radiogroup"]:has(label:nth-child(3)) > label:nth-child(2):has(input:checked) {
    background: rgba(255,124,115,0.16) !important;
    color: #EF696A !important;
    box-shadow: inset 0 0 0 1px rgba(255,124,115,0.16) !important;
}
div[data-testid="stRadio"] > div[role="radiogroup"]:has(label:nth-child(3)) > label:nth-child(3):has(input:checked) {
    background: rgba(47,221,150,0.15) !important;
    color: #42e7a7 !important;
    box-shadow: inset 0 0 0 1px rgba(47,221,150,0.14) !important;
}
/* ── Tabelle Registro HTML ── */
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
/* Header colonne */
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
/* Righe body */
.reg-html-table tbody tr {
    background: #0c1120;
    transition: background 0.1s;
}
.reg-html-table tbody tr:hover {
    background: rgba(79,142,240,0.04);
}
.reg-html-table tbody td {
    padding: 14px 14px;
    background: transparent;
    color: #dde6f5;
    font-size: 0.875rem;
    line-height: 1.3;
    border-bottom: 1px solid rgba(79,142,240,0.07);
    vertical-align: middle;
}
.reg-html-table tbody tr:last-child td {
    border-bottom: none;
}
/* Cella vuota / empty state */
.reg-html-empty {
    padding: 24px 16px !important;
    text-align: center !important;
    color: #5a6f8c !important;
    font-size: 0.875rem !important;
}
/* Chip badge */
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
/* Elimina button sotto tabella */
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
</style>
""", unsafe_allow_html=True)
 
    # Banner conferma movimento (mostrato nel ciclo dopo il rerun)
    if st.session_state.pop("_banner_mov", False):
        st.success("✅ Movimento registrato con successo!")

    with st.container(border=True):
        st.markdown("""
<div style="display:flex;align-items:center;gap:10px;margin-bottom:18px;">
  <div style="width:28px;height:28px;border-radius:7px;background:rgba(79,142,240,0.12);
              display:flex;align-items:center;justify-content:center;font-size:15px;">💳</div>
  <span style="font-family:'Plus Jakarta Sans',sans-serif;font-size:13px;font-weight:700;
               color:#dde6f5;letter-spacing:-0.1px;">Nuova Transazione</span>
</div>""", unsafe_allow_html=True)
 
        # ── Riga 1: Tipo | Categoria | Dettaglio | Data ──
        col_tipo, col_cat, col_det, col_data = st.columns([1, 1, 1.5, 1])
 
        with col_tipo:
            tipo_inserito = st.radio(
                "Tipo movimento",
                ["↑ Uscita", "↓ Entrata"],
                horizontal=True,
                key="reg_tipo_radio",
            )
            tipo_val = "USCITA" if "Uscita" in tipo_inserito else "ENTRATA"
 
        # Categoria (fuori dal form per aggiornamento dinamico del Dettaglio)
        categoria_scelta = col_cat.selectbox(
            "Categoria",
            list(log.STRUTTURA_CATEGORIE.keys()),
            key="reg_categoria",
        )
        dettagli_filtrati = log.STRUTTURA_CATEGORIE[categoria_scelta]
        dettaglio_scelto = col_det.selectbox(
            "Dettaglio",
            dettagli_filtrati,
            key="reg_dettaglio",
        )
        data_inserita = col_data.date_input("Data", datetime.now(), key="reg_data")
 
        # ── Riga 2: Importo | Note ──
        col_imp, col_note = st.columns([1, 3])
        importo_inserito = col_imp.number_input(
            "Importo (€)", min_value=0.0, step=0.01, format="%.2f", key="reg_importo"
        )
        note_inserite = col_note.text_input(
            "Note", placeholder="Descrizione opzionale…", key="reg_note"
        )
        st.markdown('</div>', unsafe_allow_html=True)
 
        # ── Riga 3: Bottoni ──
        col_btn, col_ann, _ = st.columns([1.2, 0.8, 3])
 
        def _reset_form():
            for k in ["reg_importo", "reg_note", "reg_data"]:
                if k in st.session_state:
                    del st.session_state[k]
 
        if col_btn.button("＋ Registra Movimento", key="btn_registra_mov", use_container_width=True, type="primary"):
            if not user_email:
                st.error("Sessione non valida. Effettua di nuovo l'accesso.")
            elif importo_inserito <= 0:
                st.warning("Inserisci un importo maggiore di zero.")
            else:
                # Cattura i valori PRIMA del rerun
                _cat = st.session_state.get("reg_categoria", categoria_scelta)
                _det = st.session_state.get("reg_dettaglio", dettaglio_scelto)
                try:
                    db.aggiungi_movimento(
                        data_inserita, tipo_val, _cat,
                        _det, importo_inserito, note_inserite,
                        user_email=user_email,
                    )
                except Exception as exc:
                    st.error(f"Errore salvataggio movimento: {exc}")
                else:
                    db.carica_dati.clear()
                    st.session_state["_banner_mov"] = True
                    _reset_form()
                    st.rerun()
 
        if col_ann.button("Annulla", key="btn_annulla_mov", use_container_width=True):
            _reset_form()
            st.rerun()
 
    # ── SPESE RICORRENTI ──
    with st.container(border=True):
        # conteggio badge
        df_ric_count = db.carica_spese_ricorrenti(user_email)
        n_ric = len(df_ric_count) if not df_ric_count.empty else 0
        st.markdown(f"""
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
  <div style="display:flex;align-items:center;gap:10px;">
    <div style="width:28px;height:28px;border-radius:7px;background:rgba(79,142,240,0.12);
                display:flex;align-items:center;justify-content:center;font-size:15px;">🔁</div>
    <span style="font-family:'Plus Jakarta Sans',sans-serif;font-size:13px;font-weight:700;
                 color:#dde6f5;letter-spacing:-0.1px;">Spese Ricorrenti</span>
  </div>
  <span style="font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:400;
               padding:3px 10px;border-radius:20px;background:rgba(79,142,240,0.12);
               color:#82b4f7;border:1px solid rgba(79,142,240,0.28);">{n_ric} attive</span>
</div>""", unsafe_allow_html=True)
 
        with st.form("form_spese_ricorrenti", clear_on_submit=False):
            c_desc, c_imp, c_freq = st.columns([2, 1, 1])
            descrizione = c_desc.text_input("Descrizione spesa", placeholder="Es. Netflix, Palestra, Assicurazione…", key="ric_desc")
            importo = c_imp.number_input("Importo (€)", min_value=0.0, step=0.01, key="ric_importo")
            freq_options = {
                "Mensile": 1, "Bimestrale": 2, "Trimestrale": 3,
                "Quadrimestrale": 4, "Semestrale": 6, "Annuale": 12,
            }
            freq_label = c_freq.selectbox("Frequenza", list(freq_options.keys()), index=0, key="ric_freq")
            freq = freq_options[freq_label]

            c_giorno, c_start, c_end, c_check = st.columns([1, 1, 1, 1])
            giorno_scad = c_giorno.number_input("Giorno scadenza", min_value=1, max_value=31, step=1, value=1, key="ric_giorno")
            data_inizio = c_start.date_input("Data inizio", datetime.now(), key="ric_data_inizio")
            senza_fine = c_check.checkbox("Senza data fine", value=False, key="ric_senza_fine")
            data_fine = None if senza_fine else c_end.date_input("Data fine", datetime.now(), key="ric_data_fine")

            if st.form_submit_button("＋ Aggiungi Ricorrente", use_container_width=False):
                if descrizione and importo > 0:
                    try:
                        db.aggiungi_spesa_ricorrente(descrizione, importo, giorno_scad, freq, data_inizio, data_fine, user_email=user_email)
                        db.carica_spese_ricorrenti.clear()
                        # reset manuale campi chiave
                        for _k in ["ric_desc", "ric_importo", "ric_giorno"]:
                            st.session_state.pop(_k, None)
                        st.session_state["_banner_ric"] = True
                        st.rerun()
                    except Exception as _exc:
                        st.error(f"Errore salvataggio: {_exc}")
                else:
                    st.warning("Inserisci descrizione e importo maggiore di zero.")
 
        # Banner conferma salvataggio (mostrato nel ciclo dopo il rerun)
        if st.session_state.pop("_banner_ric", False):
            st.success("✅ Spesa ricorrente salvata con successo!")

        # Tabella ricorrenti
        df_ric_view = db.carica_spese_ricorrenti(user_email)
        if not df_ric_view.empty:
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

            # ── Header tabella ──
            tot_mensile = df_ric_view["importo"].sum()
            FREQ_MAP = {1:"Mensile",2:"Bimestrale",3:"Trimestrale",4:"Quadrimestrale",6:"Semestrale",12:"Annuale"}
            FREQ_STYLE = {
                "Mensile":   ("#82b4f7", "rgba(79,142,240,0.10)",  "rgba(79,142,240,0.28)"),
                "Annuale":   ("#f5a623", "rgba(245,166,35,0.10)",   "rgba(245,166,35,0.25)"),
                "Semestrale":("#9b74f5", "rgba(155,116,245,0.10)",  "rgba(155,116,245,0.25)"),
            }
            ric_rows_html = []
            for _, row in df_ric_view.iterrows():
                freq_n = int(row.get("frequenza_mesi", 1))
                freq_lbl = FREQ_MAP.get(freq_n, f"{freq_n}m")
                fc, fbg, fbd = FREQ_STYLE.get(freq_lbl, ("#82b4f7","rgba(79,142,240,0.10)","rgba(79,142,240,0.28)"))
                fine_val = row.get("data_fine")
                fine_str = str(fine_val)[:10] if (fine_val and str(fine_val) not in ["None","NaT",""]) else "—"
                importo_it = format_eur(float(row.get("importo", 0)), decimals=2)
                desc_txt = str(row["descrizione"])
                ric_rows_html.append(
                    _reg_table_row([
                        _reg_table_td(escape(str(row["id"])),   color="#5a6f8c", mono=True),
                        _reg_table_td(escape(desc_txt),         color="#dde6f5", weight=500, title=desc_txt),
                        _reg_table_td(importo_it,               color="#f26a6a", mono=True, weight=600),
                        _reg_table_td(_chip(freq_lbl, fc, fbg, fbd), nowrap=False),
                        _reg_table_td(str(int(row.get("giorno_scadenza", 0))), color="#5a6f8c", mono=True, align="center"),
                        _reg_table_td(str(row.get("data_inizio",""))[:10],     color="#5a6f8c", mono=True, align="center"),
                        _reg_table_td(fine_str,                                color="#5a6f8c", mono=True, align="center"),
                    ])
                )

            st.markdown(
                _render_reg_scroll_table(
                    title="Elenco ricorrenti registrate",
                    right_html=f"{format_eur(tot_mensile, decimals=2)} / mese",
                    columns=[
                        ("#",           "left"),
                        ("Descrizione", "left"),
                        ("Importo",     "left"),
                        ("Frequenza",   "left"),
                        ("Scad.",       "center"),
                        ("Inizio",      "center"),
                        ("Fine",        "center"),
                    ],
                    widths=[0.45, 2.6, 1.1, 1.25, 0.7, 1.1, 0.9],
                    rows_html=ric_rows_html,
                    height_px=320,
                ),
                unsafe_allow_html=True,
            )
            st.caption("Per eliminare una riga, selezionala qui sotto e clicca su Elimina.")

            def _label_ric(sid):
                rows = df_ric_view[df_ric_view["id"] == sid]
                if rows.empty:
                    return str(sid)
                r = rows.iloc[0]
                return f"{r['descrizione']} | {format_eur(r['importo'], decimals=2)} | scad. {int(r.get('giorno_scadenza', 0))}"

            col_sel_ric, col_btn_ric = st.columns([4, 1], vertical_alignment="bottom")
            ric_id = col_sel_ric.selectbox(
                "Seleziona ricorrente da eliminare",
                df_ric_view["id"].tolist(),
                format_func=_label_ric,
                key="sel_del_ric",
            )
            if col_btn_ric.button("🗑️ Elimina", key="btn_del_ric", use_container_width=True):
                st.session_state["pending_delete_ric"] = ric_id

            if "_success_ric_ts" in st.session_state:
                if datetime.now().timestamp() - st.session_state["_success_ric_ts"] < 3:
                    st.success("✅ Spesa ricorrente eliminata.")
                    time.sleep(0.3)
                    st.rerun()
                else:
                    del st.session_state["_success_ric_ts"]

            if st.session_state.get("pending_delete_ric") is not None:
                sid = st.session_state["pending_delete_ric"]
                desc = df_ric_view.loc[df_ric_view["id"] == sid, "descrizione"].values[0] if sid is not None else ""
                st.warning(f"⚠️ Elimina **{desc}**? Operazione irreversibile.")
                cc1, cc2 = st.columns(2)
                if cc1.button("🗑️ Sì, elimina", key="confirm_del_ric", use_container_width=True, type="primary"):
                    db.elimina_spesa_ricorrente(sid, user_email=user_email)
                    db.carica_spese_ricorrenti.clear()
                    del st.session_state["pending_delete_ric"]
                    st.session_state["_success_ric_ts"] = datetime.now().timestamp()
                    st.rerun()
                if cc2.button("Annulla", key="cancel_del_ric", use_container_width=True):
                    del st.session_state["pending_delete_ric"]
                    st.rerun()
        else:
            st.caption("Nessuna spesa ricorrente inserita.")
 
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
 
    # ── NUOVO FINANZIAMENTO ──
    with st.container(border=True):
        n_fin = len(df_fin_db) if not df_fin_db.empty else 0
        st.markdown(f"""
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
  <div style="display:flex;align-items:center;gap:10px;">
    <div style="width:28px;height:28px;border-radius:7px;background:rgba(79,142,240,0.12);
                display:flex;align-items:center;justify-content:center;font-size:15px;">🏦</div>
    <span style="font-family:'Plus Jakarta Sans',sans-serif;font-size:13px;font-weight:700;
                 color:#dde6f5;letter-spacing:-0.1px;">Nuovo Finanziamento</span>
  </div>
  <span style="font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:400;
               padding:3px 10px;border-radius:20px;background:rgba(79,142,240,0.12);
               color:#82b4f7;border:1px solid rgba(79,142,240,0.28);">{n_fin} attivi</span>
</div>""", unsafe_allow_html=True)
 
        with st.form("form_finanziamento", clear_on_submit=False):
            c1, c2, c3 = st.columns(3)
            nome_fin = c1.text_input("Nome finanziamento", placeholder="Es. Mutuo Casa, Prestito Auto…", key="fin_nome")
            capitale = c2.number_input("Capitale iniziale (€)", min_value=0.0, step=0.1, format="%.2f", key="fin_capitale")
            taeg = c3.number_input("TAEG (%)", min_value=0.0, step=0.01, key="fin_taeg")
            c4, c5, c6, c7 = st.columns(4)
            durata = c4.number_input("Durata (mesi)", min_value=1, step=1, key="fin_durata")
            data_inizio_fin = c5.date_input("Data inizio", key="fin_data_inizio")
            giorno_scad_fin = c6.number_input("Giorno scadenza", min_value=1, max_value=31, step=1, value=1, key="fin_giorno")
            rate_pagate_input = c7.number_input(
                "Rate già pagate", min_value=0, step=1, value=0, key="fin_rate",
                help="Usa questo campo se i movimenti storici non coprono tutte le rate già saldate.",
            )
            if st.form_submit_button("💾 Salva Finanziamento", use_container_width=False):
                if nome_fin and capitale > 0 and durata > 0:
                    try:
                        rate_pagate_val = int(rate_pagate_input) if int(rate_pagate_input) > 0 else None
                        db.aggiungi_finanziamento(
                            nome_fin, capitale, taeg, durata, data_inizio_fin,
                            giorno_scad_fin, rate_pagate=rate_pagate_val, user_email=user_email,
                        )
                        db.carica_finanziamenti.clear()
                        for k in ["fin_nome", "fin_capitale", "fin_taeg", "fin_durata", "fin_rate", "fin_giorno"]:
                            if k in st.session_state:
                                del st.session_state[k]
                        st.success("✅ Finanziamento salvato!")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Errore salvataggio: {exc}")
                else:
                    st.warning("Compila nome, capitale e durata.")
 
        if not df_fin_db.empty:
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            # Header tabella finanziamenti
            fin_rows_html = []
            for _, f in df_fin_db.iterrows():
                dati_b = log.calcolo_finanziamento(
                    f["capitale_iniziale"], f["taeg"],
                    f["durata_mesi"], f["data_inizio"], f["giorno_scadenza"],
                )
                rate_db  = int(f["rate_pagate"]) if "rate_pagate" in f.index and pd.notna(f["rate_pagate"]) else None
                rate_mov = _mesi_pagati_da_mov(df_mov, f["nome"], dati_b["rata"], data_inizio=f["data_inizio"])
                rate_cal = int(dati_b.get("mesi_pagati", 0))
                vals_r   = [v for v in [rate_db, rate_mov, rate_cal] if v is not None]
                rate_eff = max(vals_r) if vals_r else None
                dati     = log.calcolo_finanziamento(
                    f["capitale_iniziale"], f["taeg"],
                    f["durata_mesi"], f["data_inizio"], f["giorno_scadenza"],
                    rate_pagate_override=rate_eff,
                )
                taeg_pct = f["taeg"]
                taeg_c  = "#f5a623" if taeg_pct > 5 else "#10d98a"
                taeg_bg = "rgba(245,166,35,0.10)" if taeg_pct > 5 else "rgba(16,217,138,0.10)"
                taeg_bd = "rgba(245,166,35,0.26)" if taeg_pct > 5 else "rgba(16,217,138,0.26)"
                nome_txt = str(f["nome"])
                fin_rows_html.append(
                    _reg_table_row([
                        _reg_table_td(f"<strong>{escape(nome_txt)}</strong>", color="#dde6f5", weight=600, title=nome_txt),
                        _reg_table_td(format_eur(f["capitale_iniziale"], 0), color="#dde6f5", mono=True),
                        _reg_table_td(_chip(f"{taeg_pct:.2f}%", taeg_c, taeg_bg, taeg_bd), nowrap=False),
                        _reg_table_td(f"{int(f['durata_mesi'])}m",             color="#5a6f8c", mono=True, align="center"),
                        _reg_table_td(str(f["data_inizio"])[:10],              color="#5a6f8c", mono=True, align="center"),
                        _reg_table_td(str(int(f["giorno_scadenza"])),          color="#5a6f8c", mono=True, align="center"),
                        _reg_table_td(format_eur(dati["rata"], 2),             color="#f26a6a", mono=True, weight=600),
                        _reg_table_td(str(rate_eff or 0),                      color="#5a6f8c", mono=True, align="center"),
                    ])
                )

            # Totale rate mensili
            try:
                totale_rate = sum(
                    log.calcolo_finanziamento(
                        r["capitale_iniziale"], r["taeg"], r["durata_mesi"],
                        r["data_inizio"], r["giorno_scadenza"]
                    )["rata"]
                    for _, r in df_fin_db.iterrows()
                )
                right_fin = f"{format_eur(totale_rate, 2)} / mese"
            except Exception:
                right_fin = ""

            st.markdown(
                _render_reg_scroll_table(
                    title="Finanziamenti in corso",
                    right_html=right_fin,
                    columns=[
                        ("Nome",       "left"),
                        ("Capitale",   "left"),
                        ("TAEG",       "left"),
                        ("Durata",     "center"),
                        ("Inizio",     "center"),
                        ("Scad.",      "center"),
                        ("Rata stim.", "left"),
                        ("Rate pag.",  "center"),
                    ],
                    widths=[1.8, 1.2, 0.9, 0.8, 1.1, 0.7, 1.1, 0.9],
                    rows_html=fin_rows_html,
                    height_px=280,
                ),
                unsafe_allow_html=True,
            )
            st.caption("Per eliminare una riga, selezionala qui sotto.")

            def _label_fin(nome):
                rows = df_fin_db[df_fin_db["nome"] == nome]
                if rows.empty:
                    return str(nome)
                r = rows.iloc[0]
                return f"{r['nome']} | {format_eur(r['capitale_iniziale'], 0)} | {int(r['durata_mesi'])} mesi"

            col_sel_fin, col_btn_fin = st.columns([4, 1], vertical_alignment="bottom")
            fin_nome = col_sel_fin.selectbox(
                "Seleziona finanziamento da eliminare",
                df_fin_db["nome"].tolist(),
                format_func=_label_fin,
                key="sel_del_fin",
            )
            if col_btn_fin.button("🗑️ Elimina", key="btn_del_fin", use_container_width=True):
                st.session_state["pending_delete_fin"] = fin_nome

            if "_success_fin_ts" in st.session_state:
                if datetime.now().timestamp() - st.session_state["_success_fin_ts"] < 3:
                    st.success("✅ Finanziamento eliminato.")
                    time.sleep(0.3)
                    st.rerun()
                else:
                    del st.session_state["_success_fin_ts"]

            if st.session_state.get("pending_delete_fin") is not None:
                fnome = st.session_state["pending_delete_fin"]
                st.warning(f"⚠️ Elimina finanziamento **{fnome}**? Operazione irreversibile.")
                cc1, cc2 = st.columns(2)
                if cc1.button("🗑️ Sì, elimina", key="confirm_del_fin", use_container_width=True, type="primary"):
                    db.elimina_finanziamento(fnome, user_email=user_email)
                    db.carica_finanziamenti.clear()
                    del st.session_state["pending_delete_fin"]
                    st.session_state["_success_fin_ts"] = datetime.now().timestamp()
                    st.rerun()
                if cc2.button("Annulla", key="cancel_del_fin", use_container_width=True):
                    del st.session_state["pending_delete_fin"]
                    st.rerun()
 
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
 
    # ── STORICO MOVIMENTI ── 
    with st.container(border=True):
        st.markdown("""
<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;">
  <div style="width:28px;height:28px;border-radius:7px;background:rgba(79,142,240,0.12);
              display:flex;align-items:center;justify-content:center;font-size:15px;">📜</div>
  <span style="font-family:'Plus Jakarta Sans',sans-serif;font-size:13px;font-weight:700;
               color:#dde6f5;letter-spacing:-0.1px;">Storico Movimenti</span>
</div>""", unsafe_allow_html=True)
        
        c_f1, c_f2, c_f3 = st.columns([1, 1, 2])
        mese_reg = c_f1.selectbox("Mese", list(MONTH_NAMES.keys()), index=mese_sel - 1, format_func=lambda x: MONTH_NAMES[x])
        anno_reg = c_f2.selectbox("Anno", anni_disponibili, index=anni_disponibili.index(anno_sel) if anno_sel in anni_disponibili else 0)
        mostra_tutto = c_f3.checkbox("Mostra tutte le transazioni", value=False)
 
        df_reg = df_mov.copy()
        if not mostra_tutto:
            df_reg = df_reg[(df_reg["Data"].dt.month == mese_reg) & (df_reg["Data"].dt.year == anno_reg)]
 
        c_f4, c_f5, c_f6 = st.columns([1, 1, 2])
        with c_f4:
            tipo_radio = st.radio(
                "Tipo",
                ["Tutte", "↑ Uscita", "↓ Entrata"],
                horizontal=True,
                key="storico_tipo_radio",
            )
            if tipo_radio == "↑ Uscita":
                tipo_filter = ["USCITA"]
            elif tipo_radio == "↓ Entrata":
                tipo_filter = ["ENTRATA"]
            else:
                tipo_filter = ["USCITA", "ENTRATA"]
        categoria_filter = c_f5.multiselect("Categoria", sorted(df_reg["Categoria"].dropna().unique()))
        testo_filter = c_f6.text_input("Cerca in Dettaglio / Note", placeholder="Cerca…")
        st.markdown('</div>', unsafe_allow_html=True)
 
        if tipo_filter:
            df_reg = df_reg[df_reg["Tipo"].isin(tipo_filter)]
        if categoria_filter:
            df_reg = df_reg[df_reg["Categoria"].isin(categoria_filter)]
        if testo_filter:
            t = testo_filter.lower()
            df_reg = df_reg[
                df_reg["Dettaglio"].astype(str).str.lower().str.contains(t, na=False) |
                df_reg["Note"].astype(str).str.lower().str.contains(t, na=False)
            ]

        if "Id" in df_reg.columns:
            df_reg = df_reg.sort_values(by=["Data", "Id"], ascending=[False, False])
        else:
            df_reg = df_reg.sort_values(by="Data", ascending=False)

        def _label_mov(i):
            if "Id" not in df_reg.columns:
                return str(i)
            rows = df_reg[df_reg["Id"] == i]
            if rows.empty:
                return str(i)
            r = rows.iloc[0]
            data_txt = r["Data"].strftime("%d/%m/%Y") if pd.notna(r["Data"]) else ""
            dettaglio_txt = str(r.get("Dettaglio", "") or "").strip()
            return f"{i} | {data_txt} | {r['Tipo']} | {dettaglio_txt} | {eur2(r['Importo'])}"

        if not df_reg.empty:
            totale_mov = len(df_reg)
            uscite_tot = df_reg[df_reg["Tipo"] == "USCITA"]["Importo"].sum()
            mov_rows_html = []
            for _, row in df_reg.iterrows():
                row_id = row["Id"] if "Id" in row.index else _
                data_txt = row["Data"].strftime("%d/%m/%Y") if pd.notna(row.get("Data")) else "—"
                categoria_txt = str(row.get("Categoria", "") or "—")
                dettaglio_txt = str(row.get("Dettaglio", "") or "—")
                note_raw = str(row.get("Note", "") or "").strip()
                note_txt = note_raw if note_raw else "—"
                importo_color = "#10d98a" if str(row.get("Tipo", "")).upper() == "ENTRATA" else "#f26a6a"
                mov_rows_html.append(
                    _reg_table_row([
                        _reg_table_td(escape(str(row_id)),            color="#5a6f8c", mono=True),
                        _reg_table_td(data_txt,                       color="#5a6f8c", mono=True),
                        _reg_table_td(_tipo_chip(row.get("Tipo")),    nowrap=False),
                        _reg_table_td(escape(categoria_txt),          color="#5a6f8c", title=categoria_txt),
                        _reg_table_td(f"<strong>{escape(dettaglio_txt)}</strong>", color="#dde6f5", weight=600, title=dettaglio_txt),
                        _reg_table_td(format_eur(row.get("Importo", 0), 2), color=importo_color, mono=True, weight=600),
                        _reg_table_td(escape(note_txt),               color="#5a6f8c", title=note_txt),
                    ])
                )

            st.markdown(
                _render_reg_scroll_table(
                    title="Storico movimenti",
                    right_html=f"{totale_mov} righe",
                    columns=[
                        ("ID",         "left"),
                        ("Data",       "left"),
                        ("Tipo",       "left"),
                        ("Categoria",  "left"),
                        ("Dettaglio",  "left"),
                        ("Importo",    "left"),
                        ("Note",       "left"),
                    ],
                    widths=[0.45, 0.9, 0.9, 1.0, 1.7, 0.95, 1.3],
                    rows_html=mov_rows_html,
                    height_px=420,
                ),
                unsafe_allow_html=True,
            )
            st.caption("Per eliminare una riga, selezionala qui sotto.")

            col_sel_mov, col_btn_mov = st.columns([4, 1], vertical_alignment="bottom")
            mov_id = col_sel_mov.selectbox(
                "Seleziona movimento da eliminare",
                df_reg["Id"].tolist(),
                format_func=_label_mov,
                key="sel_del_mov",
            )
            if col_btn_mov.button("🗑️ Elimina", key="btn_del_mov", use_container_width=True):
                st.session_state["pending_delete_mov"] = mov_id
        else:
            st.markdown(
                _render_reg_scroll_table(
                    title="Storico movimenti",
                    right_html="0 righe",
                    columns=[
                        ("ID",        "left"),
                        ("Data",      "left"),
                        ("Tipo",      "left"),
                        ("Categoria", "left"),
                        ("Dettaglio", "left"),
                        ("Importo",   "left"),
                        ("Note",      "left"),
                    ],
                    widths=[0.45, 0.9, 0.9, 1.0, 1.7, 0.95, 1.3],
                    rows_html=[],
                    height_px=160,
                    empty_message="Nessun movimento trovato con i filtri selezionati.",
                ),
                unsafe_allow_html=True,
            )

        if "_success_mov_ts" in st.session_state:
            if datetime.now().timestamp() - st.session_state["_success_mov_ts"] < 3:
                st.success("✅ Movimento eliminato con successo.")
                time.sleep(0.5)
                st.rerun()
            else:
                del st.session_state["_success_mov_ts"]

        if st.session_state.get("pending_delete_mov") is not None:
            mid = st.session_state["pending_delete_mov"]
            st.warning(f"⚠️ Stai per eliminare il movimento **{_label_mov(mid)}**. Operazione irreversibile.")
            cc1, cc2 = st.columns(2)
            if cc1.button("🗑️ Sì, elimina", key="confirm_del_mov", use_container_width=True, type="primary"):
                db.elimina_movimento(mid, user_email)
                db.carica_dati.clear()
                del st.session_state["pending_delete_mov"]
                st.session_state["_success_mov_ts"] = datetime.now().timestamp()
                st.rerun()
            if cc2.button("Annulla", key="cancel_del_mov", use_container_width=True):
                del st.session_state["pending_delete_mov"]
                st.rerun()
 
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
 
    # ── BACKUP DATI ──
    with st.container(border=True):
        st.markdown("""
<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
  <div style="width:50px;height:28px;border-radius:7px;background:rgba(79,142,240,0.12);
              display:flex;align-items:center;justify-content:center;font-size:15px;">🗄️</div>
  <span style="font-family:'Plus Jakarta Sans',sans-serif;font-size:19px;font-weight:700;
               color:#dde6f5;letter-spacing:-0.1px;">Backup Dati</span>
</div>""", unsafe_allow_html=True)
 
        @st.cache_data(ttl=0, show_spinner=False)
        def _genera_sql_backup(email):
            import psycopg2
            from config_runtime import get_secret
            db_url = get_secret("DATABASE_URL") or get_secret("DATABASE_URL_POOLER")
            if not db_url:
                return None
            tabelle = ["movimenti", "asset_settings", "finanziamenti", "spese_ricorrenti"]
            try:
                conn = psycopg2.connect(db_url)
                cursor = conn.cursor()
                ora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                blocchi = [
                    f"-- Personal Budget — Backup dati",
                    f"-- Utente: {email}",
                    f"-- Data  : {ora}",
                    "SET client_encoding = 'UTF8';",
                ]
                for tabella in tabelle:
                    blocchi.append(f"\n-- Tabella: {tabella}")
                    try:
                        cursor.execute(f"SELECT * FROM {tabella} WHERE user_email = %s", (email,))
                        righe = cursor.fetchall()
                        colonne = [desc[0] for desc in cursor.description]
                        for riga in righe:
                            valori = []
                            for v in riga:
                                if v is None:
                                    valori.append("NULL")
                                elif isinstance(v, bool):
                                    valori.append("TRUE" if v else "FALSE")
                                elif isinstance(v, (int, float)):
                                    valori.append(str(v))
                                else:
                                    valori.append(f"'{str(v).replace(chr(39), chr(39)*2)}'")
                            blocchi.append(
                                f"INSERT INTO {tabella} ({', '.join(colonne)}) "
                                f"VALUES ({', '.join(valori)});"
                            )
                    except Exception as exc:
                        blocchi.append(f"-- ERRORE {tabella}: {exc}")
                cursor.close()
                conn.close()
                return "\n".join(blocchi)
            except Exception:
                return None
 
        sql_backup = _genera_sql_backup(user_email)
        col_txt, col_btn = st.columns([3, 1], vertical_alignment="bottom")
        col_txt.markdown(
            "<div style='font-size:0.90rem;color:#5a6f8c;line-height:1.7;'>"
            "<p style='margin-bottom:4px;'>Scarica una <strong style='color:#dde6f5;'>copia completa</strong> dei tuoi dati in formato SQL.</p>"
            "<p style='margin:0;'>Conservala in un posto sicuro — accessibile anche senza l'app.</p></div>",
            unsafe_allow_html=True,
        )
        if sql_backup:
            data_oggi = datetime.now().strftime("%Y-%m-%d")
            col_btn.download_button(
                label="⬇ Scarica backup",
                data=sql_backup.encode("utf-8"),
                file_name=f"personal_budget_backup_{data_oggi}.sql",
                mime="text/plain",
                use_container_width=True,
            )
        else:
            col_btn.caption("Backup non disponibile.")