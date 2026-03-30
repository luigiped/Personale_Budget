import time
import base64
import json
import os
from datetime import date, datetime, timedelta
 
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from html import escape
 
from config_runtime import (
    IS_CLOUD_RUN, IS_DEMO, default_base_url,
    export_runtime_env, load_google_oauth_credentials,
    get_secret, auth_access_mode,
)
 
export_runtime_env()
client_id, client_secret = load_google_oauth_credentials()
APP_BASE_URL = default_base_url()
 
try:
    from streamlit_oauth import OAuth2Component
except Exception:
    OAuth2Component = None
 
import Database as db
import logiche as log
 
# auth_manager: usa solo le funzioni pure (niente st.*)
from auth_manager import (
    create_session, validate_session, delete_session,
    login_email_password, register_user, get_display_name,
    AuthError, AccessDeniedError, SESSION_TOKEN_COOKIE,
)
 
from utils.styles import CSS_ALL
from utils.constants import (
    Colors, MONTH_NAMES, MONTH_SHORT, FREQ_OPTIONS, FREQ_MAP,
    STRUTTURA_CATEGORIE, PLOTLY_CONFIG,
)
from utils.formatters import format_eur, eur0, eur2, hex_to_rgba, badge_html, chip_html
from utils.charts import style_fig, kpi_card_html, KPI_DEFINITIONS
from utils.html_tables import (
    scroll_table, render_calendario_html, render_ricorrenti_rows,
    _td, _tr, _th
)
 
# ---------------------------------------------------------------------------
# Demo config
# ---------------------------------------------------------------------------
DEMO_USER_EMAIL = get_secret("DEMO_USER_EMAIL") if IS_DEMO else None
DEMO_USER_PASSWORD = get_secret("DEMO_USER_PASSWORD") if IS_DEMO else None
DEMO_USER_EMAIL_NORM = str(DEMO_USER_EMAIL or "").strip().lower() if DEMO_USER_EMAIL else None
 
AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
 
# ---------------------------------------------------------------------------
# Configurazione pagina (deve essere prima di qualsiasi st.*)
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Personal Budget Dashboard", layout="wide", page_icon="💰")


# Nasconde la navigazione automatica della cartella pages/ dalla sidebar Streamlit.
# Questa app usa tab interni — la multi-page nav di Streamlit non è desiderata.
st.markdown(
    "<style>[data-testid='stSidebarNav']{display:none!important;}</style>",
    unsafe_allow_html=True,
)
st.markdown(f"<style>{CSS_ALL}</style>", unsafe_allow_html=True)
 
# ---------------------------------------------------------------------------
# Helpers cookie/session (layer Streamlit — responsabilità di questo file)
# ---------------------------------------------------------------------------
 
def _read_cookie(name: str) -> str | None:
    """Legge un cookie dalla request Streamlit (1.30+) o tramite extra_streamlit_components."""
    try:
        cookies = getattr(st.context, "cookies", None)
        if cookies:
            val = cookies.get(name)
            if isinstance(val, (list, tuple)):
                val = val[0] if val else None
            if val:
                return str(val).strip() or None
    except Exception:
        pass
 
    try:
        import extra_streamlit_components as stx
        mgr = stx.CookieManager(key="pb_cookie_manager")
        mgr.get_all(key=f"cookie_get_all_{name}")
        val = mgr.get(name)
        if val:
            return str(val).strip() or None
    except Exception:
        pass
    return None
 
 
def _set_cookie(name: str, value: str, expires_at: datetime | None = None) -> None:
    """Scrive un cookie lato client."""
    is_https = False
    try:
        headers = getattr(st.context, "headers", None) or {}
        is_https = str(headers.get("x-forwarded-proto", "")).lower() == "https"
    except Exception:
        pass
 
    try:
        import extra_streamlit_components as stx
        mgr = stx.CookieManager(key="pb_cookie_manager")
        kwargs: dict = {"key": f"cookie_set_{name}", "same_site": "lax", "path": "/"}
        if expires_at:
            kwargs["expires_at"] = expires_at
        mgr.set(name, value, secure=is_https, **kwargs)
        return
    except Exception:
        pass
 
    # Fallback JS
    max_age = ""
    if expires_at:
        from datetime import timezone

        # ... dentro _set_cookie ...
        if expires_at:
        # Se expires_at è aware, usiamo datetime.now(timezone.utc)
            now = datetime.now(timezone.utc) if expires_at.tzinfo else datetime.now()
            secs = int((expires_at - now).total_seconds())
            if secs > 0:
                max_age = f"max-age={secs};"
        secure = "secure;" if is_https else ""
        st.components.v1.html(
            f"<script>document.cookie='{name}={value};{max_age}SameSite=Lax;path=/;{secure}';</script>",
            height=0,
        )
 
 
def _delete_cookie(name: str) -> None:
    try:
        import extra_streamlit_components as stx
        mgr = stx.CookieManager(key="pb_cookie_manager")
        mgr.delete(name, key=f"cookie_del_{name}")
    except Exception:
        pass
 
 
def _get_session_user() -> str | None:
    """
    Controlla la sessione attiva. Usa la cache in session_state per evitare
    query DB ad ogni rerun (rispetta SESSION_RECHECK_SECONDS).
    """
    token = (
        st.session_state.get("session_token")
        or _read_cookie(SESSION_TOKEN_COOKIE)
    )
    if not token:
        return None
 
    # Cache locale
    from auth_manager import SESSION_RECHECK_SECONDS
    cache_token = st.session_state.get("_auth_cache_token")
    cache_user  = st.session_state.get("_auth_cache_user")
    cache_at    = st.session_state.get("_auth_cache_checked_at")
    if (cache_token == token and cache_user and cache_at
            and (datetime.now().timestamp() - cache_at) < SESSION_RECHECK_SECONDS):
        return cache_user
 
    # Verifica DB
    email = validate_session(token)
    if email:
        st.session_state["session_token"] = token
        st.session_state["auth_user_email"] = email
        st.session_state["_auth_cache_token"] = token
        st.session_state["_auth_cache_user"] = email
        st.session_state["_auth_cache_checked_at"] = datetime.now().timestamp()
    else:
        for k in ["session_token", "auth_user_email", "_auth_cache_token",
                  "_auth_cache_user", "_auth_cache_checked_at"]:
            st.session_state.pop(k, None)
        _delete_cookie(SESSION_TOKEN_COOKIE)
    return email
 
 
def _do_login(email: str) -> bool:
    """Crea sessione e salva token in session_state + cookie."""
    try:
        token, expiry = create_session(email)
    except AuthError as exc:
        st.error(str(exc))
        return False
    st.session_state["session_token"] = token
    st.session_state["auth_user_email"] = email
    _set_cookie(SESSION_TOKEN_COOKIE, token, expires_at=expiry)
    return True
 
 
def _do_logout() -> None:
    token = st.session_state.get("session_token") or _read_cookie(SESSION_TOKEN_COOKIE)
    if token:
        delete_session(token)
    for k in ["session_token", "auth_user_email", "_auth_cache_token",
              "_auth_cache_user", "_auth_cache_checked_at", "is_demo_guest"]:
        st.session_state.pop(k, None)
    _delete_cookie(SESSION_TOKEN_COOKIE)
 
 
# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------
 
def _infer_base_url() -> str | None:
    try:
        headers = st.context.headers
        host = headers.get("x-forwarded-host") or headers.get("host")
        proto = headers.get("x-forwarded-proto") or "https"
        return f"{proto}://{host}".rstrip("/") if host else None
    except Exception:
        return None
 
 
def _redirect_uri() -> str | None:
    if IS_CLOUD_RUN:
        return _infer_base_url() or (APP_BASE_URL.rstrip("/") if APP_BASE_URL else None)
    return (APP_BASE_URL.rstrip("/") if APP_BASE_URL else "http://localhost:8080")
 
 
def _decode_id_token_email(id_token) -> str | None:
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
        raw = base64.urlsafe_b64decode((payload + padding).encode()).decode()
        email = json.loads(raw).get("email")
        return str(email).strip().lower() if email else None
    except Exception:
        return None
 
 
# ---------------------------------------------------------------------------
# Schermata di login
# ---------------------------------------------------------------------------
 
def _render_login_screen() -> None:
    mode = auth_access_mode()
 
    st.markdown("""
<style>
    [data-testid="stSidebarNav"] { padding-top: 1rem !important; }
    .stSidebar [data-testid="stVerticalBlock"] { gap: 0.5rem !important; }

    /* Omogeneità Selectbox Registro (Grigio come richiesto) */
    div[data-baseweb="select"] > div {
        background-color: #1e293b !important; /* Grigio scuro coerente */
        border: 1px solid #334155 !important;
    }
</style>
""", unsafe_allow_html=True)
 
    _, center, _ = st.columns([1, 1.4, 1])
    with center:
        st.markdown("<h1 class='login-title'>💰 Personal Budget</h1>", unsafe_allow_html=True)
        st.markdown("<p class='login-subtitle'>Accedi per esplorare la dashboard</p>", unsafe_allow_html=True)
 
        if mode == "closed":
            st.warning("Accesso disabilitato. Riprova quando il servizio sarà riattivato.")
            return
 
        if IS_DEMO:
            user_flows_disabled = (mode == "demo_only")
            tab_login, tab_register, tab_demo = st.tabs(["🔑 Accedi", "📝 Registrati", "🚀 Demo"])
 
            with tab_login:
                if user_flows_disabled:
                    st.info("Login utenti temporaneamente disattivato. Usa la tab Demo.")
                email_in = st.text_input("Email", key="login_email", disabled=user_flows_disabled)
                pwd_in   = st.text_input("Password", type="password", key="login_pwd", disabled=user_flows_disabled)
                if st.button("Accedi", use_container_width=True, key="btn_login", disabled=user_flows_disabled):
                    if email_in and pwd_in:
                        try:
                            email_norm, token, expiry = login_email_password(email_in, pwd_in)
                            st.session_state["session_token"] = token
                            st.session_state["auth_user_email"] = email_norm
                            _set_cookie(SESSION_TOKEN_COOKIE, token, expires_at=expiry)
                            st.success("Accesso effettuato!")
                            st.rerun()
                        except AuthError as exc:
                            st.error(str(exc))
                    else:
                        st.warning("Inserisci email e password.")
 
            with tab_register:
                if user_flows_disabled:
                    st.info("Registrazione temporaneamente disattivata. Usa la tab Demo.")
                nome_reg  = st.text_input("Nome",              key="reg_nome",  disabled=user_flows_disabled)
                email_reg = st.text_input("Email",             key="reg_email", disabled=user_flows_disabled)
                pwd_reg   = st.text_input("Password",          type="password", key="reg_pwd",  disabled=user_flows_disabled)
                pwd_reg2  = st.text_input("Conferma password", type="password", key="reg_pwd2", disabled=user_flows_disabled)
                if st.button("Registrati", use_container_width=True, key="btn_register", disabled=user_flows_disabled):
                    if not email_reg or not pwd_reg:
                        st.warning("Compila email e password.")
                    elif pwd_reg != pwd_reg2:
                        st.error("Le password non coincidono.")
                    else:
                        try:
                            register_user(email_reg, pwd_reg, nome_reg)
                            st.success("Registrazione completata! Ora accedi dalla tab 'Accedi'.")
                        except AuthError as exc:
                            st.error(str(exc))
 
            with tab_demo:
                st.markdown(
                    "<p style='color:rgba(230,238,249,0.7);font-size:0.9rem;'>"
                    "Esplora tutte le funzionalità con dati di esempio.</p>",
                    unsafe_allow_html=True,
                )
                if st.button("▶ Entra in modalità Demo", use_container_width=True, key="btn_demo"):
                    if DEMO_USER_EMAIL:
                        if _do_login(DEMO_USER_EMAIL):
                            st.session_state["is_demo_guest"] = True
                            st.rerun()
                    else:
                        st.error("Credenziali demo non configurate nei secrets.")
        else:
            # Produzione: solo Google OAuth
            if OAuth2Component is None:
                st.error("Modulo mancante: installa `streamlit-oauth`.")
                st.stop()
            if not client_id or not client_secret:
                st.error("Credenziali OAuth mancanti.")
                st.stop()
 
            login_clicked = st.button("Accedi con Google", key="google_login_custom", use_container_width=True)
            oauth2 = OAuth2Component(client_id, client_secret, AUTHORIZE_URL, TOKEN_URL, TOKEN_URL, "")
            if login_clicked:
                st.session_state["oauth_auto_click"] = True
                st.rerun()
 
            auto_click = bool(st.session_state.pop("oauth_auto_click", False))
            redirect_uri = _redirect_uri()
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
                    acc = result.get("access_token") or (result.get("token") or {}).get("access_token")
                    if acc:
                        from urllib.request import Request, urlopen
                        try:
                            req = Request(
                                "https://openidconnect.googleapis.com/v1/userinfo",
                                headers={"Authorization": f"Bearer {acc}"},
                            )
                            with urlopen(req, timeout=15) as resp:
                                payload = json.loads(resp.read())
                                email_google = str(payload.get("email", "")).strip().lower() or None
                        except Exception:
                            pass
                if email_google and _do_login(email_google):
                    try:
                        st.query_params.clear()
                    except Exception:
                        pass
                    st.success("Accesso autorizzato.")
                    st.rerun()
                if not email_google:
                    st.error("Impossibile leggere l'email dal profilo Google.")
 
    st.stop()
 
 
