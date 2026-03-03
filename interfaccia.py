# streamlit run interfaccia.py
#per abilitare login e registrazione cambiare in secrets la chiave, da demo only a normal.

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
                        st.experimental_set_query_params()
                    except Exception:
                        pass
                    st.success("Accesso autorizzato.")
                    st.rerun()
                if not email_google:
                    st.error("Impossibile leggere l'email dal profilo Google.")

    st.stop()


# --- CSS PERSONALIZZATO (Stile Dashboard Dark) ---
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
    :root {
        --bg: #0b1020;
        --panel: #141b2d;
        --panel-2: #101626;
        --panel-border: rgba(255,255,255,0.08);
        --text: #e6eef9;
        --muted: #fffffff0;
        --accent:#f0b429;
        --accent-2: #2dd4bf;
        --accent-3: #f472b6;
        --good: #22c55e;
        --bad: #ef4444;
    }
    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background: radial-gradient(1200px 700px at 10% -20%, #0e1426 0%, var(--bg) 50%);
        color: var(--text);
        font-family: "IBM Plex Sans", sans-serif;
    }
    [data-testid="stSidebar"] {
        background: #0e1426;
        border-right: 1px solid rgba(255,255,255,0.06);
    }
    [data-testid="stSidebar"] div.stButton > button {
        padding: 8px 12px !important;
        height: auto !important;
        min-height: 25px !important;
        line-height: 1 !important;
        font-size: 0.75rem !important;
        border-radius: 5px !important;
        margin-top: 5px !important;
        background-color: transparent !important;
        color: #ff4b4b !important;
        border: 1px solid #ff4b4b !important;
    }
    h1, h2, h3, h4, h5, h6 {
        font-family: "Space Grotesk", sans-serif;
        color: var(--text);
    }
    .block-container { padding-top: 4.0rem; }
    div[data-testid="stMetric"] {
        background: var(--panel);
        border: 1px solid var(--panel-border);
        border-left: 4px solid var(--accent);
        border-radius: 20px;
        padding: 10px 30px;
        box-shadow: 0 8px 20px rgba(0,0,0,0.25);
    }
    .stTabs [data-baseweb="tab-list"] { gap: 20px; }
    .stTabs [data-baseweb="tab"] {
        height: 44px;
        background-color: var(--panel-2);
        color: var(--muted);
        border-radius: 10px 10px 0 0;
        padding: 8px 16px;
        border: 1px solid var(--panel-border);
    }
    .stTabs [aria-selected="true"] {
        background-color: var(--panel);
        color: var(--text);
        border-bottom: 2px solid var(--accent);
    }
    .section-title {
        font-size: 1.80rem;
        letter-spacing: 0.10em;
        color: var(--muted);
        text-transform: uppercase;
        margin-bottom: 0.2rem;
        font-weight: bold;
    }
    .panel-title {
        font-weight: bold;
        font-size: 1.20rem;
        color: var(--text);
        margin: 0 0 0.0rem 0;
    }
    .kpi-note { color: var(--muted); font-size: 0.85rem; }
    .badge {
        display: inline-block;
        padding: 4px 20px;
        border-radius: 999px;
        font-size: 0.85rem;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        background: rgba(240,180,41,0.15);
        color: #facc15;
        border: 1px solid rgba(240,180,41,0.35);
    }
    .badge-green { background: rgba(34,197,94,0.15); color: #46be9a; border-color: rgba(34,197,94,0.35); }
    .badge-red { background: rgba(239,68,68,0.15); color: #ef4444; border-color: rgba(239,68,68,0.35); }
    .badge-blue { background: rgba(96,165,250,0.15); color: #60a5fa; border-color: rgba(96,165,250,0.35); }
    .badge-pink { background: rgba(244,114,182,0.15); color: #f472b6; border-color: rgba(244,114,182,0.35); }
    .stDataFrame, .stTable { background: var(--panel); }
    .stPlotlyChart > div {
        background: var(--panel);
        border: 2px solid var(--panel-border);
        border-radius: 20px;
        padding: 5px;
        box-shadow: 0 8px 20px rgba(0,0,0,0.25);
    }
    .js-plotly-plot text { font-weight: 800 !important; }
    .side-title { font-weight: 800; font-size: 1.1rem; margin: 0.8rem 0 0.4rem 0; }
    .side-chip {
        display: inline-block;
        padding: 8px 12px;
        border-radius: 999px;
        border: 1px solid rgba(96,165,250,0.5);
        color: #60a5fa;
        background: rgba(96,165,250,0.12);
        font-weight: 600;
        margin-bottom: 0.6rem;
    }
    .side-residuo {
        background: var(--panel);
        border: 1px solid rgba(34,197,94,0.45);
        border-radius: 16px;
        padding: 10px 14px;
        text-align: center;
        box-shadow: 0 8px 20px rgba(0,0,0,0.25);
        color: #22c55e;
        font-weight: 800;
        font-size: 1.35rem;
        letter-spacing: 0.02em;
    }
    .side-residuo.neg { border-color: rgba(239,68,68,0.55); color: #ef4444; }
    .side-residuo .label {
        display: block;
        font-size: 0.9rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--muted);
        margin-bottom: 6px;
    }
    .side-residuo .pill {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: rgba(34,197,94,0.18);
        border: 1px solid rgba(34,197,94,0.55);
        color: #22c55e;
        padding: 6px 10px;
        border-radius: 999px;
        font-weight: 800;
        font-size: 1.2rem;
    }
    .side-residuo.neg .pill {
        background: rgba(239,68,68,0.18);
        border-color: rgba(239,68,68,0.55);
        color: #ef4444;
    }
    .progress-wrap { margin-top: 6px; }
    .progress-track {
        width: 100%;
        height: 14px;
        background: rgba(255,255,255,0.12);
        border-radius: 999px;
        overflow: hidden;
        box-shadow: inset 0 0 0 1px rgba(255,255,255,0.05);
    }
    .progress-fill {
        height: 100%;
        background: linear-gradient(90deg, #22c55e 0%, #34d399 100%);
        border-radius: 999px;
    }
    .block-container { padding-top: 2.1rem; padding-bottom: 0.8rem; }
    .element-container { margin-bottom: 0rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- AVVIO APP ---
@st.cache_resource
def _ensure_db_ready():
    db.inizializza_db()
    return True


_ensure_db_ready()
AUTH_USER_EMAIL = _require_login()
user_email = AUTH_USER_EMAIL
# Banner demo: visibile solo quando accede l'account demo.
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
    conn_local = db.connetti_db()
    try:
        df = pd.read_sql(
            "SELECT chiave, valore_numerico, valore_testo "
            "FROM asset_settings WHERE user_email = %s",
            conn_local,
            params=(user_email,),
        )
        if df.empty:
            return pd.DataFrame(columns=["valore_numerico", "valore_testo"]).set_index(pd.Index([]))
        # Difesa ulteriore: in caso di dati storici duplicati manteniamo l'ultima riga per chiave.
        df = df.drop_duplicates(subset=["chiave"], keep="last")
        return df.set_index("chiave")
    except Exception:
        return pd.DataFrame(columns=["valore_numerico", "valore_testo"]).set_index(pd.Index([]))
    finally:
        conn_local.close()


def _save_settings_batch(num_payload=None, txt_payload=None):
    num_payload = num_payload or {}
    txt_payload = txt_payload or {}
    if not user_email:
        return False, "Utente non autenticato."
    conn_local = db.connetti_db()
    cur = conn_local.cursor()
    try:
        upsert_q = """
            INSERT INTO asset_settings (chiave, user_email, valore_numerico, valore_testo)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (chiave, user_email) DO UPDATE SET
                valore_numerico = EXCLUDED.valore_numerico,
                valore_testo = EXCLUDED.valore_testo
        """
        for key, value in num_payload.items():
            cur.execute(
                upsert_q,
                (
                    str(key),
                    user_email,
                    float(value) if value is not None else None,
                    None,
                ),
            )
        for key, value in txt_payload.items():
            cur.execute(
                upsert_q,
                (
                    str(key),
                    user_email,
                    None,
                    str(value) if value is not None else "",
                ),
            )
        conn_local.commit()
        return True, ""
    except Exception as e:
        conn_local.rollback()
        return False, str(e)
    finally:
        conn_local.close()


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
    """Evidenzia pagato/non pagato nel calendario scadenze."""
    if df is None or df.empty:
        return df

    sty = style_df_currency(df, ["Importo"])
    if not hasattr(sty, "apply"):
        return sty

    def _row_style(row):
        stato = str(row.get("Stato", "")).upper()
        if "PAGATO" in stato:
            return ["background-color: rgba(34,197,94,0.20); color: #e9fff2;" for _ in row]
        if "IN SCADENZA" in stato:
            # giallo tenue
            return ["background-color: rgba(250,204,21,0.20);" for _ in row]
        if "DA PAGARE" in stato:
            return ["background-color: rgba(239,68,68,0.12);" for _ in row]
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
        font=dict(color="#e6eef9", size=12),
        margin=dict(l=10, r=10, t=45, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=0),
        height=height,
        xaxis_title=None,
        yaxis_title=None,
        showlegend=show_legend,
        legend_title_text="",
        separators=".",
    )
    if title:
        layout_kwargs["title"] = dict(text=title, x=0.02, xanchor="left")
    else:
        layout_kwargs["title_text"] = ""
    fig.update_layout(**layout_kwargs)
    fig.update_layout(separators=".")
    fig.update_xaxes(showgrid=False, zeroline=False, tickfont=dict(size=12, color="#fafcff"))
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.08)", zeroline=False, tickfont=dict(size=12, color="#fafcff"))
    return fig

def show_chart(fig, height=300, show_legend=True):
    fig.update_traces(textfont=dict(size=12))
    st.plotly_chart(style_fig(fig, height=height, show_legend=show_legend), use_container_width=True, config=PLOTLY_CONFIG)

def badge(text, variant=""):
    cls = f"badge {variant}".strip()
    return f"<span class='{cls}'>{text}</span>"

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
    #st.caption(f"Dati iniziali: {saldo_iniziale_key}, {risp_prev_key}")

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
        }
        text_payload = {
            "pac_ticker": str(pac_ticker_set).strip(),
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

# --- KPI SUPERIORI (Sempre visibili) ---
kpi = log.calcola_kpi_dashboard(df_mov, mese_sel, anno_sel)

st.markdown(
    f"<div class='section-title' style='color: #facc15; font-style: italic;'>" f"{NOME_DISPLAY} - PERSONAL DASHBOARD" f"</div>",unsafe_allow_html=True)
st.markdown(f"### {MONTH_NAMES.get(mese_sel, mese_sel)} {anno_sel}")

saldo_iniziale = s_num_candidates([f"saldo_iniziale_{anno_sel}", f"saldo iniziale_{anno_sel}"], 0.0)
saldo_disponibile = log.saldo_disponibile_da_inizio(df_mov, anno_sel, mese_sel, saldo_iniziale)

c1, c2, c3, c4 = st.columns(4)

# Stile comune per le card (sfondo, bordi arrotondati, padding)
card_style = "background-color: #141B2D; padding: 9px; border-radius: 15px; border: 1px solid #2e364f; height: 100px;"
distanza = "-15px"
c1.markdown(f"""
    <div style="{card_style} text-align: center; display: flex; flex-direction: column; justify-content: center; align-items: center;">
        <p style='margin: 0 0 {distanza} 0; font-size:20px; color:#ffffff; font-weight:bold; text-transform: uppercase;'>
            Saldo Disponibile
        </p>
        <h2 style='margin:0; color:#41D0A6; font-size:40px;'>
            {eur2(saldo_disponibile)}
        </h2>
    </div>
""", unsafe_allow_html=True)

# KPI 2: USCITE
c2.markdown(f"""
    <div style="{card_style} text-align: center; display: flex; flex-direction: column; justify-content: center; align-items: center;">
        <p style='margin: 0 0 {distanza} 0; font-size:20px; color:#ffffff; font-weight:bold; text-transform: uppercase;'>
            Uscite Mese
        </p>
        <h2 style='margin:0; color:#FA598E; font-size:40px;'>
            {eur2(kpi['uscite_mese'])}
        </h2>
    </div>
""", unsafe_allow_html=True)

# KPI 3: RISPARMIO
c3.markdown(f"""
    <div style="{card_style} text-align: center; display: flex; flex-direction: column; justify-content: center; align-items: center;">
        <p style='margin: 0 0 {distanza} 0; font-size:20px; color:#ffffff; font-weight:bold; text-transform: uppercase;'>
            Risparmio Mese
        </p>
        <h2 style='margin:0; color:#41d0a6; font-size:40px;'>
            {eur2(kpi['risparmio_mese'])}
        </h2>
    </div>
""", unsafe_allow_html=True)

# KPI 4: TASSO
c4.markdown(f"""
    <div style="{card_style} text-align: center; display: flex; flex-direction: column; justify-content: center; align-items: center;">
        <p style='margin: 0 0 {distanza} 0; font-size:20px; color:#ffffff; font-weight:bold; text-transform: uppercase;'>
            Tasso Risparmio
        </p>
        <h2 style='margin:0; color:#9b7ae6; font-size:40px;'>
            {kpi['tasso_risparmio']}%
        </h2>
    </div>
""", unsafe_allow_html=True)

st.divider()
# --- DATI FILTRATI ---
mask_mese = (df_mov["Data"].dt.month == mese_sel) & (df_mov["Data"].dt.year == anno_sel)
df_mese = df_mov[mask_mese].copy()
df_anno = df_mov[df_mov["Data"].dt.year == anno_sel].copy()

# --- TAB INTERFACCIA ---
tab_home, tab_charts, tab_assets, tab_debts, tab_admin = st.tabs([
    "🏠 HOME", "📈 ANALISI", "💰 PATRIMONIO", "🏍️ DEBITI", "📝 REGISTRO"
])

# --- TAB 1: HOME ---
with tab_home:
    st.markdown("<div class='section-title'>HOME</div>", unsafe_allow_html=True)

    mesi = list(MONTH_SHORT.values())

    c1, c2 = st.columns([1.35, 1.2])

    with c1:
        st.markdown("<div class='panel-title'>Budget di spesa (50/30/20)</div>", unsafe_allow_html=True)
        if not df_budget.empty:
            cat_order = list(log.PERCENTUALI_BUDGET.keys())
            colors = {
                "NECESSITÀ": ("#9b7ae6", "#4b3a75"),
                "SVAGO": ("#ff5f9b", "#6d2e47"),
                "INVESTIMENTI": ("#41d0a6", "#1f5e52"),
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
            fig_budget.update_yaxes(categoryorder="array", categoryarray=mesi, autorange="reversed", tickfont=dict(size=12))
            fig_budget.update_xaxes(tickprefix="€ ", tickfont=dict(size=12), tickformat=".0f")

            show_chart(fig_budget, height=420, show_legend=False)
        else:
            st.info("Imposta 'budget_mensile_base' o registra spese per vedere il grafico.")

    with c2:
        st.markdown("<div class='panel-title'>Dettaglio spese per categoria </div>", unsafe_allow_html=True)
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
                insidetextanchor="middle",
            )
            fig_det.update_yaxes(tickprefix="€ ", tickformat=",.0f")
            show_chart(fig_det, height=420, show_legend=False)
        else:
            st.info("Nessuna spesa nel mese selezionato.")

    st.markdown("<div class='panel-title'>Calendario spese ricorrenti</div>", unsafe_allow_html=True)
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

            st.dataframe(style_calendario_scadenze(tabella_ric), use_container_width=True, hide_index=True, height=280)

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
        st.markdown("<div class='panel-title'>Obiettivo risparmio</div>", unsafe_allow_html=True) 
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

            # Ombra 3D
            fig_obj.add_bar(
                x=[risp_prev],
                y=[y_prev - 0.12],
                orientation="h",
                width=0.42,
                marker_color="rgba(20,60,50,0.5)",
                showlegend=False,
                hoverinfo="skip",
            )
            fig_obj.add_bar(
                x=[accumulo + mancante],
                y=[y_curr - 0.12],
                orientation="h",
                width=0.42,
                marker_color="rgba(60,20,40,0.45)",
                showlegend=False,
                hoverinfo="skip",
            )

            # Barra 2025 (accumulo)
            fig_obj.add_bar(
                x=[risp_prev],
                y=[y_prev],
                orientation="h",
                width=0.46,
                name="Accumulo",
                marker_color="#41d0a6",
                marker_line=dict(color="rgba(0,0,0,0.5)", width=1),
                text=[eur0(risp_prev)],
                texttemplate="<b>%{text}</b>",
                textposition="inside",
                insidetextanchor="middle",
            )

            # Barra 2026 (accumulo + mancante)
            fig_obj.add_bar(
                x=[accumulo],
                y=[y_curr],
                orientation="h",
                width=0.46,
                name="Accumulo",
                marker_color="#41d0a6",
                marker_line=dict(color="rgba(0,0,0,0.5)", width=1),
                text=[eur0(accumulo, signed=True)],
                texttemplate="<b>%{text}</b>",
                textposition="inside",
                insidetextanchor="middle",
                showlegend=False,
            )
            fig_obj.add_bar(
                x=[mancante],
                y=[y_curr],
                base=[accumulo],
                orientation="h",
                width=0.46,
                name="Mancante",
                marker_color="#6d3456",
                marker_line=dict(color="rgba(0,0,0,0.5)", width=1),
                text=[eur0(mancante)],
                texttemplate="<b>%{text}</b>",
                textposition="inside",
                insidetextanchor="middle",
            )

            # Valori a destra
            fig_obj.add_trace(
                go.Scatter(
                    x=[risp_prev],
                    y=[y_prev],
                    mode="text",
                    text=[eur0(risp_prev)],
                    textposition="middle right",
                    showlegend=False,
                )
            )
            fig_obj.add_trace(
                go.Scatter(
                    x=[accumulo + mancante],
                    y=[y_curr],
                    mode="text",
                    text=[eur0(accumulo + mancante)],
                    textposition="middle right",
                    showlegend=False,
                )
            )

            fig_obj.update_layout(
    barmode="stack",
    showlegend=False,
    margin=dict(l=50, r=50, t=30, b=30),
    annotations=[
        dict(
            text=f"<b>Target +{target_perc:.0f}%</b>",
            x=1,
            y=1.18,
            xref="paper",
            yref="paper",
            showarrow=False,
            align="center",
            font=dict(
                size=13,
                color="#000000",
                weight="bold",
            ),
            bgcolor="#D0B136",
            bordercolor="#141B2D",
            borderpad=10
        )
    ]
)
            fig_obj.update_yaxes(
                tickvals=[y_prev, y_curr],
                ticktext=[str(prev_year), str(anno_sel)],
                range=[-0.6, 1.6],
                autorange=False,
            )
            max_x = max(risp_prev, accumulo + mancante)
            fig_obj.update_xaxes(tickprefix="€ ", tickformat=",.0f", range=[0, max_x * 1.2])
            show_chart(fig_obj, height=300, show_legend=False)
            
        else:
            st.info(f"Imposta il risparmio dell'anno precedente ({prev_year}) nelle impostazioni rapide.")
        
    with c2:
        st.markdown("<div class='panel-title'>Andamento entrate</div>", unsafe_allow_html=True)
    
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
                marker_color="#34d399",
                marker_line=dict(color="rgba(0,0,0,0.5)", width=1),
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

    st.markdown("<div class='panel-title'>Previsione saldo</div>", unsafe_allow_html=True)

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
            color_discrete_sequence=["#60a5fa", "#facc15"],
        )

        fig_prev.update_layout(
            separators=".,",
            margin=dict(l=70, r=10, t=10, b=40),
            legend=dict(
                orientation="h",
                xanchor="left",
                x=0,
                yanchor="top",
                y=0.99,
                title=None,
                bgcolor="rgba(0,0,0,0)",
                borderwidth=0,
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

        show_chart(fig_prev, show_legend=False, height=300)

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
        st.markdown("<div class='panel-title'>PAC - Piano di Accumulo</div>", unsafe_allow_html=True)
    with pac_badge_col:
        pac_badge_slot = st.empty()
    
    # 1. INPUT SETTINGS (Prende i dati dal tuo DB e dai selettori rapidi)
    tic = pac_ticker_corrente if pac_ticker_corrente else s_txt("pac_ticker", "")
    
    st.markdown("""
    <style>
    [data-testid="stMetric"] {
        background-color: #141B2D !important;
        padding: 15px !important;
        border-radius: 25px !important; 
        min-height: 80px !important; 
        border-left: none !important;
        justify-content: left !important;
    }
    [data-testid="stMetricLabel"] p {
        font-size: 18px !important;
        font-weight: 500 !important;
        color: #ffffff !important;
        margin-bottom: 1px !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 36px !important;
        font-weight: 500 !important;
        color: #ffffff !important;
    }
    [data-testid="stMetricDelta"] {
        display: flex !important;
        justify-content: flex-end !important;  
        margin-top: auto !important;    
        font-size: 15px !important;
        font-weight: 600 !important;
    }
    </style>
    """, unsafe_allow_html=True)

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
    f"""
    <div style="font-size: 20px; font-weight: 500; color:#5CE488; margin-bottom: 10px;">
        Versamento mese: {eur2(pac_vers)} | 
        Rendimento annuo stimato: {pac_rend:.2f}%
    </div>
    """, 
    unsafe_allow_html=True
)
        

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Valore attuale", eur2(s["Valore Attuale"]))
        k2.metric("Rendimento", eur2(s["P&L"], signed=True), f"{s['P&L %']}%")
        k3.metric("Tasse plusvalenze", eur2(s["Imposte"]))
        k4.metric("Netto smobilizzo", eur2(s["Netto"]))
        st.caption(f"Versato PAC da registro ({anno_sel}): {eur2(s.get('Versato_Reale_Registro_Anno', s['Versato_Reale_Registro']))}")
        st.markdown("<div class='panel-title'> Proiezione PAC </div>", unsafe_allow_html=True)
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
    st.markdown("<div class='panel-title'>Fondo Pensione</div>", unsafe_allow_html=True)
    valore_quota = fondo_valore_quota_corrente
    q_fondo = fondo_quote_corrente
    inv_fondo = fondo_capitale_base_corrente
    vers_fondo = fondo_vers_corrente
    rendimento_fondo = fondo_rend_corrente
    aliquota_irpef = aliquota_irpef_corrente

    if valore_quota > 0 and q_fondo > 0:
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
        st.markdown(f"<b>Avanzamento versamento</b> ({res_fondo['Avanzamento_Fiscale']['Percentuale']}%)", unsafe_allow_html=True)
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
        st.caption(
            f"Versato anno: {eur2(res_fondo['Avanzamento_Fiscale']['Versato_Anno'])} | "
            f"Rimanente soglia: {eur2(res_fondo['Avanzamento_Fiscale']['Rimanente_Soglia'])}"
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
        st.markdown("<div class='panel-title'> Proiezione Fondo Pensione </div>", unsafe_allow_html=True)
        st.caption(f"Proiezione 30 anni con rendimento annuo stimato: {rendimento_fondo:.2f}%")
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
        st.markdown("<div class='panel-title'>Versamenti PAC / Fondo</div>", unsafe_allow_html=True)
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

    st.markdown("<div class='panel-title'>Variazione investimenti (anno precedente vs attuale)</div>", unsafe_allow_html=True)
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

    # FINANZIAMENTI
    COLOR_PAGATO = "#34d399"
    # Trasformiamo l'esadecimale con opacità in RGBA
    COLOR_RESIDUO = hex_to_rgba("#fa5a8d76") 
    COLOR_RESIDUO_pie = "#fa5a8e"  # versione piena per torta

    # INTERESSI
    COLOR_INT_PAGATI = "#34d399"
    # Trasformiamo l'esadecimale con opacità in RGBA
    COLOR_INT_RESIDUI = hex_to_rgba("#fa5a8d76")

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
                text=df_prog["Residuo"].map(eur0),
                textposition="inside",
                insidetextanchor="middle",
                textfont=dict(
            color="#ffffff",   # ← COLORE ETICHETTE (BIANCO)
            size=13
        )
            )

            fig_prog.update_layout(
                title=dict(text="FINANZIAMENTI", 
                           x=0.5, 
                           xanchor='center', 
                           y=0.95, yanchor='middle'),
                barmode="stack",
                height=300,
                paper_bgcolor=APP_BG,        # ← SFONDO APP
                plot_bgcolor=PANEL_BG,       # ← SFONDO GRAFICO
                font=dict(color=TEXT_COLOR),
                legend=dict(
                    orientation="h",
                    x=0.45,
                    xanchor="center",
                    y=1.45
                ),
                xaxis=dict(tickprefix="€ ", tickformat=",.0f"),
                separators=",."
            )

            fig_prog.update_xaxes(showgrid=False)
            fig_prog.update_yaxes(showgrid=False)

            st.plotly_chart(fig_prog, use_container_width=True)

    with c2:
        fig_pie = go.Figure(go.Pie(
            labels=["Pagato", "Residuo"],
            values=[totale_pagato, totale_residuo],
            hole=0,
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

        fig_pie.update_layout(
            title=dict(text="POSIZIONE DEBITI", 
            x=0.5, xanchor='center',
            y=0.95, yanchor='middle'),
            height=300,                 # altezza pannello invariata
            showlegend=False,
            paper_bgcolor=APP_BG,       # sfondo app
            plot_bgcolor=PANEL_BG,      # sfondo grafico
            font=dict(color=TEXT_COLOR),
            margin=dict(t=10, b=10, l=10, r=10),
            separators=",."
        )

        st.plotly_chart(fig_pie, use_container_width=True)

    c3, c4 = st.columns([1.4, 1], gap="large")

    with c3:
        fig_int = go.Figure()

        fig_int.add_bar(
            y=["Interessi"],
            x=[interessi_pagati],
            orientation="h",
            name="Quota interessi",
            marker_color=COLOR_INT_PAGATI,  # ← COLORE INTERESSI PAGATI
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
            text=[eur0(interessi_residui)],
            textposition="inside",
            insidetextanchor="middle",
            textfont=dict(
                color="#ffffff",   # ← COLORE ETICHETTE (BIANCO)
                size=13
            )
        )

        fig_int.update_layout(
            title=dict(text="INTERESSI PAGATI", 
                       x=0.5, xanchor='center', 
                       y=0.95, yanchor='middle'),
            barmode="stack",
            height=300,
            paper_bgcolor=APP_BG,
            plot_bgcolor=PANEL_BG,
            font=dict(color=TEXT_COLOR),
            legend=dict(
                orientation="h",
                x=0.45,
                xanchor="center",
                y=1.35
            ),
            xaxis=dict(tickprefix="€ ", tickformat=",.0f"),
            separators=",."

        )

        fig_int.update_xaxes(showgrid=False)
        fig_int.update_yaxes(showgrid=False)

        st.plotly_chart(fig_int, use_container_width=True)

    with c4:
        df_tabella = pd.DataFrame(
            dettagli_rows,
            columns=["Nome", "Rata", "Residuo", "% Completato", "Mesi rim."],
        )
        if df_tabella.empty:
            st.caption("Nessun finanziamento da mostrare.")
        else:
            st.dataframe(
                style_finanziamento(df_tabella),
                use_container_width=True,
                hide_index=True
            )

# --- TAB 5: REGISTRO ---
with tab_admin:
    st.subheader("Nuova Transazione")

    c_cat, c_det = st.columns(2)
    categoria_scelta = c_cat.selectbox("Categoria", list(log.STRUTTURA_CATEGORIE.keys()))
    dettagli_filtrati = log.STRUTTURA_CATEGORIE[categoria_scelta]
    dettaglio_scelto = c_det.selectbox("Dettaglio", dettagli_filtrati)

    with st.form("form_inserimento_dati", clear_on_submit=True):
        col_imp, col_data, col_tipo = st.columns(3)
        importo_inserito = col_imp.number_input("Importo (€)", min_value=0.0, step=0.01)
        data_inserita = col_data.date_input("Data", datetime.now())
        tipo_inserito = col_tipo.selectbox("Tipo", ["USCITA", "ENTRATA"])
        note_inserite = st.text_input("Note")

        if st.form_submit_button("REGISTRA MOVIMENTO"):
            db.aggiungi_movimento(data_inserita, tipo_inserito, categoria_scelta, dettaglio_scelto, importo_inserito, note_inserite, user_email=user_email)
            st.success("Movimento salvato!")
            st.rerun()

    st.divider()
    st.subheader("Spese ricorrenti")
    with st.form("form_spese_ricorrenti", clear_on_submit=True):
        c_desc, c_imp = st.columns([2, 1])
        descrizione = c_desc.text_input("Descrizione spesa ricorrente")
        importo = c_imp.number_input("Importo (€)", min_value=0.0, step=0.01)

        c_giorno, c_freq = st.columns(2)
        giorno_scad = c_giorno.number_input("Giorno scadenza", min_value=1, max_value=31, step=1, value=1)
        freq_options = {
            "Mensile": 1,
            "Bimestrale": 2,
            "Trimestrale": 3,
            "Quadrimestrale": 4,
            "Semestrale": 6,
            "Annuale": 12,
        }
        freq_label = c_freq.selectbox("Frequenza", list(freq_options.keys()), index=0)
        freq = freq_options[freq_label]

        c_start, c_end = st.columns(2)
        data_inizio = c_start.date_input("Data inizio", datetime.now())
        senza_fine = c_end.checkbox("Senza data fine", value=False)
        data_fine = None if senza_fine else c_end.date_input("Data fine", datetime.now())

        if st.form_submit_button("AGGIUNGI RICORRENTE"):
            if descrizione and importo > 0:
                db.aggiungi_spesa_ricorrente(descrizione, importo, giorno_scad, freq, data_inizio, data_fine, user_email=user_email)
                st.success("Spesa ricorrente salvata!")
                st.rerun()
            else:
                st.warning("Inserisci descrizione e importo.")

    df_ric_view = db.carica_spese_ricorrenti(user_email)
    if not df_ric_view.empty:
        st.dataframe(style_df_currency(df_ric_view, ["importo"]), use_container_width=True, hide_index=True)
        with st.form("form_delete_ricorrente"):
            spesa_id = st.selectbox("Elimina spesa ricorrente (ID)", df_ric_view["id"].tolist())
            if st.form_submit_button("ELIMINA"):
                db.elimina_spesa_ricorrente(spesa_id, user_email=user_email)
                st.success("Spesa ricorrente eliminata.")
                st.rerun()
    else:
        st.caption("Nessuna spesa ricorrente inserita.")

    st.divider()
    st.subheader("Nuovo Finanziamento")
    with st.form("form_finanziamento", clear_on_submit=True):
        c1, c2 = st.columns(2)
        nome_fin = c1.text_input("Nome finanziamento")
        capitale = c2.number_input("Capitale iniziale",min_value=0.0,step=0.1,format="%.2f")
        c2.caption(f"Valore inserito: **{capitale:.2f} €**")
        c3, c4 = st.columns(2)
        taeg = c3.number_input("TAEG (%)", min_value=0.0, step=0.01)
        durata = c4.number_input("Durata (mesi)", min_value=1, step=1)
        c5, c6 = st.columns(2)
        data_inizio = c5.date_input("Data inizio")
        giorno_scad = c6.number_input("Giorno scadenza", min_value=1, max_value=31, step=1, value=1)
        rate_pagate_input = st.number_input(
            "Rate gia pagate ",
            min_value=0,
            step=1,
            value=0,
            help="Usa questo campo se i movimenti storici non coprono tutte le rate gia saldate.",
        )

        if st.form_submit_button("SALVA FINANZIAMENTO"):
            if nome_fin and capitale > 0 and durata > 0:
                rate_pagate_val = int(rate_pagate_input) if int(rate_pagate_input) > 0 else None
                db.aggiungi_finanziamento(
                    nome_fin,
                    capitale,
                    taeg,
                    durata,
                    data_inizio,
                    giorno_scad,
                    rate_pagate=rate_pagate_val, user_email=user_email
                )
                st.success("Finanziamento salvato!")
                st.rerun()
            else:
                st.warning("Compila nome, capitale e durata.")

    if not df_fin_db.empty:
        df_fin_view = df_fin_db.rename(columns={
            "nome": "Nome",
            "capitale_iniziale": "Capitale",
            "taeg": "TAEG %",
            "durata_mesi": "Durata (mesi)",
            "data_inizio": "Data inizio",
            "giorno_scadenza": "Giorno scadenza",
            "rate_pagate": "Rate pagate (override)",
        })
        if "Rate pagate (override)" in df_fin_view.columns:
            df_fin_view["Rate pagate (override)"] = (
                pd.to_numeric(df_fin_view["Rate pagate (override)"], errors="coerce")
                .fillna(0)
                .astype(int)
            )
        def _fmt_num_it(value, decimals=2):
            try:
                v = float(value)
            except Exception:
                return ""
            s = f"{v:,.{decimals}f}"
            return s.replace(",", "X").replace(".", ",").replace("X", ".")

        sty = df_fin_view.style.format({
            "Capitale": lambda x: _fmt_num_it(x, 2),
            "TAEG %": "{:.2f}%",
        })
        st.dataframe(sty, use_container_width=True, hide_index=True)
        with st.form("form_delete_finanziamento"):
            fin_nome = st.selectbox("Elimina finanziamento (Nome)", df_fin_db["nome"].tolist())
            if st.form_submit_button("ELIMINA FINANZIAMENTO"):
                db.elimina_finanziamento(fin_nome,user_email=user_email)
                st.success("Finanziamento eliminato.")
                st.rerun()

    st.divider()
    st.subheader("Storico Movimenti")
    # Filtri registro
    c_f1, c_f2, c_f3 = st.columns([1, 1, 2])
    mese_reg = c_f1.selectbox("Mese registro", list(MONTH_NAMES.keys()), index=mese_sel - 1, format_func=lambda x: MONTH_NAMES[x])
    anno_reg = c_f2.selectbox("Anno registro", anni_disponibili, index=anni_disponibili.index(anno_sel) if anno_sel in anni_disponibili else 0)
    mostra_tutto = c_f3.checkbox("Mostra tutte le transazioni", value=False)

    df_reg = df_mov.copy()
    if not mostra_tutto:
        df_reg = df_reg[(df_reg["Data"].dt.month == mese_reg) & (df_reg["Data"].dt.year == anno_reg)]

    c_f4, c_f5, c_f6 = st.columns([1, 1, 2])
    tipo_filter = c_f4.multiselect("Tipo", ["USCITA", "ENTRATA"], default=["USCITA", "ENTRATA"])
    categoria_filter = c_f5.multiselect("Categoria", sorted(df_reg["Categoria"].dropna().unique()))
    testo_filter = c_f6.text_input("Cerca in Dettaglio/Note")

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
    st.dataframe(style_df_currency(df_reg, ["Importo"]), use_container_width=True, height=280)

    if not df_reg.empty:
        with st.form("form_delete_movimento"):
            def _label_mov(i):
                r = df_reg[df_reg["Id"] == i].iloc[0]
                data_txt = r["Data"].strftime("%d/%m/%Y %H:%M") if pd.notna(r["Data"]) else ""
                return f"{i} | {data_txt} | {r['Tipo']} | {r['Dettaglio']} | {eur2(r['Importo'])}"

            mov_id = st.selectbox("Elimina movimento (ID)", df_reg["Id"].tolist(), format_func=_label_mov)
            if st.form_submit_button("ELIMINA MOVIMENTO"):
                db.elimina_movimento(mov_id,user_email)
                st.success("Movimento eliminato.")
                st.rerun()