# ---------------------------------------------------------------------------
# Bootstrap DB
# ---------------------------------------------------------------------------
 
@st.cache_resource
def _ensure_db_ready():
    db.inizializza_db()
    return True
 
 
_ensure_db_ready()
try:
    db.pulisci_sessioni_scadute()
except Exception:
    pass
 
# ---------------------------------------------------------------------------
# Auth check
# ---------------------------------------------------------------------------
 
AUTH_USER_EMAIL = _get_session_user()
if not AUTH_USER_EMAIL:
    _render_login_screen()
 
user_email = AUTH_USER_EMAIL
 
# Banner demo
is_demo_account = False
if IS_DEMO and DEMO_USER_EMAIL_NORM:
    is_demo_account = str(AUTH_USER_EMAIL).strip().lower() == DEMO_USER_EMAIL_NORM
    st.session_state["is_demo_guest"] = is_demo_account
    if is_demo_account:
        st.info("👁️ **Modalità Demo** — Stai esplorando l'app con dati di esempio.", icon="ℹ️")
 
NOME_DISPLAY = get_display_name(AUTH_USER_EMAIL, is_demo_account=is_demo_account)
 
# ---------------------------------------------------------------------------
# Caricamento dati
# ---------------------------------------------------------------------------
 
df_mov = db.carica_dati(user_email)
df_mov.columns = [c.capitalize() for c in df_mov.columns]
if "Data" in df_mov:
    df_mov["Data"] = pd.to_datetime(df_mov["Data"], errors="coerce")
else:
    df_mov["Data"] = pd.Series(pd.NaT, index=df_mov.index, dtype="datetime64[ns]")
if "Tipo" in df_mov:
    df_mov["Tipo"] = df_mov["Tipo"].astype(str).str.upper().str.strip().replace(
        {"ENTRATE": "ENTRATA", "USCITE": "USCITA"}
    )
if "Categoria" in df_mov:
    df_mov["Categoria"] = df_mov["Categoria"].astype(str).str.upper().str.strip()
 
if df_mov.empty:
    st.warning("Nessun movimento trovato. Usa il tab Registro per aggiungere movimenti.")
 
df_fin_db = db.carica_finanziamenti(user_email)
 
# ---------------------------------------------------------------------------
# Helpers settings (asset_settings)
# ---------------------------------------------------------------------------
 
def _load_settings_df() -> pd.DataFrame:
    try:
        with db.connetti_db() as conn:
            df = pd.read_sql(
                "SELECT chiave, valore_numerico, valore_testo "
                "FROM asset_settings WHERE user_email = %s",
                conn,
                params=(user_email,),
            )
        if df.empty:
            return pd.DataFrame(columns=["valore_numerico", "valore_testo"]).set_index(pd.Index([]))
        df = df.drop_duplicates(subset=["chiave"], keep="last")
        return df.set_index("chiave")
    except Exception:
        return pd.DataFrame(columns=["valore_numerico", "valore_testo"]).set_index(pd.Index([]))
 
 
def _save_settings_batch(num_payload: dict = None, txt_payload: dict = None) -> tuple[bool, str]:
    num_payload = num_payload or {}
    txt_payload = txt_payload or {}
    if not user_email:
        return False, "Utente non autenticato."
    try:
        with db.connetti_db() as conn:
            with conn.cursor() as cur:
                upsert_q = (
                    "INSERT INTO asset_settings (chiave, user_email, valore_numerico, valore_testo) "
                    "VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (chiave, user_email) DO UPDATE SET "
                    "valore_numerico = EXCLUDED.valore_numerico, "
                    "valore_testo = EXCLUDED.valore_testo"
                )
                for key, value in num_payload.items():
                    cur.execute(upsert_q, (str(key), user_email, float(value) if value is not None else None, None))
                for key, value in txt_payload.items():
                    cur.execute(upsert_q, (str(key), user_email, None, str(value) if value is not None else ""))
        return True, ""
    except Exception as exc:
        return False, str(exc)
 
 
settings = _load_settings_df()
anno_default = datetime.now().year
anno_prev_default = anno_default - 1
 
# Valori di default (solo se mancanti)
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
defaults_txt = {"pac_ticker": "VNGA80"}
updated = False
for k, v in defaults_num.items():
    if k not in settings.index or pd.isna(settings.loc[k, "valore_numerico"]):
        db.imposta_parametro(k, valore_num=v, user_email=user_email)
        updated = True
for k, v in defaults_txt.items():
    if k not in settings.index or pd.isna(settings.loc[k, "valore_testo"]):
        db.imposta_parametro(k, valore_txt=v, user_email=user_email)
        updated = True
if updated:
    settings = _load_settings_df()
 
 
def s_num(key: str, default: float = 0.0) -> float:
    try:
        val = settings.loc[key, "valore_numerico"]
        return float(val) if pd.notna(val) else default
    except Exception:
        return default
 
 
def s_txt(key: str, default: str = "") -> str:
    try:
        val = settings.loc[key, "valore_testo"]
        return str(val) if pd.notna(val) else default
    except Exception:
        return default
 
 
def s_num_candidates(keys: list[str], default: float = 0.0) -> float:
    for key in keys:
        try:
            val = settings.loc[key, "valore_numerico"]
            if pd.notna(val):
                return float(val)
        except Exception:
            continue
    return default
 
 
# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
 
# Avatar: iniziali utente + email + logout — stile moderno
_initials = "".join(w[0].upper() for w in (NOME_DISPLAY or "U").split()[:2]) or "U"
st.sidebar.markdown(f"""
<div style="display:flex;align-items:center;gap:12px;padding:12px 12px 10px;
    background:#0c1120;border:1px solid rgba(112,143,215,0.28);
    border-radius:14px;margin-bottom:4px;margin-top:-6px;">
  <div style="width:46px;height:46px;border-radius:50%;flex-shrink:0;
    background:linear-gradient(135deg,#9b74f5 0%,#f472b6 100%);
    display:flex;align-items:center;justify-content:center;
    font-size:1.1rem;font-weight:800;color:#fff;
    box-shadow:0 0 16px rgba(155,116,245,0.35);">{_initials}</div>
  <div style="min-width:0;overflow:hidden;">
    <div style="font-size:0.88rem;font-weight:700;color:#ffffff;
      white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{NOME_DISPLAY}</div>
    <div style="font-size:0.72rem;color:#60a5fa;margin-top:1px;
      white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{AUTH_USER_EMAIL}</div>
  </div>
</div>
""", unsafe_allow_html=True)

if st.sidebar.button("⎋  Logout", use_container_width=True):
    _do_logout()
    st.rerun()

st.sidebar.title("Parametri")
 
if not df_mov.empty:
    anni_disponibili = sorted(df_mov["Data"].dt.year.dropna().astype(int).unique().tolist())
else:
    anni_disponibili = [datetime.now().year]
 
def_anno = anni_disponibili.index(datetime.now().year) if datetime.now().year in anni_disponibili else len(anni_disponibili) - 1
anno_sel = st.sidebar.selectbox("Anno di analisi", anni_disponibili, index=def_anno)
mese_sel = st.sidebar.slider("Mese", 1, 12, datetime.now().month)
 
# Impostazioni rapide sidebar
prev_year = anno_sel - 1
risp_prev_key       = f"risparmio_precedente_{prev_year}"
saldo_iniziale_key  = f"saldo_iniziale_{anno_sel}"
risp_prev_candidates  = [risp_prev_key, f"risparmio_precedente_{anno_sel}"]
saldo_iniziale_candidates = [saldo_iniziale_key, f"saldo iniziale_{anno_sel}"]
 
if "quick_settings_saved_msg" in st.session_state:
    st.sidebar.success(st.session_state.pop("quick_settings_saved_msg"))
if "quick_settings_saved_err" in st.session_state:
    st.sidebar.error(st.session_state.pop("quick_settings_saved_err"))
 
last_saved = s_txt("quick_settings_last_saved_at", "")
if last_saved:
    st.sidebar.caption(f"Ultimo salvataggio: {last_saved}")
 
with st.sidebar.expander("Impostazioni rapide", expanded=False):
    with st.form("quick_settings_form", clear_on_submit=False):
        target_perc         = st.number_input(f"Incremento risparmio % (vs {prev_year})", 0.0, 100.0, s_num("obiettivo_risparmio_perc", 30.0), 1.0)
        risp_prev           = st.number_input(f"Risparmio anno prec. ({prev_year}) €", 0.0, value=s_num_candidates(risp_prev_candidates, 0.0), step=100.0)
        saldo_iniziale_set  = st.number_input(f"Saldo iniziale {anno_sel} (€)", 0.0, value=s_num_candidates(saldo_iniziale_candidates, 0.0), step=100.0)
        budget_base_set     = st.number_input("Budget mensile base (€)", 0.0, value=s_num("budget_mensile_base", 0.0), step=50.0)
        saldo_fineco_set    = st.number_input("Saldo Fineco (€)", 0.0, value=s_num("saldo_fineco", 25995.0), step=50.0)
        saldo_revolut_set   = st.number_input("Saldo Revolut (€)", 0.0, value=s_num("saldo_revolut", 2400.0), step=50.0)
        pac_quote_set       = st.number_input("Quote PAC", 0, value=int(s_num("pac_quote", 0)), step=1)
        pac_capitale_base_set = st.number_input("Capitale PAC investito (€)", 0.0, value=s_num("pac_capitale_investito", 0.0), step=10.0)
        pac_vers_set        = st.number_input("Versamento mensile PAC (€)", 0.0, value=s_num("pac_versamento_mensile", 80.0), step=10.0)
        pac_ticker_set      = st.text_input("Ticker ETF PAC", value=s_txt("pac_ticker", "VNGA80"))
        pac_rend_set        = st.number_input("Rendimento PAC stimato (%)", 0.0, value=s_num("pac_rendimento_stimato", 7.0), step=0.5)
        fondo_quote_set     = st.number_input("Quote Fondo Pensione", 0.0, value=s_num("fondo_quote", 0.0), step=1.0)
        fondo_capitale_base_set = st.number_input("Capitale Fondo investito (€)", 0.0, value=s_num("fondo_capitale_investito", 0.0), step=10.0)
        fondo_vers_set      = st.number_input("Versamento mensile Fondo (€)", 0.0, value=s_num("fondo_versamento_mensile", 50.0), step=10.0)
        fondo_quota_set     = st.number_input("Valore quota Fondo", 0.0, value=s_num("fondo_valore_quota", 7.28), step=0.01, format="%.4f")
        aliq_irpef_set      = st.number_input("Aliquota IRPEF (0-1)", 0.0, 1.0, s_num("aliquota_irpef", 0.26), 0.01, format="%.2f")
        fondo_rend_set      = st.number_input("Rendimento Fondo stimato (%)", 0.0, value=s_num("fondo_rendimento_stimato", 5.0), step=0.5)
        fondo_tfr_set       = st.number_input("TFR versato anno (€)", 0.0, value=s_num("fondo_tfr_versato_anno", 0.0), step=100.0)
        fondo_snapshot_set  = st.text_input("Data snapshot Fondo (YYYY-MM-DD)", value=s_txt("fondo_data_snapshot", str(date.today())))
 
        if st.form_submit_button("💾 Salva impostazioni", use_container_width=True):
            num_payload = {
                "obiettivo_risparmio_perc": float(target_perc),
                f"risparmio_precedente_{prev_year}": float(risp_prev),
                f"saldo_iniziale_{anno_sel}": float(saldo_iniziale_set),
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
            txt_payload = {
                "pac_ticker": str(pac_ticker_set).strip(),
                "fondo_data_snapshot": str(fondo_snapshot_set),
            }
            ok, err = _save_settings_batch(num_payload, txt_payload)
            if not ok:
                st.session_state["quick_settings_saved_err"] = f"Salvataggio fallito: {err}"
                st.rerun()
            ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            _save_settings_batch({}, {"quick_settings_last_saved_at": ts})
            st.session_state["quick_settings_saved_msg"] = f"Impostazioni salvate alle {ts}."
            settings = _load_settings_df()
            st.rerun()
 
# Parametri correnti (prima e dopo il form, usa sempre i valori del DB ricaricato)
target_perc_corrente       = float(target_perc)
risp_prev_corrente         = float(risp_prev)
budget_base_corrente       = float(budget_base_set)
pac_quote_corrente         = int(pac_quote_set)
pac_capitale_base_corrente = float(pac_capitale_base_set)
pac_vers_corrente          = float(pac_vers_set)
pac_rend_corrente          = float(pac_rend_set)
pac_ticker_corrente        = str(pac_ticker_set).strip()
fondo_quote_corrente       = float(fondo_quote_set)
fondo_capitale_base_corrente = float(fondo_capitale_base_set)
fondo_vers_corrente        = float(fondo_vers_set)
fondo_valore_quota_corrente = float(fondo_quota_set)
fondo_rend_corrente        = float(fondo_rend_set)
aliquota_irpef_corrente    = float(aliq_irpef_set)
budget_base                = budget_base_corrente
 
# Pannello residuo mese in sidebar
df_budget = log.budget_spese_annuale(df_mov, anno_sel, budget_base)
st.sidebar.markdown("<div class='side-title'>Residuo mese</div>", unsafe_allow_html=True)
st.sidebar.markdown(f"<div class='side-chip'>{MONTH_SHORT.get(mese_sel, mese_sel)}</div>", unsafe_allow_html=True)
if not df_budget.empty:
    mese_short = MONTH_SHORT.get(mese_sel, str(mese_sel))
    df_res = df_budget[df_budget["Mese"] == mese_short][["Categoria", "Speso", "Residuo"]]
    if not df_res.empty:
        residuo_tot = df_res["Residuo"].sum()
        cls   = "side-residuo neg" if residuo_tot < 0 else "side-residuo"
        arrow = "↓" if residuo_tot < 0 else "↑"
        st.sidebar.markdown(
            f"<div class='{cls}'><span class='label'>Residuo</span>"
            f"<span class='pill'>{arrow} {eur2(residuo_tot, signed=True)}</span></div>",
            unsafe_allow_html=True,
        )
else:
    st.sidebar.caption("Nessun dato budget disponibile.")
 
# ---------------------------------------------------------------------------
# Header principale
# ---------------------------------------------------------------------------
 
st.markdown(
    f"<div style='font-family:\"Plus Jakarta Sans\",sans-serif;font-size:0.95rem;"
    f"font-weight:700;letter-spacing:2px;text-transform:uppercase;"
    f"color:{Colors.TEXT_MID};margin-bottom:10px;'>"
    f"{NOME_DISPLAY} — {MONTH_NAMES.get(mese_sel, mese_sel)} {anno_sel}</div>",
    unsafe_allow_html=True,
)
 
# KPI cards superiori
saldo_iniziale    = s_num_candidates([f"saldo_iniziale_{anno_sel}", f"saldo iniziale_{anno_sel}"], 0.0)
saldo_disponibile = log.saldo_disponibile_da_inizio(df_mov, anno_sel, mese_sel, saldo_iniziale)
kpi               = log.calcola_kpi_dashboard(df_mov, mese_sel, anno_sel)
 
# KPI cards pill-style — font grande, bordi arrotondati, glow colorato
_kpi_data = [
    ("Saldo Disponibile", eur2(saldo_disponibile), Colors.GREEN_BRIGHT, "rgba(92,228,136,0.20)",  "linear-gradient(90deg,#5ce48880,transparent)"),
    ("Uscite Mese",       eur2(kpi["uscite_mese"]),    Colors.RED_BRIGHT,   "rgba(250,89,142,0.20)",  "linear-gradient(90deg,#fa598e80,transparent)"),
    ("Risparmio Mese",    eur2(kpi["risparmio_mese"]), Colors.GREEN_BRIGHT, "rgba(92,228,136,0.20)",  "linear-gradient(90deg,#5ce48880,transparent)"),
    ("Tasso Risparmio",   f"{kpi['tasso_risparmio']}%", Colors.VIOLET,  "rgba(155,127,232,0.20)", "linear-gradient(90deg,#9b7fe880,transparent)"),
]
_kpi_cols = st.columns(4)
for _col, (_lbl, _val, _col_hex, _glow, _grad) in zip(_kpi_cols, _kpi_data):
    _col.markdown(
        f"""<div style="background:#0c1120;border:1px solid rgba(92,118,178,0.22);
        border-radius:16px;padding:22px 18px 18px;text-align:center;
        box-shadow:0 4px 28px rgba(0,0,0,0.45),0 0 32px {_glow};position:relative;overflow:hidden;">
  <div style="font-size:0.85rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;
    color:rgba(180,200,240,0.55);margin-bottom:10px;font-family:'Plus Jakarta Sans',sans-serif;">{_lbl}</div>
  <div style="font-family:'JetBrains Mono',monospace;font-size:1.70rem;font-weight:700;
    color:{_col_hex};text-shadow:0 0 20px {_glow};line-height:1.1;">{_val}</div>
  <div style="position:absolute;bottom:0;left:0;right:0;height:3px;
    background:{_grad};"></div>
</div>""",
        unsafe_allow_html=True,
    )
 
st.divider()

# CSS selectbox: grigio uniforme per tutti i selectbox del Registro — coerenza visiva
st.markdown("""<style>
[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stForm"] div[data-testid="stSelectbox"] [data-baseweb="select"] > div {
    background-color: #1e293b !important;
    border: 1px solid #334155 !important;
    color: #dde6f5 !important;
    border-radius: 8px !important;
}
[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stSelectbox"] [data-baseweb="select"] > div:hover,
[data-testid="stForm"] div[data-testid="stSelectbox"] [data-baseweb="select"] > div:hover {
    border-color: #4a5568 !important;
    background-color: #253348 !important;
}
[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stSelectbox"] label,
[data-testid="stForm"] div[data-testid="stSelectbox"] label {
    color: rgba(180,200,240,0.70) !important;
    font-size: 0.75rem !important;
    font-weight: 600 !important;
}
[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stSelectbox"] svg,
[data-testid="stForm"] div[data-testid="stSelectbox"] svg {
    fill: #94a3b8 !important;
}
/* Nasconde il testo "Press Enter to submit form" nei number_input dentro i form */
[data-testid="InputInstructions"] {
    display: none !important;
}
/* Uniforma il bordo rosso dei number_input quando in focus dentro form */
[data-testid="stForm"] input:focus,
[data-testid="stVerticalBlockBorderWrapper"] input:focus {
    border-color: rgba(79,142,240,0.5) !important;
    outline: none !important;
    box-shadow: 0 0 0 1px rgba(79,142,240,0.3) !important;
}
/* Rimuove il bordo rosso da number_input dentro form */
[data-testid="stForm"] [data-baseweb="input"] > div,
[data-testid="stVerticalBlockBorderWrapper"] [data-baseweb="input"] > div {
    border-color: #334155 !important;
}
[data-testid="stForm"] [data-baseweb="input"] > div:focus-within,
[data-testid="stVerticalBlockBorderWrapper"] [data-baseweb="input"] > div:focus-within {
    border-color: rgba(79,142,240,0.5) !important;
}
</style>""", unsafe_allow_html=True)

# Dati filtrati per mese/anno
mask_mese = (df_mov["Data"].dt.month == mese_sel) & (df_mov["Data"].dt.year == anno_sel)
df_mese   = df_mov[mask_mese].copy()
df_anno   = df_mov[df_mov["Data"].dt.year == anno_sel].copy()
 
# ---------------------------------------------------------------------------
# Helper grafico — da usare in tutti i tab
# ---------------------------------------------------------------------------
 
def show_chart(fig: go.Figure, height: int = 300, show_legend: bool = True) -> None:
    fig.update_traces(textfont=dict(size=12))
    st.plotly_chart(
        style_fig(fig, height=height, show_legend=show_legend),
        use_container_width=True,
        config=PLOTLY_CONFIG,
    )
 
 
# ---------------------------------------------------------------------------
# Helper calendario scadenze (usato in HOME e altrove)
# ---------------------------------------------------------------------------
 
def _get_calendario_cached() -> dict:
    """Cache locale del calcolo scadenze per evitare ricalcoli per ogni rerun."""
    if "_cal_cache" not in st.session_state:
        st.session_state["_cal_cache"] = {}
    return st.session_state["_cal_cache"]
 
 
def _calcolo_scadenze_mese(mese_ref: int, anno_ref: int):
    key = f"{anno_ref}-{mese_ref}"
    cache = _get_calendario_cached()
    if key not in cache:
        df_ric = db.carica_spese_ricorrenti(user_email)
        if not df_ric.empty:
            df_ric = df_ric.rename(columns={
                "descrizione": "Descrizione", "importo": "Importo",
                "giorno_scadenza": "Giorno Scadenza", "frequenza_mesi": "Frequenza",
                "data_inizio": "Data Inizio", "data_fine": "Data Fine",
            })
        df_fin_cal = df_fin_db.rename(columns={
            "nome": "Nome Finanziamento", "capitale_iniziale": "Capitale",
            "taeg": "TAEG", "durata_mesi": "Durata",
            "data_inizio": "Data Inizio", "giorno_scadenza": "Giorno Scadenza",
            "rate_pagate": "Rate Pagate",
        }) if not df_fin_db.empty else pd.DataFrame()
        cache[key] = log.calcolo_spese_ricorrenti(df_ric, df_fin_cal, df_mov, mese_ref, anno_ref)
    return cache[key]
 
 
# ---------------------------------------------------------------------------
# Tab layout
# ---------------------------------------------------------------------------
 
tab_home, tab_charts, tab_assets, tab_debts, tab_admin = st.tabs([
    "🏠 HOME", "📈 ANALISI", "💰 PATRIMONIO", "🔗 DEBITI", "📝 REGISTRO"
])
 
# ============================================================
# TAB 1 — HOME
# ============================================================
with tab_home:
    st.markdown("<div class='section-title'>HOME</div>", unsafe_allow_html=True)
    mesi_labels = list(MONTH_SHORT.values())
 
    c1, c2 = st.columns([1.35, 1.2])
 
    with c1:
        st.markdown("<div class='panel-title'>📊 Budget di spesa (50/30/20)</div>", unsafe_allow_html=True)
        if not df_budget.empty:
            from utils.constants import PERCENTUALI_BUDGET
            # Ordine categorie e mesi (Gen in alto = reverso per Plotly Y bottom-up)
            cat_order   = list(PERCENTUALI_BUDGET.keys())
            # Plotly asse Y categorico: categoryarray[0] = bottom → passiamo Dic→Gen così Gen arriva in cima
            _y_order    = list(reversed(mesi_labels))   # ["Dic","Nov",...,"Gen"]
            fig_budget  = go.Figure()

            for cat in cat_order:
                df_cat   = df_budget[df_budget["Categoria"] == cat].set_index("Mese").reindex(mesi_labels)
                budget_c = df_cat["BudgetCategoria"].fillna(budget_base * PERCENTUALI_BUDGET[cat])
                speso    = df_cat["Speso"].fillna(0)
                residuo  = (budget_c - speso).clip(lower=0)
                spesa_ok = speso.where(speso <= budget_c, budget_c)
                extra    = (speso - budget_c).clip(lower=0)
                col_bright, col_dark = Colors.BUDGET_COLORS[cat]

                # Segmento residuo
                fig_budget.add_bar(
                    x=list(residuo), y=mesi_labels, orientation="h", width=0.70,
                    name=f"{cat}", marker_color=col_bright,
                    marker_cornerradius=4, showlegend=True,
                    text=[f"{eur0(v)}" if v >= 1 else "" for v in residuo],
                    textposition="inside", insidetextanchor="middle",
                    textfont=dict(color="#0B1020", size=13, weight="bold",family="'Plus Jakarta Sans',sans-serif"),
                    hovertemplate=f"<b>{cat} residuo</b>: €%{{x:.0f}}<extra></extra>",
                )
                # Segmento spesa (colore pieno, etichetta bianca)
                fig_budget.add_bar(
                    x=list(spesa_ok), y=mesi_labels, orientation="h", width=0.70,
                    name=cat, marker_color=col_dark,
                    marker_cornerradius=4, showlegend=False,
                    text=[f"€ {int(v):,}".replace(",", ".") if v >= 1 else "" for v in spesa_ok],
                    textposition="inside", insidetextanchor="middle",
                    textfont=dict(color="#ffffff", size=18, weight="bold",family="'Plus Jakarta Sans',sans-serif"),
                    hovertemplate=f"<b>{cat} speso</b>: €%{{x:,.0f}}<extra></extra>",
                )
                
                # Segmento extra sforamento (rosso, con etichetta e triangolino ⚠)
                if extra.sum() > 0:
                    fig_budget.add_bar(
                        x=list(extra), y=mesi_labels, orientation="h", width=0.70,
                        name=f"{cat} extra", marker_color=Colors.RED,
                        marker_cornerradius=4, showlegend=False,
                        text=[f"⚠ {eur0(v)}" if v >= 1 else "" for v in extra],
                        textposition="inside", insidetextanchor="middle",
                        textfont=dict(color="#0B1020", size=16, weight="bold",family="'Plus Jakarta Sans',sans-serif"),
                        hovertemplate=f"<b>{cat} sforato</b>: €%{{x:,.0f}}<extra></extra>",
                    )
            fig_budget.update_traces(textfont_size=16)
            fig_budget.update_layout(
                barmode="stack",
                yaxis=dict(
                    categoryorder="array",
                    categoryarray=_y_order,  # Dic in fondo → Gen in cima
                    tickfont=dict(color=Colors.TEXT, size=12),
                ),
                xaxis=dict(tickprefix="€ ", tickformat=".0f"),
                margin=dict(l=10, r=10, t=40, b=10),
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0,
                    font=dict(size=12, color=Colors.TEXT),
                    bgcolor="rgba(0,0,0,0)",
                ),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="'Plus Jakarta Sans',sans-serif", color=Colors.TEXT),
                height=420,
                showlegend=True,
            )
            fig_budget.update_xaxes(
                showgrid=True, gridcolor="rgba(79,142,240,0.08)",
                zeroline=False, tickfont=dict(size=12, color=Colors.TEXT),
            )
            st.plotly_chart(fig_budget, use_container_width=True, config=PLOTLY_CONFIG)
        else:
            st.info("Imposta 'budget_mensile_base' nelle impostazioni rapide.")
 
    with c2:
        st.markdown("<div class='panel-title'>📂 Dettaglio spese per categoria</div>", unsafe_allow_html=True)
        df_uscite_mese = df_mese[df_mese["Tipo"] == "USCITA"].copy()
        det = log.dettaglio_spese(df_uscite_mese)
        if not det.empty:
            det["Etichetta"] = det["Importo"].map(eur0)
            fig_det = px.bar(det, x="Dettaglio", y="Importo", color="Dettaglio",
                text="Etichetta", color_discrete_sequence=Colors.SEQ)
            fig_det.update_layout(showlegend=False)
            fig_det.update_xaxes(tickangle=-35)
            fig_det.update_traces(texttemplate="<b>%{text}</b>", textposition="auto",
                textfont=dict(size=16, color="#ffffff"), marker_cornerradius=6)
            fig_det.update_yaxes(tickprefix="€ ", tickformat=",.0f")
            show_chart(fig_det, height=420, show_legend=False)
        else:
            st.info("Nessuna spesa nel mese selezionato.")
 
    st.markdown("<div class='panel-title'>📅 Calendario spese ricorrenti</div>", unsafe_allow_html=True)
    cal = _calcolo_scadenze_mese(mese_sel, anno_sel)
    if cal is not None and not cal.empty:
        nascondi_pagate = st.checkbox("Nascondi movimenti pagati", value=False, key=f"hide_paid_{anno_sel}_{mese_sel}")
        cal_view = cal.copy()
        if nascondi_pagate:
            cal_view = cal_view[~cal_view["Stato"].astype(str).str.contains("PAGATO", case=False, na=False)]
 
        tabella_ric = cal_view.copy()
        if "Giorno Previsto" not in tabella_ric.columns:
            tabella_ric["Giorno Previsto"] = pd.to_datetime(tabella_ric["Data"], errors="coerce").dt.day
        tabella_ric["Giorno Previsto"] = pd.to_numeric(tabella_ric["Giorno Previsto"], errors="coerce").fillna(0).astype(int)
        if "Data Fine Prevista" not in tabella_ric.columns:
            tabella_ric["Data Fine Prevista"] = None
        tabella_ric["Data Fine Prevista"] = pd.to_datetime(tabella_ric["Data Fine Prevista"], errors="coerce").dt.strftime("%d/%m/%Y").fillna("Nessuna")
        if "Frequenza" not in tabella_ric.columns:
            tabella_ric["Frequenza"] = "Mensile"
        tabella_ric = tabella_ric[["Spesa", "Importo", "Giorno Previsto", "Data Fine Prevista", "Stato", "Frequenza"]].rename(columns={"Spesa": "Spesa Prevista"})
 
        st.markdown(render_calendario_html(tabella_ric), unsafe_allow_html=True)
 
        # Alert scadenze vicine
        oggi = date.today()
        window = [oggi + timedelta(days=i) for i in range(3)]
        coppie = sorted({(d.year, d.month) for d in window})
        frames_a = [_calcolo_scadenze_mese(m, y) for y, m in coppie]
        frames_a = [f for f in frames_a if f is not None and not f.empty]
        if frames_a:
            base_alert = pd.concat(frames_a, ignore_index=True)
            alert_df = log.alert_scadenze_ricorrenti(base_alert, giorni_preavviso=2, oggi=oggi)
            alert_df = alert_df[alert_df["Giorni Alla Scadenza"] == 2]
            if not alert_df.empty:
                st.warning(f"Hai {len(alert_df)} spese ricorrenti in scadenza.")
    else:
        st.info("Nessuna scadenza prevista per questo mese.")
 
 
# ============================================================
# TAB 2 — ANALISI
# ============================================================
with tab_charts:
    st.markdown("<div class='section-title'>ANALISI</div>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1], gap="large")
 
    with c1:
        st.markdown("<div class='panel-title'>🎯 Obiettivo risparmio</div>", unsafe_allow_html=True)
        entrate_annue = df_anno[df_anno["Tipo"] == "ENTRATA"]["Importo"].sum()
        uscite_annue  = df_anno[df_anno["Tipo"] == "USCITA"]["Importo"].abs().sum()
        risp_corrente = entrate_annue - uscite_annue
        target_curr   = risp_prev_corrente * (1 + target_perc_corrente / 100) if risp_prev_corrente > 0 else 0
 
        if risp_prev_corrente > 0:
            accumulo  = max(risp_corrente, 0)
            mancante  = max(target_curr - accumulo, 0)

            _target_sign = "+" if target_perc_corrente >= 0 else ""
            _badge_label = f"Target {_target_sign}{target_perc_corrente:.0f}%"

            fig_obj = go.Figure()
            fig_obj.add_bar(x=[risp_prev_corrente], y=[1], orientation="h", width=0.46,
                name=str(prev_year), marker_color=Colors.GREEN, marker_cornerradius=6,
                text=[eur0(risp_prev_corrente)], texttemplate="<b>%{text}</b>",
                textposition="inside", insidetextanchor="middle", textfont=dict(color="#07090f", size=13))
            if mancante > 0:
                fig_obj.add_bar(x=[mancante], y=[0], orientation="h", width=0.46,
                    base=[accumulo],
                    name="Mancante al target", marker_color="rgba(109,32,64,0.85)",
                    marker_cornerradius=6,
                    text=[eur0(mancante)], texttemplate="<b>%{text}</b>",
                    textposition="inside", insidetextanchor="middle",
                    textfont=dict(color="#ffffff", size=13))
            fig_obj.add_bar(x=[accumulo], y=[0], orientation="h", width=0.46,
                name=f"{anno_sel} accumulato", marker_color=Colors.VIOLET, marker_cornerradius=6,
                text=[eur0(accumulo, signed=True)], texttemplate="<b>%{text}</b>",
                textposition="inside", insidetextanchor="middle",
                textfont=dict(color="#ffffff", size=13), showlegend=False)
            
            # Badge Target come annotation DENTRO il grafico, in alto a destra
            fig_obj.add_annotation(
                xref="paper", yref="paper", x=1.0, y=1.15,
                text=f"<b>{_badge_label}</b>",
                showarrow=False, xanchor="right", yanchor="top",
                bgcolor="#f5a623", bordercolor="#f5a623", borderwidth=0,
                borderpad=6, font=dict(color="#07090f", size=13),
            )
            fig_obj.update_layout(barmode="overlay",
                yaxis=dict(tickvals=[1, 0], ticktext=[str(prev_year), str(anno_sel)], range=[-0.6, 1.6]),
                xaxis=dict(tickprefix="€ ", tickformat=",.0f"),
                margin=dict(l=50, r=20, t=55, b=30))
            show_chart(fig_obj, height=295, show_legend=True)
        else:
            st.info(f"Imposta il risparmio dell'anno precedente ({prev_year}) nelle impostazioni rapide.")
 
    with c2:
        st.markdown("<div class='panel-title'>📈 Andamento entrate</div>", unsafe_allow_html=True)
        entrate = log.analizza_entrate(df_mov, anno_sel)
        if not entrate.empty:
            fig_ent = go.Figure()
            vals    = entrate["Importo"].tolist()
            fig_ent.add_bar(x=entrate["Mese"], y=vals, marker_color=Colors.GREEN,
                marker_cornerradius=6, text=[eur0(v) for v in vals],
                texttemplate="<b>%{text}</b>", textposition="auto", insidetextanchor="middle")
            fig_ent.update_layout(bargap=0.30)
            fig_ent.update_yaxes(tickprefix="€ ", tickformat=",.0f", range=[0, max(vals, default=0) * 1.8])
            show_chart(fig_ent, height=300, show_legend=False)
        else:
            st.info("Nessuna entrata disponibile per l'anno selezionato.")
 
    st.markdown("<div class='panel-title'>🔮 Previsione saldo</div>", unsafe_allow_html=True)
    df_prev = log.previsione_saldo(df_mov, anno_sel, saldo_iniziale=saldo_iniziale, mese_riferimento=mese_sel)
    if not df_prev.empty:
    # 1. Recuperiamo l'ultimo punto del Reale per "agganciarlo" alla Previsione
        df_reale = df_prev[df_prev["Tipo"] == "Reale"]
        ultimo_punto_reale = df_reale.iloc[[-1]] if not df_reale.empty else None

        _tipos = df_prev["Tipo"].unique()
        _colors_prev = {"Reale": "#4f8ef0", "Previsione": "#f5a623"} # Nota: corretto da Proiezione a Previsione
        
        fig_prev = go.Figure()
        
        for _tipo in _tipos:
            _df_t = df_prev[df_prev["Tipo"] == _tipo].copy()
            
            # 2. SE è la Previsione, aggiungiamo in testa l'ultimo punto del Reale
            if _tipo == "Previsione" and ultimo_punto_reale is not None:
                _df_t = pd.concat([ultimo_punto_reale, _df_t]).drop_duplicates(subset=["Mese"], keep="last")
                # Nota: 'keep="last"' serve se per caso Aprile esiste in entrambi, 
                # ma l'aggancio serve per la linea continua.

            _color = _colors_prev.get(str(_tipo), "#f5a623")
            _y = _df_t["Saldo"].tolist()
            _text = [eur0(v) for v in _y] 

            fig_prev.add_trace(go.Scatter(
                x=_df_t["Mese"], y=_y, name=str(_tipo),
                mode="lines+markers+text",
                line=dict(color=_color, width=3, dash="dash" if _tipo == "Previsione" else "solid"),
                fill="tozeroy", 
                fillcolor=hex_to_rgba(_color, 0.05),
                marker=dict(color=_color, size=6),
                text=_text, 
                textposition="top center",
                textfont=dict(size=10, color=_color),
            ))
        fig_prev.update_yaxes(tickprefix="€ ", tickformat=",.0f")
        style_fig(fig_prev, height=320, show_legend=True)
        st.plotly_chart(fig_prev, use_container_width=True, config=PLOTLY_CONFIG)
    else:
        st.info("Dati insufficienti per la previsione saldo.")
 
 
# ============================================================
# TAB 3 — PATRIMONIO
# ============================================================
with tab_assets:
    st.markdown("<div class='section-title'>PATRIMONIO</div>", unsafe_allow_html=True)
 
    valore_pac_attuale   = s_num("pac_capitale_investito", 0.0)
    valore_fondo_attuale = s_num("fondo_capitale_investito", 0.0)
 
    # PAC
    pac_title_col, pac_badge_col = st.columns([3, 2])
    with pac_title_col:
        st.markdown("<div class='panel-title'>📈 PAC — Piano di Accumulo</div>", unsafe_allow_html=True)
    pac_badge_slot = pac_badge_col.empty() 
    tic     = pac_ticker_corrente or s_txt("pac_ticker", "")
    q_pac   = pac_quote_corrente
    inv_pac = pac_capitale_base_corrente
 
    if tic and q_pac >= 0:
        res_pac = log.analisi_pac(
            ticker=tic, quote_base=q_pac, capitale_base=inv_pac,
            versamento_mensile_proiezione=pac_vers_corrente,
            rendimento_annuo_stimato=pac_rend_corrente,
            df_transazioni=df_mov, anno_corrente=anno_sel,
        )
        s = res_pac["Sintesi"]
        valore_pac_attuale = s["Valore Attuale"]
        _badge_txt = f"Ticker {tic} | {s['Quote_Totali']} Quote"
        pac_badge_slot.markdown(
            f"<div style='text-align:right'>{badge_html(_badge_txt, 'badge-red')}</div>",
            unsafe_allow_html=True,
        )

        # ── 4 KPI cards con glow — stile coerente con Debiti ──────────────
        _pl_val   = s["P&L"]
        _pl_perc  = s["P&L %"]
        _pl_color = Colors.GREEN if _pl_val >= 0 else Colors.RED
        _pl_glow  = "rgba(16,217,138,0.18)" if _pl_val >= 0 else "rgba(242,106,106,0.18)"
        _pac_kpis = [
            ("Valore Attuale",    eur2(s["Valore Attuale"]),         Colors.ACCENT_LT,  "rgba(79,142,240,0.15)", None,       None),
            ("Rendimento",        eur2(_pl_val, signed=True),        _pl_color,          _pl_glow,               _pl_perc,   _pl_color),
            ("Tasse Plusvalenze", eur2(s["Imposte"]),                Colors.AMBER,       "rgba(245,166,35,0.15)", None,       None),
            ("Netto Smobilizzo",  eur2(s["Netto"]),                  Colors.TEXT,        "rgba(79,142,240,0.10)", None,       None),
        ]
        _pac_cols = st.columns(4)
        for _pc, (_pl, _pv, _pcolor, _pglow, _pperc, _ppcolor) in zip(_pac_cols, _pac_kpis):
            _perc_html = ""
            if _pperc is not None:
                _arrow = "↑" if float(_pperc) >= 0 else "↓"
                _perc_html = (
                    f"<div style='display:inline-flex;align-items:center;gap:4px;"
                    f"background:rgba(16,217,138,0.15);border-radius:20px;"
                    f"padding:3px 10px;margin-top:6px;font-size:0.78rem;font-weight:700;"
                    f"color:{_ppcolor};'>{_arrow} {_pperc}%</div>"
                )
            _pc.markdown(
                f"""<div style="background:#0c1120;border:1px solid rgba(92,118,178,0.22);
                border-radius:14px;padding:18px 14px 14px;text-align:center;
                box-shadow:0 4px 20px rgba(0,0,0,0.4),0 0 24px {_pglow};position:relative;overflow:hidden;">
  <div style="font-size:0.80rem;font-weight:700;letter-spacing:1.4px;text-transform:uppercase;
    color:rgba(180,200,240,0.55);margin-bottom:8px;">{_pl}</div>
  <div style="font-family:'JetBrains Mono',monospace;font-size:1.40rem;font-weight:700;color:{_pcolor};">{_pv}</div>
  {_perc_html}
  <div style="position:absolute;bottom:0;left:0;right:0;height:2px;
    background:linear-gradient(90deg,{_pcolor}60,transparent);"></div>
</div>""",
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # Info riga sotto KPI
        vers_da_reg = res_pac["Sintesi"].get("Versato_Reale_Registro", 0.0)
        _info_parts = [
            f"<span style='color:var(--green);font-weight:700;'>●</span> "
            f"Versamento mensile: <strong style='color:var(--txt);'>{eur2(pac_vers_corrente)}</strong>"
            f" &nbsp;|&nbsp; Rendimento stimato: <strong style='color:var(--green);'>{pac_rend_corrente:.2f}%</strong>"
        ]
        st.markdown(
            f"<div style='font-size:0.85rem;color:var(--txt-mid);margin-bottom:14px;"
            f"background:rgba(16,217,138,0.06);border:1px solid rgba(16,217,138,0.15);"
            f"border-radius:8px;padding:8px 14px;'>{''.join(_info_parts)}</div>",
            unsafe_allow_html=True,
        )

        df_pac  = res_pac["Grafico_Proiezione"]
        def _fmt_k(v):
            try:
                v = float(v)
                return f"€{v/1000:.1f}k" if abs(v) >= 1000 else f"€{v:.0f}"
            except Exception:
                return ""

        # Header grafico con "Versato PAC da registro" a destra
        _gcol_l, _gcol_r = st.columns([3, 2])
        _gcol_l.markdown("<div style='font-size:0.82rem;font-weight:600;color:#94a3b8;padding:4px 0;'>Proiezione PAC</div>", unsafe_allow_html=True)
        if vers_da_reg is not None:
            _gcol_r.markdown(
                f"<div style='text-align:right;font-size:0.80rem;color:#82b4f7;padding:4px 0;'>"
                f"Versamento PAC da registro ({anno_sel}): "
                f"<strong style='color:#34d399;'>{eur2(vers_da_reg)}</strong></div>",
                unsafe_allow_html=True,
            )

        fig_pac = go.Figure()
        for name, color, fill in [
            ("Proiezione Stimata", "#34d399", "tozeroy"),
            ("Capitale Versato",   "#60a5fa", "tozeroy"),
            ("Valore Netto",       "#facc15", "none"),
        ]:
            _y = df_pac[name]
            _n = max(1, len(_y) // 12)
            _text = [_fmt_k(v) if i % _n == 0 else "" for i, v in enumerate(_y)]
            fig_pac.add_trace(go.Scatter(
                x=df_pac["Mese"], y=_y, name=name,
                mode="lines+text",
                line=dict(color=color, width=2 if name == "Proiezione Stimata" else 2),
                fill=fill, fillcolor=hex_to_rgba(color, 0.1),
                text=_text, textposition="top center",
                textfont=dict(size=11, color=color),
                cliponaxis=False, 
            ))
        style_fig(fig_pac, height=380, show_legend=True)
        fig_pac.update_layout(margin=dict(l=10, r=10, t=60, b=10)) 
        fig_pac.update_xaxes(rangemode="tozero", range=[0, None])
        st.plotly_chart(fig_pac, use_container_width=True, config=PLOTLY_CONFIG)
    else:
        pac_badge_slot.empty()
        st.info("Imposta 'Ticker' e 'Quote' nelle impostazioni rapide per visualizzare il PAC.")
 
    st.divider()
 
    # Fondo pensione
    st.markdown("<div class='panel-title'>🏦 Fondo Pensione</div>", unsafe_allow_html=True)
    valore_quota = fondo_valore_quota_corrente
    q_fondo      = fondo_quote_corrente
    inv_fondo    = fondo_capitale_base_corrente
 
    if valore_quota > 0 and q_fondo > 0:
        _fondo_snapshot = pd.to_datetime(s_txt("fondo_data_snapshot", str(date.today())), errors="coerce").date()
        _fondo_tfr      = s_num("fondo_tfr_versato_anno", 0.0)
        res_fondo = log.analisi_fondo_pensione(
            valore_quota, q_fondo, inv_fondo, fondo_vers_corrente, fondo_rend_corrente,
            df_mov, anno_sel, aliquota_irpef=aliquota_irpef_corrente, anni=30,
            data_snapshot=_fondo_snapshot, tfr_versato_anno=_fondo_tfr,
        )
        valore_fondo_attuale = res_fondo["Sintesi"]["Valore Attuale"]
        perc_fp   = min(res_fondo["Avanzamento_Fiscale"]["Percentuale"] / 100, 1.0)
        _fp_pl    = res_fondo["Sintesi"]["P&L"]
        _fp_perc  = res_fondo["Sintesi"]["P&L %"]
        _fp_color = Colors.GREEN if _fp_pl >= 0 else Colors.RED
        _fp_glow  = "rgba(16,217,138,0.18)" if _fp_pl >= 0 else "rgba(242,106,106,0.18)"

        # Quote possedute formattata IT
        _fp_quote_str = f"{res_fondo['Sintesi']['Quote Attuali']:,.2f}".replace(",","X").replace(".",",").replace("X",".")

        # ── 3 KPI cards con glow ───────────────────────────────────────────
        _fondo_kpis = [
            ("Valore Attuale",   eur2(res_fondo["Sintesi"]["Valore Attuale"]), Colors.ACCENT_LT, "rgba(79,142,240,0.15)", None,      None),
            ("Quote Possedute",  _fp_quote_str,                                Colors.TEXT,      "rgba(79,142,240,0.10)", None,      None),
            ("Rendimento",       eur2(_fp_pl, signed=True),                    _fp_color,        _fp_glow,               _fp_perc,  _fp_color),
        ]
        _fp_cols = st.columns(3)
        for _fc, (_fl, _fv, _fcolor, _fglow, _fperc, _fpcolor) in zip(_fp_cols, _fondo_kpis):
            _fp_perc_html = ""
            if _fperc is not None:
                _arrow = "↑" if float(_fperc) >= 0 else "↓"
                _fp_perc_html = (
                    f"<div style='display:inline-flex;align-items:center;gap:4px;"
                    f"background:rgba(16,217,138,0.15);border-radius:20px;"
                    f"padding:3px 10px;margin-top:6px;font-size:0.78rem;font-weight:700;"
                    f"color:{_fpcolor};'>{_arrow} {_fperc}%</div>"
                )
            _fc.markdown(
                f"""<div style="background:#0c1120;border:1px solid rgba(92,118,178,0.22);
                border-radius:14px;padding:10px 10px 10px;text-align:center;
                box-shadow:0 4px 20px rgba(0,0,0,0.4),0 0 24px {_fglow};position:relative;overflow:hidden;">
  <div style="font-size:0.80rem;font-weight:700;letter-spacing:1.4px;text-transform:uppercase;
    color:rgba(180,200,240,0.55);margin-bottom:8px;">{_fl}</div>
  <div style="font-family:'JetBrains Mono',monospace;font-size:1.40rem;font-weight:700;color:{_fcolor};">{_fv}</div>
  {_fp_perc_html}
  <div style="position:absolute;bottom:0;left:0;right:0;height:2px;
    background:linear-gradient(90deg,{_fcolor}60,transparent);"></div>
</div>""",
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        # ── Progress bar avanzamento fiscale ──────────────────────────────
        _avanc    = res_fondo["Avanzamento_Fiscale"]
        _versato  = _avanc.get("Versato_Anno", 0.0)
        _soglia   = _avanc.get("Soglia_Deducibile", 5164.57)
        _rim      = max(_soglia - _versato, 0)
        st.markdown(
            f"<div style='margin-bottom:4px;font-size:0.82rem;font-weight:600;color:#94a3b8;'>"
            f"Avanzamento versamento ({perc_fp*100:.1f}%)</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div class='progress-wrap'><div class='progress-track'>"
            f"<div class='progress-fill' style='width:{perc_fp*100:.1f}%'></div>"
            f"</div></div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div style='font-size:0.78rem;color:#5a6f8c;margin-top:4px;margin-bottom:12px;'>"
            f"Versato anno: <strong style='color:#dde6f5;'>{eur2(_versato)}</strong>"
            f" &nbsp;|&nbsp; Rimanente soglia: <strong style='color:#f5a623;'>{eur2(_rim)}</strong></div>",
            unsafe_allow_html=True,
        )

        # ── Header grafico Fondo ──────────────────────────────────────────
        _fh_l, _fh_r = st.columns([3, 2])
        _fh_l.markdown("<div style='font-size:0.82rem;font-weight:600;color:#94a3b8;padding:4px 0;'>Proiezione Fondo Pensione</div>", unsafe_allow_html=True)
        _fh_r.markdown(
            f"<div style='text-align:right;font-size:0.80rem;color:#82b4f7;padding:4px 0;'>"
            f"Proiezione 30 anni — rendimento stimato: "
            f"<strong style='color:#f472b6;'>{fondo_rend_corrente:.2f}%</strong></div>",
            unsafe_allow_html=True,
        )

        df_fondo = res_fondo["Grafico_Proiezione"].copy()
        fig_fondo = go.Figure()
        for name, color, fill in [
            ("Proiezione Teorica", "#f472b6", "tozeroy"),
            ("Cap.Versato Cumu.", "#60a5fa", "tozeroy"),
            ("Valore Attuale Linea", "#facc15", "none"),
        ]:
            _y2 = df_fondo[name]
            _n2 = max(1, len(_y2) // 10)
            _text2 = [_fmt_k(v) if i % _n2 == 0 else "" for i, v in enumerate(_y2)]
            fig_fondo.add_trace(go.Scatter(
                x=df_fondo["Mese"], y=_y2, mode="lines+text",
                line=dict(color=color, width=3 if "Teorica" in name else 2,
                          dash="dash" if "Linea" in name else "solid"),
                fill=fill, fillcolor=hex_to_rgba(color, 0.08),
                name=name.replace(" Linea", ""),
                text=_text2, textposition="top center",
                textfont=dict(size=11, color=color),
                cliponaxis=False, 
            ))
        style_fig(fig_fondo, height=380, show_legend=True)
        fig_fondo.update_layout(margin=dict(l=10, r=10, t=60, b=10)) 
        fig_fondo.update_xaxes(rangemode="tozero", range=[0, None])
        st.plotly_chart(fig_fondo, use_container_width=True, config=PLOTLY_CONFIG)
    else:
        st.info("Imposta valore quota e quote fondo nelle impostazioni rapide.")
 
    st.divider()
 
    # Composizione portafoglio
    r1, r2 = st.columns(2)
    with r1:
        st.markdown("<div class='panel-title'>Composizione portafoglio</div>", unsafe_allow_html=True)
        comp = log.composizione_portafoglio(
            float(saldo_disponibile), float(saldo_revolut_set),
            valore_pac_attuale, valore_fondo_attuale,
        )
        if comp:
            fig_comp = px.pie(comp["Dettaglio"], names="Asset", values="Valore",
                hole=0.35, color_discrete_sequence=Colors.SEQ)
            fig_comp.update_traces(textinfo="percent+label", textposition="inside")
            fig_comp.update_layout(showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
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
            mask_pac   = det.str.contains("PAC", na=False)
            mask_fondo = det.str.contains("FONDO|PENSION", na=False, regex=True)
            df_inv = df_inv[mask_pac | mask_fondo].copy()
            if not df_inv.empty:
                df_inv["Dettaglio"] = det.loc[df_inv.index].apply(
                    lambda x: "PAC" if "PAC" in x else "FONDO PENSIONE"
                )
                df_inv = df_inv.groupby(["Mese", "Dettaglio"])["Importo"].sum().abs().reset_index()
                pivot  = df_inv.pivot_table(index="Mese", columns="Dettaglio", values="Importo", fill_value=0)\
                    .reindex(list(MONTH_SHORT.values()), fill_value=0)
                fig_vers = go.Figure()
                for col in pivot.columns:
                    if "PAC" in col.upper():
                        line_color, fill_color = "#34d399", "rgba(52,211,153,0.12)"
                    else:
                        line_color, fill_color = "#f472b6", "rgba(244,114,182,0.12)"

                    vals = pivot[col].tolist()
                    labels = [_fmt_k(v) if v > 0 else "" for v in vals]

                    fig_vers.add_trace(go.Scatter(
                        x=list(MONTH_SHORT.values()), y=vals,
                        mode="lines+markers+text",
                        name=col.title(),
                        line=dict(shape="hvh", width=2, color=line_color),
                        fill="tozeroy", fillcolor=fill_color,
                        text=labels,
                        textposition="top center",
                        textfont=dict(size=10, color=line_color),
                        cliponaxis=False,
                    ))
                style_fig(fig_vers, height=300, show_legend=True)
                st.plotly_chart(fig_vers, use_container_width=True, config=PLOTLY_CONFIG)
            else:
                st.info("Nessun versamento PAC/Fondo trovato.")
        else:
            st.info("Nessun versamento registrato per l'anno selezionato.")
 
 
    # ── Variazione investimenti anno precedente vs attuale ────────────────────
    st.divider()
    st.markdown("<div class='panel-title'>📊 Variazione investimenti (anno precedente vs attuale)</div>", unsafe_allow_html=True)
    _prev_y = anno_sel - 1
    def _inv_totale_anno(df, anno):
        _d = df[
            (df["Categoria"] == "INVESTIMENTI") &
            (df["Tipo"] == "USCITA") &
            (df["Data"].dt.year == anno)
        ]
        _det = _d["Dettaglio"].astype(str).str.upper().str.strip()
        _pac   = _d[_det.str.contains("PAC", na=False)]["Importo"].abs().sum()
        _fondo = _d[_det.str.contains("FONDO|PENSION", na=False, regex=True)]["Importo"].abs().sum()
        return _pac, _fondo

    _pac_prev,   _fondo_prev   = _inv_totale_anno(df_mov, _prev_y)
    _pac_curr,   _fondo_curr   = _inv_totale_anno(df_mov, anno_sel)
    _tot_prev = _pac_prev + _fondo_prev
    _tot_curr = _pac_curr + _fondo_curr
    _delta    = _tot_curr - _tot_prev
    _delta_pct = (_delta / _tot_prev * 100) if _tot_prev > 0 else 0

    if _tot_prev > 0 or _tot_curr > 0:
        fig_var = go.Figure()

        _anni = [str(_prev_y), str(anno_sel)]

        fig_var.add_bar(
            x=_anni,
            y=[_pac_prev, _pac_curr],
            name="PAC",
            marker_color="#fb7185",
            marker_cornerradius=6,
            text=[
                eur0(_pac_prev) if _pac_prev > 0 else "",
                eur0(_pac_curr) if _pac_curr > 0 else "",
            ],
            texttemplate="<b>%{text}</b>",
            textposition="inside",
            textfont=dict(color="#ffffff", size=13),
        )

        fig_var.add_bar(
            x=_anni,
            y=[_fondo_prev, _fondo_curr],
            name="Fondo Pensione",
            marker_color="#facc15",
            marker_cornerradius=6,
            text=[
                eur0(_fondo_prev) if _fondo_prev > 0 else "",
                eur0(_fondo_curr) if _fondo_curr > 0 else "",
            ],
            texttemplate="<b>%{text}</b>",
            textposition="inside",
            textfont=dict(color="#07090f", size=13),
        )

        fig_var.update_layout(
            barmode="group",
            bargap=0.40,
            bargroupgap=0.10,
        )

        fig_var.update_yaxes(tickprefix="€ ", tickformat=",.0f")
        style_fig(fig_var, height=320, show_legend=True)
        st.plotly_chart(fig_var, use_container_width=True, config=PLOTLY_CONFIG)
    else:
        st.info("Nessun versamento investimento trovato per gli anni selezionati.")


# ============================================================
# TAB 4 — DEBITI
# ============================================================
with tab_debts:
    st.markdown("<div class='section-title'>DEBITI</div>", unsafe_allow_html=True)
 
    COLOR_PAGATO      = "#4f8ef0"
    COLOR_RESIDUO     = "#97464d"
    COLOR_RESIDUO_pie = "#97464d"
    COLOR_INT_PAGATI  = "#f5a623"
    COLOR_INT_RESIDUI = "#5D799D"
 
    import re as _re
 
    def _fin_match_pattern(nome: str) -> str | None:
        if not nome:
            return None
        raw    = str(nome).strip()
        tokens = [raw]
        if "." in raw:
            tokens.append(raw.split(".")[-1])
        tokens.append(_re.sub(r"^fin\.?\s*", "", raw, flags=_re.I))
        for t in _re.split(r"[\s\-_/.]+", raw):
            if len(t.strip()) >= 3:
                tokens.append(t.strip())
        tokens = list(dict.fromkeys(t for t in tokens if t.strip()))
        return "|".join(_re.escape(t) for t in tokens) if tokens else None
 
    def _mesi_pagati_da_mov(df_m, nome_fin: str, rata, data_inizio=None) -> int | None:
        if df_m is None or df_m.empty:
            return None
        pattern = _fin_match_pattern(nome_fin)
        if not pattern:
            return None
        tipo  = df_m["Tipo"].astype(str).str.upper().str.strip()
        mask  = (tipo == "USCITA") & (
            df_m["Dettaglio"].astype(str).str.contains(pattern, case=False, na=False) |
            df_m["Note"].astype(str).str.contains(pattern, case=False, na=False)
        )
        df_f = df_m[mask].copy()
        if df_f.empty:
            return None
        df_f["Data"] = pd.to_datetime(df_f["Data"], errors="coerce")
        df_f = df_f[df_f["Data"].notna()]
        if data_inizio is not None:
            inizio = pd.to_datetime(data_inizio, errors="coerce")
            if pd.notna(inizio):
                df_f = df_f[df_f["Data"] >= inizio]
        if df_f.empty:
            return None
        rata_abs = abs(float(rata)) if rata is not None else 0.0
        if rata_abs > 0:
            tol  = max(1.0, rata_abs * 0.25)
            df_f = df_f[df_f["Importo"].abs().between(rata_abs - tol, rata_abs + tol)]
        return int(len(df_f)) if not df_f.empty else None
 
    if df_fin_db.empty:
        st.info("Nessun finanziamento presente. Aggiungilo nel tab Registro.")
    else:
        totale_capitale  = df_fin_db["capitale_iniziale"].sum()
        totale_residuo   = 0.0
        interessi_pagati = 0.0
        interessi_totali = 0.0
        fin_rows         = []
        dettagli_rows    = []
        interessi_rows   = []  # per grafico interessi per finanziamento

        for _, f in df_fin_db.iterrows():
            dati_base     = log.calcolo_finanziamento(f["capitale_iniziale"], f["taeg"], f["durata_mesi"], f["data_inizio"], f["giorno_scadenza"])
            rate_db       = int(f["rate_pagate"]) if "rate_pagate" in f.index and pd.notna(f["rate_pagate"]) else None
            rate_mov      = _mesi_pagati_da_mov(df_mov, f["nome"], dati_base["rata"], f["data_inizio"])
            rate_cal      = int(dati_base.get("mesi_pagati", 0))
            vals          = [v for v in [rate_db, rate_mov, rate_cal] if v is not None]
            rate_eff      = max(vals) if vals else None
            dati          = log.calcolo_finanziamento(f["capitale_iniziale"], f["taeg"], f["durata_mesi"], f["data_inizio"], f["giorno_scadenza"], rate_pagate_override=rate_eff)

            pagato  = max(dati["capitale_pagato"], 0)
            residuo = max(dati["debito_residuo"],  0)
            fin_rows.append({"Nome": f["nome"], "Pagato": pagato, "Residuo": residuo})
            dettagli_rows.append({"Nome": f["nome"], "Rata": dati["rata"], "Residuo": dati["debito_residuo"],
                "% Completato": round(dati["percentuale_completato"], 1), "Mesi rim.": dati["mesi_rimanenti"]})
            interessi_rows.append({
                "Nome":     f["nome"],
                "Pagati":   max(dati["interessi_pagati"], 0),
                "Residui":  max(dati["interessi_totali"] - dati["interessi_pagati"], 0),
            })
            totale_residuo   += residuo
            interessi_pagati += dati["interessi_pagati"]
            interessi_totali += dati["interessi_totali"]

        df_prog     = pd.DataFrame(fin_rows)
        df_int_fin  = pd.DataFrame(interessi_rows)  # interessi per finanziamento
        totale_pag  = max(0.0, totale_capitale - totale_residuo)
        int_res     = max(0.0, interessi_totali - interessi_pagati)

        # ── 4 KPI cards riepilogo ──────────────────────────────────────────
        _d_kpis = [
            ("Capitale totale",   eur2(totale_capitale),  Colors.TEXT,       "rgba(79,142,240,0.15)"),
            ("Debito residuo",    eur2(totale_residuo),   Colors.RED_BRIGHT, "rgba(250,89,142,0.18)"),
            ("Interessi pagati",  eur2(interessi_pagati), Colors.AMBER,      "rgba(245,166,35,0.15)"),
            ("Interessi residui", eur2(int_res),          Colors.AMBER,      "rgba(245,166,35,0.12)"),
        ]
        _dk_cols = st.columns(4)
        for _dc, (_dl, _dv, _dcolor, _dglow) in zip(_dk_cols, _d_kpis):
            _dc.markdown(
                f"""<div style="background:#0c1120;border:1px solid rgba(92,118,178,0.22);
                border-radius:14px;padding:18px 14px 14px;text-align:center;
                box-shadow:0 4px 20px rgba(0,0,0,0.4),0 0 24px {_dglow};position:relative;overflow:hidden;margin-bottom:4px;">
  <div style="font-size:0.80rem;font-weight:700;letter-spacing:1.4px;text-transform:uppercase;
    color:rgba(180,200,240,0.55);margin-bottom:8px;">{_dl}</div>
  <div style="font-family:'JetBrains Mono',monospace;font-size:1.40rem;font-weight:700;color:{_dcolor};">{_dv}</div>
  <div style="position:absolute;bottom:0;left:0;right:0;height:2px;
    background:linear-gradient(90deg,{_dcolor}60,transparent);"></div>
</div>""",
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

        # ── Riga 1: avanzamento (sinistra) + pie (destra) — layout simmetrico [1.4, 1] ──
        c1, c2 = st.columns([1.4, 1], gap="large")
        with c1:
            st.markdown("<div class='panel-title'>📊 Avanzamento finanziamenti</div>", unsafe_allow_html=True)
            fig_prog = go.Figure()
            fig_prog.add_bar(y=df_prog["Nome"], x=df_prog["Pagato"], orientation="h",
                name="Totale pagato", marker_color="#10d98a", marker_cornerradius=6,
                text=df_prog["Pagato"].map(eur0), textposition="auto", insidetextanchor="middle",
                textfont=dict(color="#07090f", size=14))
            fig_prog.add_bar(y=df_prog["Nome"], x=df_prog["Residuo"], orientation="h",
                name="Debito residuo", marker_color=COLOR_RESIDUO, marker_cornerradius=6,
                text=df_prog["Residuo"].map(eur0), textposition="auto", insidetextanchor="middle",
                textfont=dict(color="#ffffff", size=14))
            fig_prog.update_layout(barmode="stack", xaxis=dict(tickprefix="€ ", tickformat=",.0f"))
            style_fig(fig_prog, height=300, show_legend=True)
            st.plotly_chart(fig_prog, use_container_width=True, config=PLOTLY_CONFIG)

        with c2:
            st.markdown("<div class='panel-title'>🥧 Pagato vs Residuo</div>", unsafe_allow_html=True)
            fig_pie = go.Figure(go.Pie(
                labels=["Pagato", "Residuo"], values=[totale_pag, totale_residuo],
                hole=0.35, textinfo="percent+label",
                marker=dict(colors=["#10d98a", "rgba(242,106,106,0.60)"]),
                textfont=dict(size=13, color="#ffffff"),
            ))
            style_fig(fig_pie, height=300, show_legend=False)
            st.plotly_chart(fig_pie, use_container_width=True, config=PLOTLY_CONFIG)

        # ── Riga 2: interessi per finanziamento (sinistra) + riepilogo rate (destra) — [1.4, 1] ──
        c3, c4 = st.columns([1.4, 1], gap="large")
        with c3:
            st.markdown("<div class='panel-title'>💰 Interessi pagati vs residui </div>", unsafe_allow_html=True)
            fig_int = go.Figure()
            if not df_int_fin.empty:
                # Una barra per ciascun finanziamento: pagati + residui stacked
                fig_int.add_bar(
                    y=df_int_fin["Nome"], x=df_int_fin["Pagati"], orientation="h",
                    name="Interessi pagati", marker_color=COLOR_INT_PAGATI, marker_cornerradius=6,
                    text=df_int_fin["Pagati"].map(eur0), textposition="auto",
                    insidetextanchor="middle", textfont=dict(color="#07090f", size=16),
                )
                fig_int.add_bar(
                    y=df_int_fin["Nome"], x=df_int_fin["Residui"], orientation="h",
                    name="Interessi residui", marker_color=COLOR_INT_RESIDUI, marker_cornerradius=6,
                    text=df_int_fin["Residui"].map(eur0), textposition="auto",
                    insidetextanchor="middle", textfont=dict(color="#ffffff", size=16),
                )
            fig_int.update_layout(
                barmode="stack",
                xaxis=dict(tickprefix="€ ", tickformat=",.0f"),
                yaxis=dict(tickfont=dict(color=Colors.TEXT)),
                margin=dict(l=10, r=20, t=20, b=10),
            )
            style_fig(fig_int, height=300, show_legend=True)
            st.plotly_chart(fig_int, use_container_width=True, config=PLOTLY_CONFIG)

        with c4:
            st.markdown("<div class='panel-title'>📋 Riepilogo rate</div>", unsafe_allow_html=True)
            df_tabella = pd.DataFrame(dettagli_rows)
            if not df_tabella.empty:
                debt_rows = []
                for _, row in df_tabella.iterrows():
                    perc       = float(row["% Completato"])
                    mesi_r     = int(row["Mesi rim."])
                    perc_color = Colors.GREEN if perc >= 50 else Colors.AMBER if perc >= 25 else Colors.RED
                    mesi_color = Colors.RED   if mesi_r > 120 else Colors.AMBER if mesi_r > 36 else Colors.GREEN
                    debt_rows.append(_tr([
                        _td(f"<strong>{escape(str(row['Nome']))}</strong>", color=Colors.TEXT, weight=600),
                        _td(f"<span style='white-space:nowrap'>{eur2(row['Rata'])}</span>",    color=Colors.RED,  mono=True, weight=600),
                        _td(f"<span style='white-space:nowrap'>{eur2(row['Residuo'])}</span>", color=Colors.TEXT, mono=True),
                        _td(f"<span style='white-space:nowrap'>{perc:.1f}%</span>",            color=perc_color,  mono=True, align="center"),
                        _td(str(mesi_r),                                                        color=mesi_color,  mono=True, align="center"),
                    ]))
                st.markdown(scroll_table(
                    title="Riepilogo finanziamenti", right_html="",
                    columns=[("Nome","left"),("Rata","right"),("Residuo","right"),("% Compl.","center"),("Mesi","center")],
                    widths=[2.0, 1.5, 1.8, 1.0, 0.7],
                    rows_html=debt_rows, height_px=300,
                ), unsafe_allow_html=True)
            else:
                st.info("Nessun dettaglio rate disponibile.")

 
 
# ============================================================
# TAB 5 — REGISTRO
# ============================================================
with tab_admin:
    st.markdown("<div class='section-title'>Registro</div>", unsafe_allow_html=True)
 
    if st.session_state.pop("_banner_mov", False):
        st.success("✅ Movimento registrato con successo!")
 
    # ── Nuova transazione ──
    with st.container(border=True):
        st.markdown("""<div style="display:flex;align-items:center;gap:10px;margin-bottom:18px;">
  <div style="width:28px;height:28px;border-radius:7px;background:rgba(79,142,240,0.12);
              display:flex;align-items:center;justify-content:center;font-size:15px;">💳</div>
  <span style="font-size:13px;font-weight:700;color:#dde6f5;">Nuova Transazione</span>
</div>""", unsafe_allow_html=True)
 
        col_tipo, col_cat, col_det, col_data = st.columns([1, 1, 1.5, 1])
        tipo_inserito     = col_tipo.radio("Tipo movimento", ["↑ Uscita", "↓ Entrata"], horizontal=True, key="reg_tipo_radio")
        tipo_val          = "USCITA" if "Uscita" in tipo_inserito else "ENTRATA"
        categoria_scelta  = col_cat.selectbox("Categoria", list(STRUTTURA_CATEGORIE.keys()), key="reg_categoria")
        dettagli_filtrati = STRUTTURA_CATEGORIE[categoria_scelta]
        dettaglio_scelto  = col_det.selectbox("Dettaglio", dettagli_filtrati, key="reg_dettaglio")
        data_inserita     = col_data.date_input("Data", datetime.now(), key="reg_data")
 
        col_imp, col_note = st.columns([1, 3])
        importo_inserito  = col_imp.number_input("Importo (€)", min_value=0.0, step=0.01, format="%.2f", key="reg_importo")
        note_inserite     = col_note.text_input("Note", placeholder="Descrizione opzionale…", key="reg_note")
 
        col_btn, col_ann, _ = st.columns([1.2, 0.8, 3])
        if col_btn.button("＋ Registra Movimento", key="btn_registra_mov", use_container_width=True, type="primary"):
            if importo_inserito <= 0:
                st.warning("Inserisci un importo maggiore di zero.")
            else:
                try:
                    db.aggiungi_movimento(
                        data_inserita, tipo_val,
                        st.session_state.get("reg_categoria", categoria_scelta),
                        st.session_state.get("reg_dettaglio", dettaglio_scelto),
                        importo_inserito, note_inserite, user_email=user_email,
                    )
                    st.session_state["_banner_mov"] = True
                    for k in ["reg_importo", "reg_note", "reg_data"]:
                        st.session_state.pop(k, None)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Errore salvataggio: {exc}")
        if col_ann.button("Annulla", key="btn_annulla_mov", use_container_width=True):
            for k in ["reg_importo", "reg_note", "reg_data"]:
                st.session_state.pop(k, None)
            st.rerun()
 
    # ── Spese ricorrenti ──
    with st.container(border=True):
        df_ric_view = db.carica_spese_ricorrenti(user_email)
        n_ric = len(df_ric_view) if not df_ric_view.empty else 0
        st.markdown(f"""<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
  <span style="font-size:13px;font-weight:700;color:#dde6f5;">🔁 Spese Ricorrenti</span>
  <span style="font-size:10px;padding:3px 10px;border-radius:20px;background:rgba(79,142,240,0.12);
               color:#82b4f7;border:1px solid rgba(79,142,240,0.28);">{n_ric} attive</span>
</div>""", unsafe_allow_html=True)
 
        with st.form("form_spese_ricorrenti", clear_on_submit=False):
            c_desc, c_imp, c_freq = st.columns([2, 1, 1])
            descrizione = c_desc.text_input("Descrizione spesa", key="ric_desc")
            importo_ric = c_imp.number_input("Importo (€)", min_value=0.0, step=0.01, key="ric_importo")
            freq_label  = c_freq.selectbox("Frequenza", list(FREQ_OPTIONS.keys()), key="ric_freq")
            freq_val    = FREQ_OPTIONS[freq_label]
 
            c_g, c_s, c_e, c_check = st.columns([1, 1, 1, 1])
            giorno_scad  = c_g.number_input("Giorno scadenza", 1, 31, 1, 1, key="ric_giorno")
            data_inizio  = c_s.date_input("Data inizio", datetime.now(), key="ric_data_inizio")
            senza_fine   = c_check.checkbox("Senza data fine", value=False, key="ric_senza_fine")
            data_fine    = None if senza_fine else c_e.date_input("Data fine", datetime.now(), key="ric_data_fine")
 
            if st.form_submit_button("＋ Aggiungi Ricorrente"):
                if descrizione and importo_ric > 0:
                    try:
                        db.aggiungi_spesa_ricorrente(descrizione, importo_ric, giorno_scad, freq_val, data_inizio, data_fine, user_email=user_email)
                        for k in ["ric_desc", "ric_importo", "ric_giorno"]:
                            st.session_state.pop(k, None)
                        st.session_state["_banner_ric"] = True
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Errore: {exc}")
                else:
                    st.warning("Inserisci descrizione e importo.")
 
        if st.session_state.pop("_banner_ric", False):
            st.success("✅ Spesa ricorrente salvata!")
 
        if not df_ric_view.empty:
            tot_mensile  = df_ric_view["importo"].sum()
            ric_rows_html = render_ricorrenti_rows(df_ric_view, FREQ_MAP)
            st.markdown(scroll_table(
                title="Elenco ricorrenti",
                right_html=f"{format_eur(tot_mensile, 2)} / mese",
                columns=[("#","left"),("Descrizione","left"),("Importo","left"),("Frequenza","left"),("Scad.","center"),("Inizio","center"),("Fine","center")],
                widths=[0.45, 2.6, 1.1, 1.25, 0.7, 1.1, 0.9],
                rows_html=ric_rows_html, height_px=320,
            ), unsafe_allow_html=True)
 
            col_sel_ric, col_btn_ric = st.columns([4, 1], vertical_alignment="bottom")
            ric_id = col_sel_ric.selectbox(
                "Seleziona ricorrente da eliminare",
                df_ric_view["id"].tolist(),
                format_func=lambda sid: f"{df_ric_view.loc[df_ric_view['id']==sid].iloc[0]['descrizione']} | {format_eur(df_ric_view.loc[df_ric_view['id']==sid].iloc[0]['importo'], 2)}" if not df_ric_view[df_ric_view['id']==sid].empty else str(sid),
                key="sel_del_ric",
            )
            if col_btn_ric.button("🗑️ Elimina", key="btn_del_ric", use_container_width=True):
                st.session_state["pending_delete_ric"] = ric_id
 
            if st.session_state.get("pending_delete_ric") is not None:
                sid  = st.session_state["pending_delete_ric"]
                desc = df_ric_view.loc[df_ric_view["id"] == sid, "descrizione"].values[0] if not df_ric_view[df_ric_view["id"]==sid].empty else str(sid)
                st.warning(f"⚠️ Elimina **{desc}**? Operazione irreversibile.")
                cc1, cc2 = st.columns(2)
                if cc1.button("🗑️ Sì, elimina", key="confirm_del_ric", use_container_width=True, type="primary"):
                    db.elimina_spesa_ricorrente(sid, user_email=user_email)
                    del st.session_state["pending_delete_ric"]
                    st.session_state["_success_ric_ts"] = datetime.now().timestamp()
                    st.rerun()
                if cc2.button("Annulla", key="cancel_del_ric", use_container_width=True):
                    del st.session_state["pending_delete_ric"]
                    st.rerun()
 
            if "_success_ric_ts" in st.session_state:
                if datetime.now().timestamp() - st.session_state["_success_ric_ts"] < 3:
                    st.success("✅ Spesa ricorrente eliminata.")
                else:
                    del st.session_state["_success_ric_ts"]
 
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
 
    # ── Finanziamenti ──
    with st.container(border=True):
        n_fin = len(df_fin_db) if not df_fin_db.empty else 0
        st.markdown(f"""<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
  <span style="font-size:13px;font-weight:700;color:#dde6f5;">🏦 Nuovo Finanziamento</span>
  <span style="font-size:10px;padding:3px 10px;border-radius:20px;background:rgba(79,142,240,0.12);
               color:#82b4f7;border:1px solid rgba(79,142,240,0.28);">{n_fin} attivi</span>
</div>""", unsafe_allow_html=True)
 
        with st.form("form_finanziamento", clear_on_submit=False):
            c1, c2, c3 = st.columns(3)
            nome_fin  = c1.text_input("Nome finanziamento", key="fin_nome")
            capitale  = c2.number_input("Capitale iniziale (€)", 0.0, step=0.1, format="%.2f", key="fin_capitale")
            taeg      = c3.number_input("TAEG (%)", 0.0, step=0.01, key="fin_taeg")
            c4, c5, c6, c7 = st.columns(4)
            durata    = c4.number_input("Durata (mesi)", 1, step=1, key="fin_durata")
            data_inizio_fin   = c5.date_input("Data inizio", key="fin_data_inizio")
            giorno_scad_fin   = c6.number_input("Giorno scadenza", 1, 31, 1, 1, key="fin_giorno")
            rate_pagate_input = c7.number_input("Rate già pagate", 0, step=1, value=0, key="fin_rate")
 
            if st.form_submit_button("💾 Salva Finanziamento"):
                if nome_fin and capitale > 0 and durata > 0:
                    try:
                        db.aggiungi_finanziamento(nome_fin, capitale, taeg, durata, data_inizio_fin,
                            giorno_scad_fin, rate_pagate=int(rate_pagate_input) or None, user_email=user_email)
                        for k in ["fin_nome","fin_capitale","fin_taeg","fin_durata","fin_rate","fin_giorno"]:
                            st.session_state.pop(k, None)
                        st.success("✅ Finanziamento salvato!")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Errore: {exc}")
                else:
                    st.warning("Compila nome, capitale e durata.")
 
        if not df_fin_db.empty:
            import re as _re2
            fin_rows_html = []
            for _, f in df_fin_db.iterrows():
                dati_b    = log.calcolo_finanziamento(f["capitale_iniziale"], f["taeg"], f["durata_mesi"], f["data_inizio"], f["giorno_scadenza"])
                rate_db   = int(f["rate_pagate"]) if "rate_pagate" in f.index and pd.notna(f["rate_pagate"]) else None
                rate_mov  = _mesi_pagati_da_mov(df_mov, f["nome"], dati_b["rata"], f["data_inizio"]) if "DEBITI" not in str(tab_debts) else None
                rate_cal  = int(dati_b.get("mesi_pagati", 0))
                vals_r    = [v for v in [rate_db, rate_mov, rate_cal] if v is not None]
                rate_eff  = max(vals_r) if vals_r else None
                dati      = log.calcolo_finanziamento(f["capitale_iniziale"], f["taeg"], f["durata_mesi"], f["data_inizio"], f["giorno_scadenza"], rate_pagate_override=rate_eff)
                taeg_pct  = f["taeg"]
                taeg_c, taeg_bg, taeg_bd = (
                    ("#f5a623", "rgba(245,166,35,0.10)", "rgba(245,166,35,0.26)") if taeg_pct > 5
                    else ("#10d98a", "rgba(16,217,138,0.10)", "rgba(16,217,138,0.26)")
                )
                fin_rows_html.append(_tr([
                    _td(f"<strong>{escape(str(f['nome']))}</strong>", color=Colors.TEXT, weight=600),
                    _td(format_eur(f["capitale_iniziale"], 0), color=Colors.TEXT, mono=True),
                    _td(chip_html(f"{taeg_pct:.2f}%", taeg_c, taeg_bg, taeg_bd), nowrap=True),
                    _td(f"{int(f['durata_mesi'])}m",        color=Colors.TEXT_MID, mono=True, align="center"),
                    _td(str(f["data_inizio"])[:10],         color=Colors.TEXT_MID, mono=True, align="center"),
                    _td(format_eur(dati["rata"], 2),        color=Colors.RED,      mono=True, weight=600),
                    _td(str(rate_eff or 0),                 color=Colors.TEXT_MID, mono=True, align="center"),
                ]))
 
            try:
                totale_rate = sum(log.calcolo_finanziamento(r["capitale_iniziale"], r["taeg"], r["durata_mesi"], r["data_inizio"], r["giorno_scadenza"])["rata"] for _, r in df_fin_db.iterrows())
                right_fin   = f"{format_eur(totale_rate, 2)} / mese"
            except Exception:
                right_fin   = ""
 
            st.markdown(scroll_table(
                title="Finanziamenti in corso", right_html=right_fin,
                columns=[("Nome","left"),("Capitale","left"),("TAEG","left"),("Durata","center"),("Inizio","center"),("Rata","left"),("Rate pag.","center")],
                widths=[1.8, 1.2, 0.9, 0.8, 1.1, 1.1, 0.9],
                rows_html=fin_rows_html, height_px=280,
            ), unsafe_allow_html=True)
 
            col_sel_fin, col_btn_fin = st.columns([4, 1], vertical_alignment="bottom")
            fin_nome = col_sel_fin.selectbox(
                "Seleziona finanziamento da eliminare",
                df_fin_db["nome"].tolist(),
                format_func=lambda n: f"{n} | {format_eur(df_fin_db.loc[df_fin_db['nome']==n].iloc[0]['capitale_iniziale'], 0)}" if not df_fin_db[df_fin_db['nome']==n].empty else str(n),
                key="sel_del_fin",
            )
            if col_btn_fin.button("🗑️ Elimina", key="btn_del_fin", use_container_width=True):
                st.session_state["pending_delete_fin"] = fin_nome
 
            if st.session_state.get("pending_delete_fin") is not None:
                fnome = st.session_state["pending_delete_fin"]
                st.warning(f"⚠️ Elimina **{fnome}**? Operazione irreversibile.")
                cc1, cc2 = st.columns(2)
                if cc1.button("🗑️ Sì, elimina", key="confirm_del_fin", use_container_width=True, type="primary"):
                    db.elimina_finanziamento(fnome, user_email=user_email)
                    del st.session_state["pending_delete_fin"]
                    st.session_state["_success_fin_ts"] = datetime.now().timestamp()
                    st.rerun()
                if cc2.button("Annulla", key="cancel_del_fin", use_container_width=True):
                    del st.session_state["pending_delete_fin"]
                    st.rerun()
 
            if "_success_fin_ts" in st.session_state:
                if datetime.now().timestamp() - st.session_state["_success_fin_ts"] < 3:
                    st.success("✅ Finanziamento eliminato.")
                else:
                    del st.session_state["_success_fin_ts"]
 
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
 
    # ── Storico movimenti ──
    with st.container(border=True):
        st.markdown("""<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">
  <span style="font-size:13px;font-weight:700;color:#dde6f5;">📋 Storico Movimenti</span>
</div>""", unsafe_allow_html=True)

        # Filtri riga 1: tipo, categoria, anno
        col_ft, col_fc, col_fa = st.columns([1.2, 2, 1])
        filtro_tipo = col_ft.radio("Tipo", ["Tutti", "↑ Uscita", "↓ Entrata"], horizontal=True, key="reg_filtro_tipo")
        categorie_disp = sorted(df_mov["Categoria"].dropna().unique().tolist()) if not df_mov.empty else []
        filtro_cat  = col_fc.multiselect("Categoria", categorie_disp, key="reg_filtro_cat")
        _anni_disp  = ["Tutti"] + [str(a) for a in sorted(df_mov["Data"].dt.year.dropna().unique(), reverse=True)] if not df_mov.empty else ["Tutti"]
        # Anno default = anno selezionato nella sidebar (non "Tutti")
        _cur_anno_str = str(anno_sel)
        _anno_def_idx = _anni_disp.index(_cur_anno_str) if _cur_anno_str in _anni_disp else 0
        filtro_anno = col_fa.selectbox("Anno", _anni_disp, index=_anno_def_idx, key="reg_filtro_anno") if not df_mov.empty else "Tutti"

        # Filtro mese: mostra solo il mese corrente della sidebar, con checkbox per espandere
        _mese_label = MONTH_SHORT.get(mese_sel, str(mese_sel))
        mostra_tutti_mesi = st.checkbox(
            f"Mostra tutti i mesi (attualmente: {_mese_label} {anno_sel})",
            value=False, key="reg_mostra_tutti_mesi"
        )

        df_reg = df_mov.copy()
        if filtro_tipo != "Tutti":
            tipo_f = "USCITA" if "Uscita" in filtro_tipo else "ENTRATA"
            df_reg = df_reg[df_reg["Tipo"] == tipo_f]
        if filtro_cat:
            df_reg = df_reg[df_reg["Categoria"].isin(filtro_cat)]
        if filtro_anno != "Tutti":
            df_reg = df_reg[df_reg["Data"].dt.year == int(filtro_anno)]
        # Filtro mese: attivo di default, disattivabile con checkbox
        if not mostra_tutti_mesi:
            df_reg = df_reg[df_reg["Data"].dt.month == mese_sel]

        df_reg = df_reg.copy()
        df_reg.columns = [c.capitalize() for c in df_reg.columns]
        df_reg = df_reg.rename(columns={"Id": "Id"})
        if "Id" not in df_reg.columns and "id" in df_mov.columns:
            df_reg["Id"] = df_mov.loc[df_reg.index, "id"] if hasattr(df_mov, "loc") else df_reg.index

        totale_mov    = len(df_reg)
        mov_rows_html = []

        TIPO_COLOR    = {"ENTRATA": Colors.GREEN, "USCITA": Colors.RED}
        CAT_COLOR_MAP = {
            "NECESSITÀ": ("#4f8ef0", "rgba(79,142,240,0.10)", "rgba(79,142,240,0.28)"),
            "SVAGO":     ("#f472b6", "rgba(244,114,182,0.10)", "rgba(244,114,182,0.28)"),
            "INVESTIMENTI": ("#10d98a", "rgba(16,217,138,0.10)", "rgba(16,217,138,0.28)"),
            "ENTRATE":   ("#f5a623", "rgba(245,166,35,0.10)", "rgba(245,166,35,0.28)"),
        }

        def _label_mov(mid):
            rows = df_reg[df_reg.get("Id", pd.Series(dtype=int)) == mid] if "Id" in df_reg.columns else pd.DataFrame()
            if rows.empty:
                return str(mid)
            r = rows.iloc[0]
            return f"{str(r.get('Data',''))[:10]} | {r.get('Tipo','')} | {r.get('Categoria','')} | {format_eur(r.get('Importo',0), 2)}"

        for _, row in df_reg.iterrows():
            tipo_val_r = str(row.get("Tipo", "")).upper()
            cat_val    = str(row.get("Categoria", "")).upper()
            cc, cbg, cbd = CAT_COLOR_MAP.get(cat_val, ("#82b4f7", "rgba(79,142,240,0.10)", "rgba(79,142,240,0.28)"))
            data_str   = str(row.get("Data", ""))[:10]
            mov_rows_html.append(_tr([
                _td(str(row.get("Id", "")),         color=Colors.TEXT_MID, mono=True),
                _td(data_str,                       color=Colors.TEXT_MID, mono=True),
                _td(tipo_val_r,                     color=TIPO_COLOR.get(tipo_val_r, Colors.TEXT), weight=600),
                _td(chip_html(cat_val, cc, cbg, cbd), nowrap=True),
                _td(escape(str(row.get("Dettaglio", ""))), color=Colors.TEXT),
                _td(format_eur(row.get("Importo", 0), 2), color=Colors.RED if tipo_val_r == "USCITA" else Colors.GREEN, mono=True, weight=600),
                _td(escape(str(row.get("Note", ""))), color=Colors.TEXT_MID),
            ]))
 
        st.markdown(scroll_table(
            title="Storico movimenti", right_html=f"{totale_mov} righe",
            columns=[("ID","left"),("Data","left"),("Tipo","left"),("Categoria","left"),("Dettaglio","left"),("Importo","left"),("Note","left")],
            widths=[0.45, 0.9, 0.9, 1.0, 1.7, 0.95, 1.3],
            rows_html=mov_rows_html, height_px=420,
            empty_message="Nessun movimento trovato con i filtri selezionati.",
        ), unsafe_allow_html=True)
 
        if "Id" in df_reg.columns and not df_reg.empty:
            col_sel_mov, col_btn_mov = st.columns([4, 1], vertical_alignment="bottom")
            mov_id = col_sel_mov.selectbox("Seleziona movimento da eliminare",
                df_reg["Id"].tolist(), format_func=_label_mov, key="sel_del_mov")
            if col_btn_mov.button("🗑️ Elimina", key="btn_del_mov", use_container_width=True):
                st.session_state["pending_delete_mov"] = mov_id
 
        if st.session_state.get("pending_delete_mov") is not None:
            mid = st.session_state["pending_delete_mov"]
            st.warning(f"⚠️ Stai per eliminare il movimento **{_label_mov(mid)}**. Operazione irreversibile.")
            cc1, cc2 = st.columns(2)
            if cc1.button("🗑️ Sì, elimina", key="confirm_del_mov", use_container_width=True, type="primary"):
                db.elimina_movimento(mid, user_email)
                del st.session_state["pending_delete_mov"]
                st.session_state["_success_mov_ts"] = datetime.now().timestamp()
                st.rerun()
            if cc2.button("Annulla", key="cancel_del_mov", use_container_width=True):
                del st.session_state["pending_delete_mov"]
                st.rerun()
 
        if "_success_mov_ts" in st.session_state:
            if datetime.now().timestamp() - st.session_state["_success_mov_ts"] < 3:
                st.success("✅ Movimento eliminato con successo.")
            else:
                del st.session_state["_success_mov_ts"]
 
    # ── Backup ──
    with st.container(border=True):
        st.markdown("""<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
  <span style="font-size:20px;font-weight:500;color:#dde6f5;">🗄️ Backup Dati</span>
</div>""", unsafe_allow_html=True)
 
        @st.cache_data(ttl=300, show_spinner=False)
        def _genera_sql_backup(email: str) -> str | None:
            from backup import genera_sql_per_utente
            db_url = get_secret("DATABASE_URL") or get_secret("DATABASE_URL_POOLER")
            if not db_url:
                return None
            try:
                import psycopg2
                conn   = psycopg2.connect(db_url)
                cursor = conn.cursor()
                sql    = genera_sql_per_utente(cursor, email)
                cursor.close()
                conn.close()
                return sql
            except Exception:
                return None
 
        sql_backup = _genera_sql_backup(user_email)
        col_txt, col_btn = st.columns([3, 1], vertical_alignment="center")
        col_txt.markdown(
            "<div style='font-size:0.90rem;color:#5a6f8c;line-height:1.6;display:flex;align-items:center;height:100%;'>"
            "Scarica una <strong style='color:#dde6f5;font-weight:600;margin:0 4px;'>copia completa</strong> dei tuoi dati in formato SQL. "
            "Conservala in un posto sicuro — accessibile anche senza l'app."
            "</div>",
            unsafe_allow_html=True,
        )
        if sql_backup:
            col_btn.download_button(
                label="⬇ Scarica backup",
                data=sql_backup.encode("utf-8"),
                file_name=f"personal_budget_backup_{datetime.now().strftime('%Y-%m-%d')}.sql",
                mime="text/plain",
                use_container_width=True,
            )
        else:
            col_btn.caption("Backup non disponibile.")