###########################################################
##### Personal Budget Dashboard - Interfaccia utente ######

# streamlit run interfaccia.py

import time
import base64
import importlib
import json
import logging
import os
import re
import threading
import Database as db
import logiche as log 
from datetime import date, datetime, timedelta, timezone
from icon.icon import render_glow_icon
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from html import escape 
from config_runtime import (
    IS_CLOUD_RUN, default_base_url,
    export_runtime_env, load_google_oauth_credentials,
    get_secret, auth_access_mode,
)

@st.cache_resource
def _init_config():
    export_runtime_env()
    cid, csecret = load_google_oauth_credentials()
    base_url = default_base_url()
    return cid, csecret, base_url


GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, APP_BASE_URL = _init_config()
 
try:
    from streamlit_oauth import OAuth2Component, StreamlitOauthError
except Exception:
    OAuth2Component = None

    class StreamlitOauthError(Exception):
        pass

try:
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2.id_token import verify_oauth2_token
except Exception:
    GoogleAuthRequest = None
    verify_oauth2_token = None
 
# auth_manager: usa solo le funzioni pure (niente st.*)
from auth_manager import (
    create_session, validate_session, delete_session,
    login_email_password, login_google_user, register_user, get_display_name,
    is_onboarding_completed, get_auth_provider, mark_onboarding_completed,
    AuthError, AccessDeniedError, SESSION_TOKEN_COOKIE,
    request_password_reset, confirm_password_reset, delete_user_account,
    login_totp_step, setup_totp_begin, setup_totp_confirm,
    cancel_totp_login_challenge,
    request_totp_recovery, confirm_totp_recovery,
    disable_totp_for_user, disable_totp_for_google_user,
    is_totp_enabled, TwoFactorRequired,
)
 
from utils.styles import CSS_ALL
from utils.constants import (
    Colors, MONTH_NAMES, MONTH_SHORT, FREQ_OPTIONS, FREQ_MAP,
    STRUTTURA_CATEGORIE, PLOTLY_CONFIG,
)
from utils.formatters import format_eur, eur0, eur2, hex_to_rgba, badge_html, chip_html
from utils.user_settings import (
    get_struttura_categorie as _get_struttura_cat,
    aggiungi_dettaglio as _aggiungi_dettaglio,
    rimuovi_dettaglio as _rimuovi_dettaglio,
    get_percentuali_budget as _get_percentuali_budget,
    salva_percentuali_budget as _salva_percentuali_budget,
    ripristina_percentuali_default as _ripristina_percentuali_default,
    CATEGORIE_MODIFICABILI,
)
from utils.charts import style_fig
from utils.html_tables import (
    scroll_table, render_calendario_html, render_ricorrenti_rows,
    _td, _tr
)

logger = logging.getLogger(__name__)

AI_ALERTS_PAYLOAD_KEY = "ai_alerts_payload_json"
AI_ALERTS_STATUS_KEY = "ai_alerts_status"
AI_ALERTS_ERROR_KEY = "ai_alerts_error"
AI_ALERTS_UPDATED_AT_KEY = "ai_alerts_updated_at"
AI_ALERTS_LAST_ATTEMPT_AT_KEY = "ai_alerts_last_attempt_at"
AI_ALERTS_REFRESH_STARTED_AT_KEY = "ai_alerts_refresh_started_at"
AI_ALERTS_DIRTY_KEY = "ai_alerts_dirty"
AI_ALERTS_SETTING_KEYS = (
    AI_ALERTS_PAYLOAD_KEY,
    AI_ALERTS_STATUS_KEY,
    AI_ALERTS_ERROR_KEY,
    AI_ALERTS_UPDATED_AT_KEY,
    AI_ALERTS_LAST_ATTEMPT_AT_KEY,
    AI_ALERTS_REFRESH_STARTED_AT_KEY,
    AI_ALERTS_DIRTY_KEY,
)
AI_ALERTS_REFRESH_MAX_AGE = timedelta(hours=12)
AI_ALERTS_RETRY_COOLDOWN = timedelta(minutes=5)
AI_ALERTS_REFRESH_LOCK_TTL = timedelta(minutes=10)


@st.cache_resource
def _get_ai_alert_refresh_registry():
    return {"lock": threading.Lock(), "threads": {}}
 
# ---------------------------------------------------------------------------
# Demo config
# ---------------------------------------------------------------------------
DEMO_USER_EMAIL = get_secret("DEMO_USER_EMAIL")
DEMO_USER_PASSWORD = get_secret("DEMO_USER_PASSWORD")
DEMO_USER_EMAIL_NORM = str(DEMO_USER_EMAIL or "").strip().lower() if DEMO_USER_EMAIL else None
 
AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_OAUTH_ICON = (
    "data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' "
    "xmlns:xlink='http://www.w3.org/1999/xlink' viewBox='0 0 48 48'%3E%3Cdefs%3E"
    "%3Cpath id='a' d='M44.5 20H24v8.5h11.8C34.7 33.9 30.1 37 24 37c-7.2 0-13-5.8-13-13s5.8-13 "
    "13-13c3.1 0 5.9 1.1 8.1 2.9l6.4-6.4C34.6 4.1 29.6 2 24 2 11.8 2 2 11.8 2 24s9.8 22 22 22"
    "c11 0 21-8 21-22 0-1.3-.2-2.7-.5-4z'/%3E%3C/defs%3E%3CclipPath id='b'%3E%3Cuse "
    "xlink:href='%23a' overflow='visible'/%3E%3C/clipPath%3E%3Cpath clip-path='url(%23b)' "
    "fill='%23FBBC05' d='M0 37V11l17 13z'/%3E%3Cpath clip-path='url(%23b)' fill='%23EA4335' "
    "d='M0 11l17 13 7-6.1L48 14V0H0z'/%3E%3Cpath clip-path='url(%23b)' fill='%2334A853' "
    "d='M0 37l30-23 7.9 1L48 0v48H0z'/%3E%3Cpath clip-path='url(%23b)' fill='%234285F4' "
    "d='M48 48L17 24l-4-3 35-10z'/%3E%3C/svg%3E"
)
 
# ---------------------------------------------------------------------------
# Configurazione pagina (deve essere prima di qualsiasi st.*)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Personal Budget Dashboard", 
    layout="wide", 
    page_icon="icon/icona_barra.png",
    initial_sidebar_state="collapsed" 
)


# Nasconde la navigazione automatica della cartella pages/ dalla sidebar Streamlit.
# Questa app usa tab interni — la multi-page nav di Streamlit non è desiderata.
st.markdown(
    "<style>[data-testid='stSidebarNav']{display:none!important;}</style>",
    unsafe_allow_html=True,
)
# Il CSS globale va reiniettato a ogni rerun: il DOM di Streamlit viene ricostruito,
# mentre session_state sopravvive e non può essere usato per "saltare" questo render.
st.markdown(f"<style>{CSS_ALL}</style>", unsafe_allow_html=True)

APP_FOOTER_HTML = (
    "<div style='width:100%;margin:40px 0 10px;padding-top:16px;"
    "border-top:1px solid rgba(255,255,255,0.08);text-align:center;"
    "font-size:0.78rem;letter-spacing:0.02em;color:rgba(220,200,255,0.55);'>"
    "Copyright &copy; 2026 Luigi Pedace - DigitalSheets_LP. All rights reserved."
    "</div>"
)


def _render_app_footer() -> None:
    st.markdown(APP_FOOTER_HTML, unsafe_allow_html=True)


def _focus_streamlit_tab(label: str) -> None:
    """Best effort: riporta il focus su un tab Streamlit specifico dopo un rerun."""
    target = json.dumps(str(label or "").strip())
    st.components.v1.html(
        f"""
        <script>
        (function() {{
          const target = {target};
          let attempts = 0;
          function selectTab() {{
            const doc = window.parent.document;
            const tabs = Array.from(doc.querySelectorAll('[data-baseweb="tab"]'));
            const match = tabs.find((tab) => ((tab.innerText || '')).trim() === target);
            if (match) {{
              match.click();
              return;
            }}
            attempts += 1;
            if (attempts < 25) {{
              window.setTimeout(selectTab, 120);
            }}
          }}
          window.setTimeout(selectTab, 0);
        }})();
        </script>
        """,
        height=0,
    )
 
# ---------------------------------------------------------------------------
# Helpers cookie/session (layer Streamlit — responsabilità di questo file)
# ---------------------------------------------------------------------------
 
def _get_cookie_manager():
    try:
        module = importlib.import_module("extra_streamlit_components")
        return module.CookieManager(key="pb_cookie_manager")
    except Exception:
        return None


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
 
    mgr = _get_cookie_manager()
    if mgr is not None:
        try:
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
 
    mgr = _get_cookie_manager()
    if mgr is not None:
        try:
            kwargs: dict = {"key": f"cookie_set_{name}", "same_site": "lax", "path": "/"}
            if expires_at:
                kwargs["expires_at"] = expires_at
            mgr.set(name, value, secure=is_https, **kwargs)
            return
        except Exception:
            pass
 
    max_age = ""
    if expires_at:
        from datetime import timezone

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
    is_https = False
    try:
        headers = getattr(st.context, "headers", None) or {}
        is_https = str(headers.get("x-forwarded-proto", "")).lower() == "https"
    except Exception:
        pass

    mgr = _get_cookie_manager()
    if mgr is not None:
        try:
            mgr.delete(name, key=f"cookie_del_{name}")
        except Exception:
            pass

    secure = "secure;" if is_https else ""
    st.components.v1.html(
        (
            f"<script>"
            f"document.cookie='{name}=;expires=Thu, 01 Jan 1970 00:00:00 GMT;"
            f"max-age=0;SameSite=Lax;path=/;{secure}';"
            f"</script>"
        ),
        height=0,
    )


_GOOGLE_OAUTH_KEYS = (
    "google_login_hidden",
    "google_delete_confirm",
    "google_totp_disable_confirm",
)


def _clear_query_params() -> None:
    try:
        st.query_params.clear()
    except Exception:
        pass


def _has_google_oauth_callback_params() -> bool:
    try:
        for key in ("code", "state", "error", "error_description"):
            value = st.query_params.get(key)
            if isinstance(value, list):
                value = value[0] if value else None
            if value:
                return True
    except Exception:
        return False
    return False


def _reset_google_oauth_state(*keys: str) -> None:
    for key in keys:
        if not key:
            continue
        st.session_state.pop(f"state-{key}", None)
        st.session_state.pop(f"pkce-{key}", None)


def _safe_google_authorize_button(
    oauth2_component,
    *,
    name: str,
    scope: str,
    redirect_uri: str,
    key: str,
    icon: str | None = None,
    auto_click: bool = False,
    use_container_width: bool = True,
    extras_params: dict | None = None,
):
    extras_params = extras_params or {}
    try:
        return oauth2_component.authorize_button(
            name=name,
            scope=scope,
            redirect_uri=redirect_uri,
            key=key,
            icon=icon,
            auto_click=auto_click,
            use_container_width=use_container_width,
            extras_params=extras_params,
        )
    except StreamlitOauthError as exc:
        _reset_google_oauth_state(key)
        _clear_query_params()
        logger.warning("OAuth Google reset (%s): %s", key, exc)
        st.warning("La sessione Google e' scaduta o non e' piu' valida. Riprova.")
        return None


def _clear_pending_totp_state(discard_server_challenge: bool = False) -> None:
    """Pulisce lo stato locale del secondo step TOTP e, opzionalmente, la challenge server-side."""
    challenge_token = str(st.session_state.get("pending_2fa_challenge", "") or "").strip()
    if discard_server_challenge and challenge_token:
        cancel_totp_login_challenge(challenge_token)
    for key in (
        "pending_2fa_email", "pending_2fa_provider", "pending_2fa_challenge",
        "totp_login_code", "totp_recovery_step", "totp_recovery_otp",
    ):
        st.session_state.pop(key, None)


def _current_user_agent() -> str | None:
    """Restituisce lo user-agent della richiesta corrente se disponibile."""
    try:
        headers = getattr(st.context, "headers", None) or {}
        value = headers.get("user-agent") or headers.get("User-Agent")
        return str(value).strip() or None
    except Exception:
        return None


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
    email = validate_session(token, user_agent=_current_user_agent())
    if email:
        st.session_state["session_token"] = token
        st.session_state["auth_user_email"] = email
        st.session_state.setdefault("session_auth_provider", get_auth_provider(email))
        st.session_state["_auth_cache_token"] = token
        st.session_state["_auth_cache_user"] = email
        st.session_state["_auth_cache_checked_at"] = datetime.now().timestamp()
    else:
        for k in ["session_token", "auth_user_email", "_auth_cache_token",
                  "_auth_cache_user", "_auth_cache_checked_at",
                  "session_auth_provider", "_force_onboarding_email"]:
            st.session_state.pop(k, None)
        _clear_pending_totp_state(discard_server_challenge=True)
        _reset_google_oauth_state(*_GOOGLE_OAUTH_KEYS)
        if not _has_google_oauth_callback_params():
            _clear_query_params()
        _delete_cookie(SESSION_TOKEN_COOKIE)
    return email
 
 
def _finalize_login(email: str, token: str, expiry: datetime, provider: str = "password") -> None:
    """Salva il login già autenticato in session_state + cookie."""
    st.session_state["session_token"] = token
    st.session_state["auth_user_email"] = email
    st.session_state["session_auth_provider"] = str(provider or "password").strip().lower()
    _set_cookie(SESSION_TOKEN_COOKIE, token, expires_at=expiry)


def _do_login(email: str) -> bool:
    """Crea sessione e salva token in session_state + cookie."""
    try:
        token, expiry = create_session(email, user_agent=_current_user_agent())
    except AuthError as exc:
        st.error(str(exc))
        return False
    _finalize_login(email, token, expiry)
    return True
 
 
def _do_logout() -> None:
    token = st.session_state.get("session_token") or _read_cookie(SESSION_TOKEN_COOKIE)
    if token:
        delete_session(token)
    for k in ["session_token", "auth_user_email", "_auth_cache_token",
              "_auth_cache_user", "_auth_cache_checked_at", "is_demo_guest",
              "session_auth_provider",
              "_force_onboarding_email",
              "totp_setup_active", "totp_setup_secret", "totp_setup_uri",
              "totp_confirm_input", "totp_disable_pwd", "_totp_recovery_success"]:
        st.session_state.pop(k, None)
    _clear_pending_totp_state(discard_server_challenge=True)
    _reset_google_oauth_state(*_GOOGLE_OAUTH_KEYS)
    _clear_query_params()
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
 
 
def _decode_id_token_claims(id_token) -> dict | None:
    if not id_token:
        return None
    if verify_oauth2_token is None or GoogleAuthRequest is None:
        return None
    try:
        if isinstance(id_token, (bytes, bytearray)):
            token_raw = id_token.decode("utf-8").strip()
        elif isinstance(id_token, str):
            token_raw = id_token.strip()
        else:
            return None
        if not token_raw or "." not in token_raw:
            return None
        claims = verify_oauth2_token(token_raw, GoogleAuthRequest(), GOOGLE_CLIENT_ID or None)
        issuer = str(claims.get("iss", "")).strip()
        if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
            logger.warning("ID token Google con issuer non valido: %s", issuer)
            return None
        if claims.get("email_verified") is False:
            logger.warning("ID token Google con email non verificata.")
            return None
        return claims
    except Exception as exc:
        logger.warning("Verifica ID token Google fallita: %s", exc)
        return None


def _decode_id_token_email(id_token) -> str | None:
    claims = _decode_id_token_claims(id_token) or {}
    email = claims.get("email")
    return str(email).strip().lower() if email else None


def _render_totp_login_step() -> None:
    """Mostra il form di verifica TOTP (secondo step del login)."""
    pending_email = str(st.session_state.get("pending_2fa_email", "") or "").strip().lower()
    pending_provider = str(st.session_state.get("pending_2fa_provider", "password") or "password").strip().lower()
    pending_challenge = str(st.session_state.get("pending_2fa_challenge", "") or "").strip()
    recovery_step = str(st.session_state.get("totp_recovery_step", "") or "").strip().lower()
    if pending_provider not in {"password", "google"}:
        pending_provider = "password"
    if recovery_step not in {"request", "confirm"}:
        recovery_step = ""

    if not pending_email or not pending_challenge:
        _clear_pending_totp_state(discard_server_challenge=True)
        st.info("Sessione di verifica scaduta. Torna al login.")
        return

    provider_label = "Google" if pending_provider == "google" else "password"
    st.markdown(
        "<div style='text-align:center;margin:12px 0 10px;'>"
        "<div style='font-size:2.2rem;'>🔐</div>"
        "<div style='font-size:1.15rem;font-weight:700;color:#f8fbff;margin-top:6px;'>Verifica in due passaggi</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"Hai già superato il primo controllo di accesso via {provider_label}. "
        f"Inserisci il codice a 6 cifre dell'app Authenticator per completare l'accesso a **{pending_email}**."
    )

    if recovery_step == "request":
        st.warning(
            "Non hai più accesso all'app Authenticator? Possiamo inviarti via email un codice temporaneo "
            "per disattivare il 2FA attuale e completare l'accesso.",
            icon="📩",
        )
        st.caption(
            f"Il codice verrà inviato a **{pending_email}** ed è valido per **10 minuti**."
        )
        col_send, col_back = st.columns(2)
        if col_send.button("Invia codice via email", use_container_width=True, type="primary", key="btn_totp_recovery_send"):
            with st.spinner("Invio codice recovery in corso…"):
                ok, msg = request_totp_recovery(pending_email, pending_challenge, provider=pending_provider)
            if ok:
                st.session_state["totp_recovery_step"] = "confirm"
                st.rerun()
            st.error(msg)
        if col_back.button("← Torna al codice Authenticator", use_container_width=True, key="btn_totp_recovery_back_request"):
            st.session_state.pop("totp_recovery_step", None)
            st.session_state.pop("totp_recovery_otp", None)
            st.rerun()
        return

    if recovery_step == "confirm":
        st.warning(
            "Abbiamo inviato un codice temporaneo via email. Inseriscilo qui per disattivare il 2FA attuale.",
            icon="📩",
        )
        st.caption(
            f"Controlla la casella di posta di **{pending_email}**. "
            "Dopo il recovery dovrai configurare di nuovo il 2FA dalle impostazioni."
        )
        recovery_code = st.text_input(
            "Codice recovery via email",
            max_chars=6,
            placeholder="123456",
            key="totp_recovery_otp",
            label_visibility="collapsed",
        )
        col_confirm, col_back, col_resend = st.columns([1.2, 1, 1])
        if col_confirm.button("Conferma recovery", use_container_width=True, type="primary", key="btn_totp_recovery_confirm"):
            if not recovery_code or len(recovery_code) != 6 or not recovery_code.isdigit():
                st.error("Inserisci un codice valido a 6 cifre.")
            else:
                try:
                    email_norm, token, expiry = confirm_totp_recovery(
                        pending_email,
                        recovery_code,
                        pending_challenge,
                        provider=pending_provider,
                        user_agent=_current_user_agent(),
                    )
                    if not is_onboarding_completed(email_norm):
                        st.session_state["_force_onboarding_email"] = email_norm
                    st.session_state["_totp_recovery_success"] = True
                    _clear_pending_totp_state(discard_server_challenge=False)
                    _finalize_login(email_norm, token, expiry, provider=pending_provider)
                    st.rerun()
                except AuthError as e:
                    st.error(str(e))
        if col_back.button("← Indietro", use_container_width=True, key="btn_totp_recovery_back_confirm"):
            st.session_state["totp_recovery_step"] = "request"
            st.session_state.pop("totp_recovery_otp", None)
            st.rerun()
        if col_resend.button("Rinvia codice", use_container_width=True, key="btn_totp_recovery_resend"):
            with st.spinner("Nuovo codice recovery in invio…"):
                ok, msg = request_totp_recovery(pending_email, pending_challenge, provider=pending_provider)
            if ok:
                st.success("Nuovo codice inviato. Controlla la posta.")
            else:
                st.error(msg)
        return

    totp_code = st.text_input(
        "Codice TOTP",
        max_chars=6,
        placeholder="000000",
        key="totp_login_code",
        label_visibility="collapsed",
    )
    col_verify, col_back = st.columns(2)
    if col_verify.button("Verifica codice", use_container_width=True, type="primary", key="btn_totp_login"):
        if not totp_code or len(totp_code) != 6 or not totp_code.isdigit():
            st.error("Inserisci un codice valido a 6 cifre.")
        else:
            try:
                email_norm, token, expiry = login_totp_step(
                    pending_email,
                    totp_code,
                    pending_challenge,
                    user_agent=_current_user_agent(),
                )
                if not is_onboarding_completed(email_norm):
                    st.session_state["_force_onboarding_email"] = email_norm
                _clear_pending_totp_state(discard_server_challenge=False)
                _finalize_login(email_norm, token, expiry, provider=pending_provider)
                st.rerun()
            except AuthError as e:
                st.error(str(e))
    if col_back.button("← Torna al login", use_container_width=True, key="btn_totp_back"):
        _clear_pending_totp_state(discard_server_challenge=True)
        st.rerun()
    st.markdown("<div style='text-align:center;margin-top:10px;'>", unsafe_allow_html=True)
    if st.button("Ho perso lo smartphone", use_container_width=True, key="btn_totp_recovery_start"):
        st.session_state["totp_recovery_step"] = "request"
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
 
 
# ---------------------------------------------------------------------------
# Schermata di login
# ---------------------------------------------------------------------------
 
def _render_login_screen() -> None:
    mode = auth_access_mode()
    pilot_mode = (mode == "pilot_only")
 
    # Sidebar già nascosta via CSS_LOGIN (.login-aurora-bg :has rule)
 
    # ── Sfondo aurora + blob animati (iniettato fuori dalla colonna) ────────
    st.markdown("""
        <div class='login-aurora-bg'>
            <div class='login-orb login-orb-1'></div>
            <div class='login-orb login-orb-2'></div>
            <div class='login-orb login-orb-3'></div>
        </div>
    """, unsafe_allow_html=True)
 
    _, center, _ = st.columns([1, 1.4, 1])
    with center:
        st.markdown("<div class='login-glass-card'>", unsafe_allow_html=True)

        render_glow_icon("icon/icona_barra.png", width=100)
        
        st.markdown("""
            <div style='text-align: center; margin-bottom: 20px;'>
                <p class='login-logo-name'>Personal Budget</p>
                <p class='login-logo-tagline'>Gestione finanza personale</p>
            </div>
            <div class='login-status-badge'>
                <span class='login-status-dot'></span>Servizio attivo
            </div>
        """, unsafe_allow_html=True)
 
        # Titolo / sottotitolo
        st.markdown("<h2 class='login-heading'>Bentornato</h2>", unsafe_allow_html=True)
        st.markdown("<p class='login-subheading'>Accedi per esplorare la dashboard</p>", unsafe_allow_html=True)
 
        # ── CLOSED: nessun tab, nessuna azione ───────────────────────────────
        if mode == "closed":
            st.warning("Accesso disabilitato. Riprova quando il servizio sarà riattivato.")
            _render_app_footer()
            return
 
        user_flows_disabled = (mode == "demo_only")
        show_demo_tab = (mode in {"demo_only", "pilot_only"})
        if pilot_mode:
            st.info(
                "Modalità Beta test attiva: la demo resta pubblica, mentre accesso e registrazione reali "
                "sono riservati agli account autorizzati."
            )

        # ── COSTRUZIONE TAB: Demo appare in modalità demo_only e pilot_only ───
        tab_labels = ["🔑 Accedi", "📝 Registrati"]
        if show_demo_tab:
            tab_labels.append("🚀 Demo")
 
        tabs = st.tabs(tab_labels)
        tab_login    = tabs[0]
        tab_register = tabs[1]
        tab_demo     = tabs[2] if show_demo_tab else None
 
        # ── TAB ACCEDI ────────────────────────────────────────────────────────
        with tab_login:
            reset_step = st.session_state.get("_pwd_reset_step")
 
            # STEP 0: secondo step TOTP
            if st.session_state.get("pending_2fa_email"):
                _render_totp_login_step()

            # STEP 1: form di login normale
            elif reset_step is None:
                email_in = st.text_input("Email", key="login_email", disabled=user_flows_disabled)
                pwd_in   = st.text_input("Password", type="password", key="login_pwd", disabled=user_flows_disabled)
 
                if st.button("Accedi", use_container_width=True, key="btn_login", disabled=user_flows_disabled):
                    if email_in and pwd_in:
                        try:
                            email_norm, token, expiry = login_email_password(
                                email_in,
                                pwd_in,
                                user_agent=_current_user_agent(),
                            )
                            if not is_onboarding_completed(email_norm):
                                st.session_state["_force_onboarding_email"] = email_norm
                            _finalize_login(email_norm, token, expiry, provider="password")
                            st.rerun()
                        except TwoFactorRequired as e:
                            st.session_state["pending_2fa_email"] = e.email
                            st.session_state["pending_2fa_provider"] = "password"
                            st.session_state["pending_2fa_challenge"] = e.challenge_token
                            st.rerun()
                        except (AuthError, AccessDeniedError) as e:
                            st.error(str(e))
                    else:
                        st.warning("Inserisci email e password.")
 
                st.markdown("<div style='text-align:right; margin-top:4px;'>", unsafe_allow_html=True)
                if st.button(
                    "🔑 Password dimenticata?",
                    key="btn_forgot_pwd",
                    disabled=user_flows_disabled,
                    help="Riceverai un codice via email per reimpostare la password",
                ):
                    st.session_state["_pwd_reset_step"] = "request"
                    st.session_state.pop("_pwd_reset_email", None)
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)
 
                # ── GOOGLE OAUTH ────────────────────────────────────────────────
                st.divider()
                if OAuth2Component is None:
                    st.error("Modulo mancante: installa `streamlit-oauth`.")
                elif not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
                    st.error("Credenziali OAuth mancanti.")
                else:
                    if mode == "demo_only":
                        st.caption("Accesso Google disabilitato in modalità `demo_only`.")
                    oauth2 = OAuth2Component(
                        GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
                        AUTHORIZE_URL, TOKEN_URL, TOKEN_URL, ""
                    )
                    redirect_uri = _redirect_uri()
                    if not redirect_uri:
                        st.error("APP_BASE_URL non configurato.")
                    elif not user_flows_disabled:
                        st.markdown("<div class='pb-google-oauth-anchor'></div>", unsafe_allow_html=True)
                        result = _safe_google_authorize_button(
                            oauth2,
                            name="Accedi con Google",
                            scope="openid email profile",
                            redirect_uri=redirect_uri,
                            key="google_login_hidden",
                            icon=GOOGLE_OAUTH_ICON,
                            use_container_width=True,
                            extras_params={"prompt": "select_account"},
                        )
                        if result:
                            id_token = result.get("id_token")
                            if not id_token and isinstance(result.get("token"), dict):
                                id_token = result["token"].get("id_token")
                            claims_google = _decode_id_token_claims(id_token) or {}
                            email_google = _decode_id_token_email(id_token)
                            nome_google = str(
                                claims_google.get("name")
                                or claims_google.get("given_name")
                                or ""
                            ).strip()
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
                                            nome_google = str(
                                                payload.get("name")
                                                or payload.get("given_name")
                                                or nome_google
                                            ).strip()
                                    except Exception:
                                        pass
                            if email_google:
                                try:
                                    email_norm, token, expiry = login_google_user(
                                        email_google,
                                        nome_google,
                                        user_agent=_current_user_agent(),
                                    )
                                    if not is_onboarding_completed(email_norm):
                                        st.session_state["_force_onboarding_email"] = email_norm
                                    _finalize_login(email_norm, token, expiry, provider="google")
                                    _reset_google_oauth_state("google_login_hidden")
                                    _clear_query_params()
                                    st.success("Accesso autorizzato.")
                                    st.rerun()
                                except TwoFactorRequired as e:
                                    st.session_state["pending_2fa_email"] = e.email
                                    st.session_state["pending_2fa_provider"] = "google"
                                    st.session_state["pending_2fa_challenge"] = e.challenge_token
                                    _reset_google_oauth_state("google_login_hidden")
                                    _clear_query_params()
                                    st.rerun()
                                except (AuthError, AccessDeniedError) as e:
                                    st.error(str(e))
                            if not email_google:
                                st.error("Impossibile leggere l'email dal profilo Google.")
 
            # STEP 1: inserisci email per reset
            elif reset_step == "request":
                st.markdown(
                    "<p style='color:#5a8dee;font-weight:600;margin-bottom:6px;'>"
                    "🔐 Reimposta la tua password</p>",
                    unsafe_allow_html=True,
                )
                st.caption(
                    "Inserisci l'email del tuo account. "
                    "Se è registrata, riceverai un codice a 6 cifre valido per 15 minuti."
                )
                reset_email = st.text_input(
                    "Email account", key="reset_email_input",
                    placeholder="es. mario@example.com", disabled=user_flows_disabled,
                )
                col_send, col_back = st.columns([3, 1])
                if col_send.button("📨 Invia codice", use_container_width=True, key="btn_send_otp", disabled=user_flows_disabled):
                    if not reset_email:
                        st.warning("Inserisci l'email.")
                    else:
                        with st.spinner("Invio codice in corso…"):
                            ok, msg = request_password_reset(reset_email)
                        if ok:
                            st.session_state["_pwd_reset_email"] = reset_email.strip().lower()
                            st.session_state["_pwd_reset_step"]  = "confirm"
                            st.rerun()
                        else:
                            st.error(msg)
                if col_back.button("← Indietro", key="btn_reset_back1", use_container_width=True):
                    st.session_state.pop("_pwd_reset_step", None)
                    st.session_state.pop("_pwd_reset_email", None)
                    st.rerun()
 
            # STEP 2: inserisci OTP + nuova password
            elif reset_step == "confirm":
                saved_email = st.session_state.get("_pwd_reset_email", "")
                st.markdown(
                    "<p style='color:#5a8dee;font-weight:600;margin-bottom:6px;'>"
                    "🔐 Reimposta la tua password</p>",
                    unsafe_allow_html=True,
                )
                st.caption(
                    f"Abbiamo inviato un codice a **{saved_email}**. "
                    "Controlla anche la cartella spam. Il codice scade in **15 minuti**."
                )
                otp_in   = st.text_input("Codice ricevuto via email (6 cifre)", key="reset_otp_input", max_chars=6, placeholder="123456", disabled=user_flows_disabled)
                pwd_new  = st.text_input("Nuova password",         type="password", key="reset_new_pwd",  disabled=user_flows_disabled)
                pwd_new2 = st.text_input("Conferma nuova password",type="password", key="reset_new_pwd2", disabled=user_flows_disabled)
                col_confirm, col_back2 = st.columns([3, 1])
                if col_confirm.button("✅ Conferma nuova password", use_container_width=True, key="btn_confirm_reset", type="primary", disabled=user_flows_disabled):
                    if not otp_in or not pwd_new or not pwd_new2:
                        st.warning("Compila tutti i campi.")
                    elif pwd_new != pwd_new2:
                        st.error("Le password non coincidono.")
                    else:
                        with st.spinner("Aggiornamento in corso…"):
                            ok, msg = confirm_password_reset(saved_email, otp_in, pwd_new)
                        if ok:
                            st.session_state["_pwd_reset_step"] = "done"
                            st.rerun()
                        else:
                            st.error(msg)
                if col_back2.button("← Indietro", key="btn_reset_back2", use_container_width=True):
                    st.session_state["_pwd_reset_step"] = "request"
                    st.rerun()
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("📨 Non ho ricevuto il codice — Rinvia", key="btn_resend_otp", disabled=user_flows_disabled):
                    with st.spinner("Nuovo codice in invio…"):
                        ok, msg = request_password_reset(saved_email)
                    if ok:
                        st.success("Nuovo codice inviato! Controlla la posta.")
                    else:
                        st.error(msg)
 
            # STEP 3: successo
            elif reset_step == "done":
                st.success("✅ Password aggiornata con successo!")
                st.caption("Hai ricevuto una email di conferma. Ora puoi accedere con la tua nuova password.")
                if st.button("🔑 Torna al login", use_container_width=True, key="btn_back_to_login"):
                    for k in ("_pwd_reset_step", "_pwd_reset_email"):
                        st.session_state.pop(k, None)
                    st.rerun()
 
        # ── TAB REGISTRATI ────────────────────────────────────────────────────
        with tab_register:
            if user_flows_disabled:
                st.info("Registrazione temporaneamente disattivata. Usa la tab Demo.")
            elif pilot_mode:
                st.info(
                    "Registrazione riservata agli indirizzi invitati per questa fase di test."
                )
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
                        email_norm = str(email_reg).strip().lower()
                        st.session_state["_force_onboarding_email"] = email_norm
                        if _do_login(email_norm):
                            st.success("Registrazione completata. Completa ora la configurazione iniziale.")
                            st.rerun()
                        st.success("Registrazione completata! Ora accedi dalla tab 'Accedi'.")
                    except AuthError as exc:
                        st.error(str(exc))
 
        # ── TAB DEMO (solo se demo_only) ──────────────────────────────────────
        if tab_demo is not None:
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
 
        # ── Chiude il div login-glass-card ──────────────────────────────
        st.markdown("</div>", unsafe_allow_html=True)

    _render_app_footer()
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


@st.cache_data(show_spinner=False)
def _load_movimenti_df(user_email_param: str) -> pd.DataFrame:
    return db.carica_dati(user_email_param)


@st.cache_data(show_spinner=False)
def _load_finanziamenti_df(user_email_param: str) -> pd.DataFrame:
    return db.carica_finanziamenti(user_email_param)


@st.cache_data(show_spinner=False)
def _load_spese_ricorrenti_df(user_email_param: str) -> pd.DataFrame:
    return db.carica_spese_ricorrenti(user_email_param)


@st.cache_data(show_spinner=False)
def _load_obiettivi_df(user_email_param: str, solo_attivi: bool = True) -> pd.DataFrame:
    return db.carica_obiettivi(user_email_param, solo_attivi=solo_attivi)


@st.cache_data(show_spinner=False)
def _get_percentuali_budget_cached(user_email_param: str) -> dict:
    return _get_percentuali_budget(user_email_param)


@st.cache_data(show_spinner=False)
def _get_struttura_categorie_cached(user_email_param: str) -> dict:
    return _get_struttura_cat(user_email_param)


def _invalidate_runtime_caches(
    *,
    movimenti: bool = False,
    finanziamenti: bool = False,
    ricorrenti: bool = False,
    obiettivi: bool = False,
    settings: bool = False,
    user_settings: bool = False,
) -> None:
    if movimenti:
        _load_movimenti_df.clear()
    if finanziamenti:
        _load_finanziamenti_df.clear()
    if ricorrenti:
        _load_spese_ricorrenti_df.clear()
    if obiettivi:
        _load_obiettivi_df.clear()
    if settings:
        _load_settings_df.clear()
    if user_settings:
        _get_percentuali_budget_cached.clear()
        _get_struttura_categorie_cached.clear()
    if movimenti or finanziamenti or ricorrenti:
        _get_anomalie_cached.clear()
        mark_ai_dirty = globals().get("_mark_ai_alerts_dirty_for_current_user")
        if callable(mark_ai_dirty):
            try:
                mark_ai_dirty()
            except Exception:
                pass
    if movimenti or finanziamenti or ricorrenti or obiettivi:
        st.session_state.pop("_cal_cache", None)


def _compute_goal_metrics(
    costo: float,
    accantonato_reale: float,
    risparmio_mensile_dedicato: float,
    scadenza,
    *,
    today: date | None = None,
) -> dict:
    """Calcola stato reale e proiezione futura di un obiettivo finanziario."""
    today = today or date.today()
    costo_v = max(0.0, float(costo or 0.0))
    accantonato_v = max(0.0, float(accantonato_reale or 0.0))
    dedicato_v = max(0.0, float(risparmio_mensile_dedicato or 0.0))

    scadenza_date = None
    if scadenza is not None and pd.notna(scadenza):
        try:
            scadenza_date = pd.to_datetime(scadenza).date()
        except Exception:
            scadenza_date = None

    if scadenza_date is not None:
        mesi_rimanenti = max(
            0,
            (scadenza_date.year - today.year) * 12 + (scadenza_date.month - today.month),
        )
        giorni_rimanenti = (scadenza_date - today).days
        versamenti_previsti = dedicato_v * mesi_rimanenti
        scadenza_label = scadenza_date.strftime("%b %Y")
    else:
        mesi_rimanenti = None
        giorni_rimanenti = None
        versamenti_previsti = 0.0
        scadenza_label = "Nessuna scadenza"

    totale_previsto = accantonato_v + versamenti_previsti
    gap_attuale = max(0.0, costo_v - accantonato_v)
    gap_previsto = max(0.0, costo_v - totale_previsto)
    perc_reale = min(100.0, (accantonato_v / costo_v * 100) if costo_v > 0 else 0.0)
    perc_previsto = min(100.0, (totale_previsto / costo_v * 100) if costo_v > 0 else 0.0)

    coperto_oggi = costo_v > 0 and accantonato_v >= costo_v
    coperto_previsto = costo_v > 0 and totale_previsto >= costo_v

    if coperto_oggi:
        stato = "COPERTO"
    elif mesi_rimanenti is None:
        stato = "SENZA_SCADENZA"
    elif coperto_previsto:
        stato = "IN_LINEA"
    else:
        stato = "INSUFFICIENTE"

    return {
        "costo": costo_v,
        "accantonato_reale": accantonato_v,
        "dedicato_mensile": dedicato_v,
        "scadenza_date": scadenza_date,
        "scadenza_label": scadenza_label,
        "mesi_rimanenti": mesi_rimanenti,
        "giorni_rimanenti": giorni_rimanenti,
        "versamenti_previsti": round(versamenti_previsti, 2),
        "totale_previsto": round(totale_previsto, 2),
        "gap_attuale": round(gap_attuale, 2),
        "gap_previsto": round(gap_previsto, 2),
        "perc_reale": round(perc_reale, 2),
        "perc_previsto": round(perc_previsto, 2),
        "coperto_oggi": coperto_oggi,
        "coperto_previsto": coperto_previsto,
        "stato": stato,
    }


@st.cache_data(ttl=10800, show_spinner=False)
def _get_anomalie_cached(user_email_param: str) -> list[dict]:
    import ai_engine

    try:
        return ai_engine.detect_anomalies(
            df_mov=_load_movimenti_df(user_email_param),
            df_ric=_load_spese_ricorrenti_df(user_email_param),
            df_fin=_load_finanziamenti_df(user_email_param),
        )
    except Exception:
        return []


@st.cache_data(ttl=1800, show_spinner=False)
def _get_ai_health_cached() -> dict:
    import ai_engine

    try:
        return ai_engine.diagnose_gemini()
    except Exception as exc:
        return {
            "configured": False,
            "reachable": False,
            "model": "",
            "message": f"Diagnostica Gemini non disponibile: {exc}",
            "sample_response": "",
        }
 
# ---------------------------------------------------------------------------
# Auth check
# ---------------------------------------------------------------------------
 
AUTH_USER_EMAIL = _get_session_user()
if not AUTH_USER_EMAIL:
    _render_login_screen()
 
user_email = AUTH_USER_EMAIL
 
# Banner demo
is_demo_account = False
if DEMO_USER_EMAIL_NORM:
    is_demo_account = str(AUTH_USER_EMAIL).strip().lower() == DEMO_USER_EMAIL_NORM
    st.session_state["is_demo_guest"] = is_demo_account
    if is_demo_account:
        st.info("👁️ **Modalità Demo** — Stai esplorando l'app con dati di esempio.", icon="ℹ️")
 
NOME_DISPLAY = get_display_name(AUTH_USER_EMAIL, is_demo_account=is_demo_account)
auth_provider = str(
    st.session_state.get("session_auth_provider")
    or get_auth_provider(AUTH_USER_EMAIL)
    or "password"
).strip().lower()
if auth_provider not in {"password", "google"}:
    auth_provider = "password"
_forced_onboarding_email = str(st.session_state.get("_force_onboarding_email", "") or "").strip().lower()
onboarding_required = (not is_demo_account) and (
    _forced_onboarding_email == str(AUTH_USER_EMAIL).strip().lower()
    or (not is_onboarding_completed(AUTH_USER_EMAIL))
)
 
# ---------------------------------------------------------------------------
# Caricamento dati
# ---------------------------------------------------------------------------

df_mov = _load_movimenti_df(user_email).copy()
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
 
if df_mov.empty and not onboarding_required:
    st.warning("Nessun dato inserito. Usa il tab 'impostazioni rapide' per settare i tuoi dati e 'Registro' per iniziare a tracciare i tuoi movimenti.")
 
df_fin_db = _load_finanziamenti_df(user_email).copy()
 
# ---------------------------------------------------------------------------
# Helpers settings (asset_settings)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _load_settings_df(user_email_param: str) -> pd.DataFrame:
    try:
        with db.connetti_db() as conn:
            df = pd.read_sql(
                "SELECT chiave, valore_numerico, valore_testo "
                "FROM asset_settings WHERE user_email = %s",
                conn,
                params=(user_email_param,),
            )
        if df.empty:
            return pd.DataFrame(columns=["valore_numerico", "valore_testo"]).set_index(pd.Index([]))
        df = df.drop_duplicates(subset=["chiave"], keep="last")
        return df.set_index("chiave")
    except Exception:
        return pd.DataFrame(columns=["valore_numerico", "valore_testo"]).set_index(pd.Index([]))
 
 
def _save_settings_batch_for_user(
    user_email_param: str,
    num_payload: dict | None = None,
    txt_payload: dict | None = None,
    *,
    invalidate_cache: bool = True,
) -> tuple[bool, str]:
    num_payload = num_payload or {}
    txt_payload = txt_payload or {}
    if not user_email_param:
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
                    cur.execute(upsert_q, (str(key), user_email_param, float(value) if value is not None else None, None))
                for key, value in txt_payload.items():
                    cur.execute(upsert_q, (str(key), user_email_param, None, str(value) if value is not None else ""))
        if invalidate_cache:
            _invalidate_runtime_caches(settings=True)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _save_settings_batch(num_payload: dict = None, txt_payload: dict = None) -> tuple[bool, str]:
    return _save_settings_batch_for_user(user_email, num_payload, txt_payload)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _dt_to_storage(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_storage_dt(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _format_snapshot_ts(value: datetime | None) -> str:
    if value is None:
        return ""
    try:
        local_value = value.astimezone()
        return local_value.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return ""


def _load_text_settings_for_user(user_email_param: str, keys: tuple[str, ...]) -> dict[str, str]:
    if not user_email_param or not keys:
        return {}
    try:
        wanted = {str(key) for key in keys}
        with db.connetti_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT chiave, valore_testo "
                    "FROM asset_settings "
                    "WHERE user_email = %s",
                    (user_email_param,),
                )
                rows = cur.fetchall()
        return {
            str(row[0]): "" if row[1] is None else str(row[1])
            for row in rows
            if str(row[0]) in wanted
        }
    except Exception:
        return {}


def _load_ai_alerts_snapshot(user_email_param: str) -> dict:
    raw = _load_text_settings_for_user(user_email_param, AI_ALERTS_SETTING_KEYS)
    payload_raw = raw.get(AI_ALERTS_PAYLOAD_KEY, "")
    payload: list[dict] = []
    if payload_raw.strip():
        try:
            parsed = json.loads(payload_raw)
            if isinstance(parsed, list):
                payload = parsed
        except Exception:
            payload = []
    status = str(raw.get(AI_ALERTS_STATUS_KEY, "") or "idle").strip().lower() or "idle"
    if status not in {"idle", "refreshing", "ready", "error"}:
        status = "idle"
    return {
        "payload": payload,
        "has_result": AI_ALERTS_PAYLOAD_KEY in raw,
        "status": status,
        "error": str(raw.get(AI_ALERTS_ERROR_KEY, "") or "").strip(),
        "updated_at": _parse_storage_dt(raw.get(AI_ALERTS_UPDATED_AT_KEY)),
        "last_attempt_at": _parse_storage_dt(raw.get(AI_ALERTS_LAST_ATTEMPT_AT_KEY)),
        "refresh_started_at": _parse_storage_dt(raw.get(AI_ALERTS_REFRESH_STARTED_AT_KEY)),
        "dirty": str(raw.get(AI_ALERTS_DIRTY_KEY, "") or "").strip() == "1",
    }


def _save_ai_alerts_state(user_email_param: str, txt_payload: dict[str, str]) -> None:
    _save_settings_batch_for_user(
        user_email_param,
        {},
        txt_payload,
        invalidate_cache=False,
    )


def _mark_ai_alerts_dirty_for_user(user_email_param: str) -> None:
    if not user_email_param:
        return
    _save_ai_alerts_state(
        user_email_param,
        {
            AI_ALERTS_DIRTY_KEY: "1",
        },
    )


def _mark_ai_alerts_dirty_for_current_user() -> None:
    if user_email:
        _mark_ai_alerts_dirty_for_user(user_email)


def _should_refresh_ai_alerts(snapshot: dict, *, has_source_data: bool) -> bool:
    now = _utc_now()
    if not has_source_data:
        return False
    if snapshot.get("status") == "refreshing":
        started_at = snapshot.get("refresh_started_at")
        if started_at and (now - started_at) < AI_ALERTS_REFRESH_LOCK_TTL:
            return False
    if snapshot.get("dirty"):
        return True
    if not snapshot.get("has_result"):
        last_attempt_at = snapshot.get("last_attempt_at")
        return last_attempt_at is None or (now - last_attempt_at) >= AI_ALERTS_RETRY_COOLDOWN
    if snapshot.get("status") == "error":
        last_attempt_at = snapshot.get("last_attempt_at")
        return last_attempt_at is None or (now - last_attempt_at) >= AI_ALERTS_RETRY_COOLDOWN
    updated_at = snapshot.get("updated_at")
    return updated_at is None or (now - updated_at) >= AI_ALERTS_REFRESH_MAX_AGE


def _ai_alerts_refresh_worker(user_email_param: str) -> None:
    registry = _get_ai_alert_refresh_registry()
    refresh_started_at = _utc_now()
    try:
        import ai_engine

        df_mov_worker = db.carica_dati(user_email_param)
        if df_mov_worker is None or df_mov_worker.empty:
            current_snapshot = _load_ai_alerts_snapshot(user_email_param)
            dirty_value = "1" if current_snapshot.get("dirty") else "0"
            ts = _dt_to_storage(_utc_now())
            _save_ai_alerts_state(
                user_email_param,
                {
                    AI_ALERTS_PAYLOAD_KEY: "[]",
                    AI_ALERTS_STATUS_KEY: "ready",
                    AI_ALERTS_ERROR_KEY: "",
                    AI_ALERTS_UPDATED_AT_KEY: ts,
                    AI_ALERTS_LAST_ATTEMPT_AT_KEY: ts,
                    AI_ALERTS_REFRESH_STARTED_AT_KEY: "",
                    AI_ALERTS_DIRTY_KEY: dirty_value,
                },
            )
            return

        df_ric_worker = db.carica_spese_ricorrenti(user_email_param)
        df_fin_worker = db.carica_finanziamenti(user_email_param)

        anomalies = ai_engine.detect_anomalies(
            df_mov=df_mov_worker,
            df_ric=df_ric_worker,
            df_fin=df_fin_worker,
        )

        if not anomalies:
            health = ai_engine.diagnose_gemini()
            if not health.get("configured") or not health.get("reachable"):
                raise RuntimeError(health.get("message") or "Gemini non disponibile.")

        current_snapshot = _load_ai_alerts_snapshot(user_email_param)
        dirty_value = "1" if current_snapshot.get("dirty") else "0"
        ts = _dt_to_storage(_utc_now())
        _save_ai_alerts_state(
            user_email_param,
            {
                AI_ALERTS_PAYLOAD_KEY: json.dumps(anomalies, ensure_ascii=False),
                AI_ALERTS_STATUS_KEY: "ready",
                AI_ALERTS_ERROR_KEY: "",
                AI_ALERTS_UPDATED_AT_KEY: ts,
                AI_ALERTS_LAST_ATTEMPT_AT_KEY: ts,
                AI_ALERTS_REFRESH_STARTED_AT_KEY: "",
                AI_ALERTS_DIRTY_KEY: dirty_value,
            },
        )
    except Exception as exc:
        logger.warning("Aggiornamento automatico avvisi AI fallito per %s: %s", user_email_param, exc, exc_info=True)
        current_snapshot = _load_ai_alerts_snapshot(user_email_param)
        dirty_value = "1" if current_snapshot.get("dirty") else "0"
        ts = _dt_to_storage(_utc_now())
        _save_ai_alerts_state(
            user_email_param,
            {
                AI_ALERTS_STATUS_KEY: "error",
                AI_ALERTS_ERROR_KEY: str(exc),
                AI_ALERTS_LAST_ATTEMPT_AT_KEY: ts,
                AI_ALERTS_REFRESH_STARTED_AT_KEY: "",
                AI_ALERTS_DIRTY_KEY: dirty_value,
            },
        )
    finally:
        with registry["lock"]:
            current = registry["threads"].get(user_email_param)
            if current is threading.current_thread():
                registry["threads"].pop(user_email_param, None)


def _ensure_ai_alerts_refresh(user_email_param: str, *, has_source_data: bool) -> dict:
    snapshot = _load_ai_alerts_snapshot(user_email_param)
    if not _should_refresh_ai_alerts(snapshot, has_source_data=has_source_data):
        return snapshot

    registry = _get_ai_alert_refresh_registry()
    with registry["lock"]:
        current = registry["threads"].get(user_email_param)
        if current and current.is_alive():
            return _load_ai_alerts_snapshot(user_email_param)
        if current and not current.is_alive():
            registry["threads"].pop(user_email_param, None)

        started_at = _utc_now()
        _save_ai_alerts_state(
            user_email_param,
            {
                AI_ALERTS_STATUS_KEY: "refreshing",
                AI_ALERTS_ERROR_KEY: "",
                AI_ALERTS_LAST_ATTEMPT_AT_KEY: _dt_to_storage(started_at),
                AI_ALERTS_REFRESH_STARTED_AT_KEY: _dt_to_storage(started_at),
                AI_ALERTS_DIRTY_KEY: "0",
            },
        )
        worker = threading.Thread(
            target=_ai_alerts_refresh_worker,
            args=(user_email_param,),
            daemon=True,
            name=f"ai-alerts-refresh:{user_email_param}",
        )
        registry["threads"][user_email_param] = worker
        worker.start()
    return _load_ai_alerts_snapshot(user_email_param)
 
 
settings = _load_settings_df(user_email)
anno_default = datetime.now().year
anno_prev_default = anno_default - 1
 
# Valori di default (solo se mancanti)
defaults_num = {
    "obiettivo_risparmio_perc": 30.0,
    "Saldo_conto_principale": 0,
    "Saldo_conto_secondario": 0,
    "pac_quote": 0.0,
    "pac_capitale_investito": 0.0,
    "pac_versamento_mensile": 100.0,
    "pac_rendimento_stimato": 7.0,
    "fondo_quote": 0.0,
    "fondo_capitale_investito": 0.0,
    "fondo_versamento_mensile": 50.0,
    "fondo_valore_quota": 7.28,
    "fondo_rendimento_stimato": 5.0,
    "aliquota_irpef": 0.26,
    f"saldo_iniziale_{anno_default}": 0,
    f"risparmio_precedente_{anno_prev_default}": 0,
    "budget_mensile_base": 1600.0,
}
defaults_txt = {
    "pac_ticker": "VNGA80",
    "fondo_codice": "CORAZN90",
    "fondo_previdoc_slug": "_core-pension-azionario-plus-90-esg",
    "fondo_teleborsa_slug": "core-pension-azionario-plus-90percent-esg",
}
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
    _invalidate_runtime_caches(settings=True)
    settings = _load_settings_df(user_email)
 
 
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


_quick_setup_completed = bool(s_txt("quick_settings_last_saved_at", "").strip())
if (not onboarding_required) and (not is_demo_account) and auth_provider == "google" and (not _quick_setup_completed):
    onboarding_required = True


_ONBOARDING_SESSION_KEYS = (
    "_force_onboarding_email",
    "_onb_step",
    "_onb_reset_optional_inputs",
    "_onb_data_salary",
    "_onb_data_saldo_iniziale",
    "_onb_data_risparmio_prev",
    "_onb_data_pct_necessita",
    "_onb_data_pct_svago",
    "_onb_data_pct_investimenti",
    "_onb_data_pac_ticker",
    "_onb_data_fondo_codice",
    "_onb_input_salary",
    "_onb_input_saldo_iniziale",
    "_onb_input_risparmio_prev",
    "_onb_input_pct_necessita",
    "_onb_input_pct_svago",
    "_onb_input_pct_investimenti",
    "_onb_input_pac_ticker",
    "_onb_input_fondo_codice",
)


def _clear_onboarding_state() -> None:
    for key in _ONBOARDING_SESSION_KEYS:
        st.session_state.pop(key, None)


def _init_onboarding_state() -> tuple[int, int]:
    anno_corrente = datetime.now().year
    anno_precedente = anno_corrente - 1
    has_manual_save = bool(s_txt("quick_settings_last_saved_at", "").strip())
    default_budget = float(s_num("budget_mensile_base", 0.0))
    default_salary = float(s_num("stipendio_mensile", 0.0)) or default_budget

    if not has_manual_save and abs(default_salary - 1600.0) < 1e-9:
        default_salary = 0.0

    pac_default = s_txt("pac_ticker", "").strip().upper()
    if not has_manual_save and pac_default == "VNGA80":
        pac_default = ""

    fondo_default = s_txt("fondo_codice", "").strip().upper()
    if not has_manual_save and fondo_default == "CORAZN90":
        fondo_default = ""

    percentuali = _get_percentuali_budget_cached(user_email)
    st.session_state.setdefault("_onb_step", 1)
    st.session_state.setdefault("_onb_data_salary", float(default_salary))
    st.session_state.setdefault(
        "_onb_data_saldo_iniziale",
        float(s_num_candidates([f"saldo_iniziale_{anno_corrente}", f"saldo iniziale_{anno_corrente}"], 0.0)),
    )
    st.session_state.setdefault(
        "_onb_data_risparmio_prev",
        float(s_num_candidates([f"risparmio_precedente_{anno_precedente}", f"risparmio_precedente_{anno_corrente}"], 0.0)),
    )
    st.session_state.setdefault("_onb_data_pct_necessita", int(round(percentuali.get("NECESSITÀ", 0.50) * 100)))
    st.session_state.setdefault("_onb_data_pct_svago", int(round(percentuali.get("SVAGO", 0.30) * 100)))
    st.session_state.setdefault("_onb_data_pct_investimenti", int(round(percentuali.get("INVESTIMENTI", 0.20) * 100)))
    st.session_state.setdefault("_onb_data_pac_ticker", pac_default)
    st.session_state.setdefault("_onb_data_fondo_codice", fondo_default)
    return anno_corrente, anno_precedente


def _render_onboarding_wizard() -> None:
    anno_corrente, anno_precedente = _init_onboarding_state()
    total_steps = 4
    step = int(max(1, min(total_steps, st.session_state.get("_onb_step", 1))))
    labels = [
        "Base",
        "Budget",
        "Investimenti",
        "Conferma",
    ]

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
    _, center, _ = st.columns([0.75, 1.8, 0.75])
    with center:
        st.markdown(
            "<div style='padding:28px 30px;border-radius:24px;"
            "background:rgba(9,15,29,0.86);border:1px solid rgba(92,118,178,0.24);"
            "box-shadow:0 18px 48px rgba(2,6,23,0.42);'>"
            "<div style='display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:18px;'>"
            "<div>"
            "<div style='font-size:0.78rem;font-weight:700;letter-spacing:1.6px;text-transform:uppercase;color:#60a5fa;'>Primo accesso</div>"
            "<div style='font-size:1.65rem;font-weight:800;color:#f8fbff;margin-top:4px;'>Configura il tuo profilo finanziario</div>"
            f"<div style='font-size:0.90rem;color:#93a9c7;margin-top:8px;'>Ciao {escape(NOME_DISPLAY.title())}, bastano pochi passaggi per partire con dati coerenti fin dal primo accesso.</div>"
            "</div>"
            f"<div style='font-size:0.82rem;font-weight:700;color:#8fb7ff;background:rgba(79,142,240,0.10);border:1px solid rgba(79,142,240,0.26);padding:8px 14px;border-radius:999px;'>Step {step}/{total_steps}</div>"
            "</div>",
            unsafe_allow_html=True,
        )

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        step_cols = st.columns(total_steps)
        for idx, (col, label) in enumerate(zip(step_cols, labels), start=1):
            is_active = idx == step
            is_done = idx < step
            bg = "rgba(16,217,138,0.14)" if is_done else "rgba(79,142,240,0.12)" if is_active else "rgba(92,118,178,0.10)"
            border = "rgba(16,217,138,0.35)" if is_done else "rgba(79,142,240,0.30)" if is_active else "rgba(92,118,178,0.18)"
            color = "#10d98a" if is_done else "#8fb7ff" if is_active else "#5a6f8c"
            badge = "✓" if is_done else str(idx)
            col.markdown(
                f"<div style='border-radius:14px;padding:12px 10px;text-align:center;background:{bg};"
                f"border:1px solid {border};margin-bottom:18px;'>"
                f"<div style='font-size:0.74rem;font-weight:800;color:{color};margin-bottom:2px;'>{badge}</div>"
                f"<div style='font-size:0.78rem;font-weight:700;color:{color};'>{label}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        if step == 1:
            st.session_state.setdefault("_onb_input_salary", float(st.session_state.get("_onb_data_salary", 0.0)))
            st.session_state.setdefault("_onb_input_saldo_iniziale", float(st.session_state.get("_onb_data_saldo_iniziale", 0.0)))
            st.session_state.setdefault("_onb_input_risparmio_prev", float(st.session_state.get("_onb_data_risparmio_prev", 0.0)))
            st.markdown(
                "<div style='font-size:1.02rem;font-weight:700;color:#f8fbff;margin-bottom:6px;'>Dati iniziali</div>"
                f"<div style='font-size:0.88rem;color:#8ba3c7;margin-bottom:16px;'>Inserisci i valori base con cui vuoi partire nel {anno_corrente}. Lo stipendio verrà usato come base iniziale del budget mensile.</div>",
                unsafe_allow_html=True,
            )
            col_salary, col_balance = st.columns(2)
            col_salary.number_input(
                "Stipendio mensile netto (€)",
                min_value=0.0,
                step=50.0,
                key="_onb_input_salary",
            )
            col_balance.number_input(
                f"Saldo iniziale {anno_corrente} (€)",
                min_value=0.0,
                step=100.0,
                key="_onb_input_saldo_iniziale",
            )
            st.number_input(
                f"Risparmio trasferito dal {anno_precedente} (€)",
                min_value=0.0,
                step=100.0,
                key="_onb_input_risparmio_prev",
            )
            st.caption("Potrai modificare questi valori in qualsiasi momento dalle impostazioni rapide nella sidebar.")

            _, col_next = st.columns([1, 1])
            if col_next.button("Continua", key="onb_next_1", use_container_width=True, type="primary"):
                salary = float(st.session_state.get("_onb_input_salary", 0.0) or 0.0)
                saldo_iniziale = float(st.session_state.get("_onb_input_saldo_iniziale", 0.0) or 0.0)
                risparmio_prev = float(st.session_state.get("_onb_input_risparmio_prev", 0.0) or 0.0)
                if salary <= 0:
                    st.error("Inserisci uno stipendio mensile maggiore di zero per procedere.")
                else:
                    st.session_state["_onb_data_salary"] = salary
                    st.session_state["_onb_data_saldo_iniziale"] = saldo_iniziale
                    st.session_state["_onb_data_risparmio_prev"] = risparmio_prev
                    st.session_state["_onb_step"] = 2
                    st.rerun()

        elif step == 2:
            st.session_state.setdefault("_onb_input_pct_necessita", int(st.session_state.get("_onb_data_pct_necessita", 50)))
            st.session_state.setdefault("_onb_input_pct_svago", int(st.session_state.get("_onb_data_pct_svago", 30)))
            st.session_state.setdefault("_onb_input_pct_investimenti", int(st.session_state.get("_onb_data_pct_investimenti", 20)))
            st.markdown(
                "<div style='font-size:1.02rem;font-weight:700;color:#f8fbff;margin-bottom:6px;'>Distribuzione del budget</div>"
                "<div style='font-size:0.88rem;color:#8ba3c7;margin-bottom:16px;'>Definisci come distribuire il tuo budget mensile tra necessità, svago e investimenti. La somma deve restare al 100%.</div>",
                unsafe_allow_html=True,
            )
            col_n, col_s, col_i = st.columns(3)
            col_n.slider("Necessità", min_value=0, max_value=100, step=1, key="_onb_input_pct_necessita")
            col_s.slider("Svago", min_value=0, max_value=100, step=1, key="_onb_input_pct_svago")
            col_i.slider("Investimenti", min_value=0, max_value=100, step=1, key="_onb_input_pct_investimenti")
            totale = (
                int(st.session_state.get("_onb_input_pct_necessita", 0))
                + int(st.session_state.get("_onb_input_pct_svago", 0))
                + int(st.session_state.get("_onb_input_pct_investimenti", 0))
            )
            is_valid = (totale == 100)
            banner_bg = "rgba(16,217,138,0.10)" if is_valid else "rgba(250,89,142,0.10)"
            banner_border = "rgba(16,217,138,0.30)" if is_valid else "rgba(250,89,142,0.30)"
            banner_text = "#10d98a" if is_valid else "#fa598e"
            banner_label = "Distribuzione valida" if is_valid else "La somma deve essere 100%"
            st.markdown(
                f"<div style='text-align:center;padding:11px;border-radius:12px;margin:12px 0 8px;"
                f"background:{banner_bg};border:1px solid {banner_border};'>"
                f"<span style='color:{banner_text};font-weight:700;font-size:0.92rem;'>Totale: {totale}% • {banner_label}</span></div>",
                unsafe_allow_html=True,
            )

            col_back, col_next = st.columns(2)
            if col_back.button("Indietro", key="onb_back_2", use_container_width=True):
                st.session_state["_onb_data_pct_necessita"] = int(st.session_state.get("_onb_input_pct_necessita", 0))
                st.session_state["_onb_data_pct_svago"] = int(st.session_state.get("_onb_input_pct_svago", 0))
                st.session_state["_onb_data_pct_investimenti"] = int(st.session_state.get("_onb_input_pct_investimenti", 0))
                st.session_state["_onb_step"] = 1
                st.rerun()
            if col_next.button("Continua", key="onb_next_2", use_container_width=True, type="primary", disabled=not is_valid):
                st.session_state["_onb_data_pct_necessita"] = int(st.session_state.get("_onb_input_pct_necessita", 0))
                st.session_state["_onb_data_pct_svago"] = int(st.session_state.get("_onb_input_pct_svago", 0))
                st.session_state["_onb_data_pct_investimenti"] = int(st.session_state.get("_onb_input_pct_investimenti", 0))
                st.session_state["_onb_step"] = 3
                st.rerun()

        elif step == 3:
            if st.session_state.pop("_onb_reset_optional_inputs", False):
                st.session_state.pop("_onb_input_pac_ticker", None)
                st.session_state.pop("_onb_input_fondo_codice", None)
            st.session_state.setdefault("_onb_input_pac_ticker", str(st.session_state.get("_onb_data_pac_ticker", "") or ""))
            st.session_state.setdefault("_onb_input_fondo_codice", str(st.session_state.get("_onb_data_fondo_codice", "") or ""))
            st.markdown(
                "<div style='font-size:1.02rem;font-weight:700;color:#f8fbff;margin-bottom:6px;'>Asset opzionali</div>"
                "<div style='font-size:0.88rem;color:#8ba3c7;margin-bottom:16px;'>Se vuoi, puoi già collegare il tuo PAC e il fondo pensione. Se non hai ancora questi dati, lascia pure i campi vuoti.</div>",
                unsafe_allow_html=True,
            )
            st.text_input(
                "Ticker ETF PAC (opzionale)",
                placeholder="es. VWCE, V80A.DE, VNGA80",
                key="_onb_input_pac_ticker",
            )
            st.text_input(
                "Codice Fondo Pensione (opzionale)",
                placeholder="es. CORAZN90",
                key="_onb_input_fondo_codice",
            )
            st.caption("Il codice fondo viene salvato subito. Eventuali slug e parametri avanzati resteranno configurabili dopo nelle impostazioni rapide.")

            col_back, col_skip, col_next = st.columns(3)
            if col_back.button("Indietro", key="onb_back_3", use_container_width=True):
                st.session_state["_onb_data_pac_ticker"] = str(st.session_state.get("_onb_input_pac_ticker", "") or "").strip().upper()
                st.session_state["_onb_data_fondo_codice"] = str(st.session_state.get("_onb_input_fondo_codice", "") or "").strip().upper()
                st.session_state["_onb_step"] = 2
                st.rerun()
            if col_skip.button("Salta per ora", key="onb_skip_3", use_container_width=True):
                st.session_state["_onb_data_pac_ticker"] = ""
                st.session_state["_onb_data_fondo_codice"] = ""
                st.session_state["_onb_reset_optional_inputs"] = True
                st.session_state["_onb_step"] = 4
                st.rerun()
            if col_next.button("Continua", key="onb_next_3", use_container_width=True, type="primary"):
                st.session_state["_onb_data_pac_ticker"] = str(st.session_state.get("_onb_input_pac_ticker", "") or "").strip().upper()
                st.session_state["_onb_data_fondo_codice"] = str(st.session_state.get("_onb_input_fondo_codice", "") or "").strip().upper()
                st.session_state["_onb_step"] = 4
                st.rerun()

        else:
            stipendio = float(st.session_state.get("_onb_data_salary", 0.0) or 0.0)
            saldo_iniziale = float(st.session_state.get("_onb_data_saldo_iniziale", 0.0) or 0.0)
            risparmio_prev = float(st.session_state.get("_onb_data_risparmio_prev", 0.0) or 0.0)
            perc_necessita = int(st.session_state.get("_onb_data_pct_necessita", 0))
            perc_svago = int(st.session_state.get("_onb_data_pct_svago", 0))
            perc_investimenti = int(st.session_state.get("_onb_data_pct_investimenti", 0))
            totale = perc_necessita + perc_svago + perc_investimenti
            pac_ticker = str(st.session_state.get("_onb_data_pac_ticker", "") or "").strip().upper()
            fondo_codice = str(st.session_state.get("_onb_data_fondo_codice", "") or "").strip().upper()

            st.markdown(
                "<div style='font-size:1.02rem;font-weight:700;color:#f8fbff;margin-bottom:6px;'>Riepilogo finale</div>"
                "<div style='font-size:0.88rem;color:#8ba3c7;margin-bottom:16px;'>Controlla i dati sotto. Al salvataggio il wizard non verrà più mostrato e potrai rifinire tutto in seguito dalle impostazioni.</div>",
                unsafe_allow_html=True,
            )

            c1, c2, c3 = st.columns(3)
            c1.metric("Stipendio / Budget base", eur2(stipendio))
            c2.metric(f"Saldo iniziale {anno_corrente}", eur2(saldo_iniziale))
            c3.metric(f"Risparmio da {anno_precedente}", eur2(risparmio_prev))

            st.markdown(
                f"<div style='margin:12px 0 16px;padding:14px 16px;border-radius:14px;"
                "background:rgba(79,142,240,0.08);border:1px solid rgba(79,142,240,0.18);'>"
                f"<div style='font-size:0.78rem;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;color:#8fb7ff;margin-bottom:6px;'>Budget</div>"
                f"<div style='font-size:0.92rem;color:#dde6f5;'>Necessità <strong>{perc_necessita}%</strong> • Svago <strong>{perc_svago}%</strong> • Investimenti <strong>{perc_investimenti}%</strong></div>"
                f"<div style='font-size:0.82rem;color:#8ba3c7;margin-top:6px;'>PAC: <strong>{escape(pac_ticker or 'Non configurato')}</strong> • Fondo: <strong>{escape(fondo_codice or 'Non configurato')}</strong></div>"
                "</div>",
                unsafe_allow_html=True,
            )

            col_back, col_finish = st.columns(2)
            if col_back.button("Indietro", key="onb_back_4", use_container_width=True):
                st.session_state["_onb_step"] = 3
                st.rerun()

            if col_finish.button("Completa configurazione", key="onb_finish", use_container_width=True, type="primary"):
                if stipendio <= 0:
                    st.error("Lo stipendio mensile deve essere maggiore di zero.")
                elif totale != 100:
                    st.error("La distribuzione del budget deve sommare esattamente 100%.")
                else:
                    percentuali = {
                        "NECESSITÀ": perc_necessita / 100.0,
                        "SVAGO": perc_svago / 100.0,
                        "INVESTIMENTI": perc_investimenti / 100.0,
                    }
                    ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    num_payload = {
                        "stipendio_mensile": stipendio,
                        "budget_mensile_base": stipendio,
                        f"saldo_iniziale_{anno_corrente}": saldo_iniziale,
                        f"risparmio_precedente_{anno_precedente}": risparmio_prev,
                    }
                    txt_payload = {
                        "pac_ticker": pac_ticker,
                        "fondo_codice": fondo_codice,
                        "fondo_previdoc_slug": "",
                        "fondo_teleborsa_slug": "",
                        "impost_percentuali_budget": json.dumps(percentuali, ensure_ascii=False),
                        "quick_settings_last_saved_at": ts,
                    }
                    ok, err = _save_settings_batch(num_payload, txt_payload)
                    if not ok:
                        st.error(f"Salvataggio onboarding fallito: {err}")
                    elif not mark_onboarding_completed(user_email):
                        st.error("Configurazione salvata, ma non sono riuscito a chiudere l'onboarding. Riprova.")
                    else:
                        _invalidate_runtime_caches(settings=True, user_settings=True)
                        st.session_state["quick_settings_saved_msg"] = f"Configurazione iniziale completata alle {ts}."
                        _clear_onboarding_state()
                        st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    _render_app_footer()
    st.stop()


if onboarding_required:
    _render_onboarding_wizard()


if st.session_state.pop("_totp_recovery_success", False):
    st.success(
        "Recovery 2FA completato. Il vecchio Authenticator è stato disattivato: "
        "configura di nuovo il 2FA dalle Impostazioni.",
        icon="✅",
    )


if user_email and not is_demo_account and not is_totp_enabled(user_email):
    st.warning(
        "🔒 **Sicurezza account:** L'autenticazione a due fattori non è attiva. "
        "Attivala nelle **Impostazioni** per proteggere meglio il tuo account.",
        icon="⚠️",
    )


def _build_fondo_urls(codice: str, previdoc_slug: str, teleborsa_slug: str) -> tuple[str, str]:
    cod_up = codice.strip().upper()
    cod_lo = codice.strip().lower()
    b64_suffix = base64.b64encode(f"FM.{cod_up}".encode()).decode().rstrip("=")
    previdoc_url = f"http://www.previdoc.it/d/Ana/{cod_up}/{previdoc_slug}"
    teleborsa_url = f"https://www.teleborsa.it/fondi/{teleborsa_slug}-{cod_lo}-{b64_suffix}"
    return previdoc_url, teleborsa_url


@st.cache_data(ttl=43200, show_spinner=False)
def _fetch_quota_fondo_pensione(
    codice: str,
    previdoc_slug: str,
    teleborsa_slug: str,
    _bust: str = "v2",
) -> tuple[float | None, str, str]:
    import requests
    from bs4 import BeautifulSoup

    previdoc_url, teleborsa_url = _build_fondo_urls(codice, previdoc_slug, teleborsa_slug)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "it-IT,it;q=0.9",
    }

    def _parse_previdoc(html: str) -> tuple[float | None, str]:
        soup = BeautifulSoup(html, "html.parser")
        testo = soup.get_text(separator="\n")
        nav_val, data_fondo = None, ""
        for dt in soup.find_all("dt"):
            dd = dt.find_next_sibling("dd")
            if not dd:
                continue
            label = dt.get_text(strip=True)
            value = dd.get_text(strip=True)
            if "Valore quota" in label:
                match = re.search(r"([\d]+[,.][\d]{2,4})", value)
                if match:
                    nav_val = float(match.group(1).replace(",", "."))
            elif "Ultimo aggiornamento" in label:
                data_fondo = value
        if nav_val is None:
            match = re.search(r"Valore quota[\s\S]{0,30}?([\d]+[,.][\d]{2,4})", testo)
            if match:
                nav_val = float(match.group(1).replace(",", "."))
        if not data_fondo:
            match = re.search(r"Ultimo aggiornamento[\s\S]{0,30}?(\d{2}/\d{2}/\d{4})", testo)
            if match:
                data_fondo = match.group(1)
        return nav_val, data_fondo

    def _parse_teleborsa(html: str) -> tuple[float | None, str]:
        testo = BeautifulSoup(html, "html.parser").get_text(separator="\n")
        nav_val, data_fondo = None, ""
        match = re.search(r"\n\s*([\d]{1,2}[,.][\d]{3,4})\s*\n\s*[+\-][\d.,]+%", testo)
        if match:
            nav_val = float(match.group(1).replace(",", "."))
        match_data = re.search(r"Ultimo aggiornamento[:\s*]+(\d{2}/\d{2}/\d{4})", testo)
        if match_data:
            data_fondo = match_data.group(1)
        return nav_val, data_fondo

    for url, parser in ((previdoc_url, _parse_previdoc), (teleborsa_url, _parse_teleborsa)):
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            nav_val, data_fondo = parser(response.text)
            if nav_val and nav_val > 0:
                ts = datetime.now().strftime("%d/%m/%Y %H:%M")
                logger.info("Quota fondo [%s]: %.4f € (%s) da %s", codice, nav_val, data_fondo, url)
                return nav_val, data_fondo, ts
        except Exception as exc:
            logger.warning("_fetch_quota_fondo_pensione [%s]: %s", url, exc)

    return None, "", ""
 
 
# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
 
# Avatar: iniziali utente + email + logout — stile moderno
_initials = "".join(w[0].upper() for w in (NOME_DISPLAY or "U").split()[:2]) or "U"
st.sidebar.markdown(f"""
<div style="display:flex;align-items:center;gap:12px;padding:12px 12px 10px;
    background:transparent !important;border:1px solid rgba(112,143,215,0.28);
    border-radius:14px;margin-bottom:4px;margin-top:-6px;">
  <div style="width:46px;height:46px;border-radius:50%;flex-shrink:0;
    background:linear-gradient(135deg,#9b74f5 0%,#f472b6 100%);
    display:flex;align-items:center;justify-content:center;
    font-size:1.1rem;font-weight:800;color:#fff;
    box-shadow:0 0 16px rgba(155,116,245,0.35);">{escape(_initials)}</div>
  <div style="min-width:0;overflow:hidden;">
    <div style="font-size:0.88rem;font-weight:700;color:#ffffff;
      white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{escape(str(NOME_DISPLAY or 'Utente'))}</div>
    <div style="font-size:0.72rem;color:#60a5fa;margin-top:1px;
      white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{escape(str(AUTH_USER_EMAIL or ''))}</div>
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
        target_perc = st.number_input(
            f"Incremento risparmio % (vs {prev_year})",
            0.0,
            100.0,
            s_num("obiettivo_risparmio_perc", 30.0),
            1.0,
        )
        risp_prev = st.number_input(
            f"Risparmio anno prec. ({prev_year}) €",
            0.0,
            value=s_num_candidates(risp_prev_candidates, 0.0),
            step=100.0,
        )
        saldo_iniziale_set = st.number_input(
            f"Saldo iniziale {anno_sel} (€)",
            0.0,
            value=s_num_candidates(saldo_iniziale_candidates, 0.0),
            step=100.0,
        )
        budget_base_set = st.number_input(
            "Budget mensile base (€)",
            0.0,
            value=s_num("budget_mensile_base", 0.0),
            step=50.0,
        )
        Saldo_conto_principale_set = st.number_input(
            "Saldo Conto Prin. (€)",
            0.0,
            value=s_num("Saldo_conto_principale", 0),
            step=50.0,
        )
        Saldo_conto_secondario_set = st.number_input(
            "Saldo Conto Sec. (€)",
            0.0,
            value=s_num("Saldo_conto_secondario", 0),
            step=50.0,
        )
        pac_quote_set = st.number_input("Quote PAC", 0, value=int(s_num("pac_quote", 0)), step=1)
        pac_capitale_base_set = st.number_input(
            "Capitale PAC investito (€)",
            0.0,
            value=s_num("pac_capitale_investito", 0.0),
            step=10.0,
        )
        pac_vers_set = st.number_input(
            "Versamento mensile PAC (€)",
            0.0,
            value=s_num("pac_versamento_mensile", 80.0),
            step=10.0,
        )
        pac_ticker_set = st.text_input("Ticker ETF PAC", value=s_txt("pac_ticker", "VNGA80"))
        pac_rend_set = st.number_input(
            "Rendimento PAC stimato (%)",
            0.0,
            value=s_num("pac_rendimento_stimato", 7.0),
            step=0.5,
        )
        fondo_quote_set = st.number_input(
            "Quote Fondo Pensione",
            0.0,
            value=s_num("fondo_quote", 0.0),
            step=1.0,
        )
        fondo_capitale_base_set = st.number_input(
            "Capitale Fondo investito (€)",
            0.0,
            value=s_num("fondo_capitale_investito", 0.0),
            step=10.0,
        )
        fondo_vers_set = st.number_input(
            "Versamento mensile Fondo (€)",
            0.0,
            value=s_num("fondo_versamento_mensile", 50.0),
            step=10.0,
        )
        fondo_codice_set = st.text_input(
            "Codice Fondo Pensione",
            value=s_txt("fondo_codice", "CORAZN90"),
            help="Codice breve del fondo usato per recuperare la quota live.",
        )
        fondo_previdoc_slug_set = st.text_input(
            "Slug PreviDoc Fondo",
            value=s_txt("fondo_previdoc_slug", "_core-pension-azionario-plus-90-esg"),
        )
        fondo_teleborsa_slug_set = st.text_input(
            "Slug Teleborsa Fondo",
            value=s_txt("fondo_teleborsa_slug", "core-pension-azionario-plus-90percent-esg"),
        )
        aliq_irpef_set = st.number_input(
            "Aliquota IRPEF (0-1)",
            0.0,
            1.0,
            s_num("aliquota_irpef", 0.26),
            0.01,
            format="%.2f",
        )
        fondo_rend_set = st.number_input(
            "Rendimento Fondo stimato (%)",
            0.0,
            value=s_num("fondo_rendimento_stimato", 5.0),
            step=0.5,
        )
        fondo_tfr_set = st.number_input(
            "TFR versato anno (€)",
            0.0,
            value=s_num("fondo_tfr_versato_anno", 0.0),
            step=100.0,
        )
        fondo_snapshot_set = st.text_input(
            "Data snapshot Fondo (YYYY-MM-DD)",
            value=s_txt("fondo_data_snapshot", str(date.today())),
        )
 
        if st.form_submit_button("💾 Salva impostazioni", use_container_width=True):
            num_payload = {
                "obiettivo_risparmio_perc": float(target_perc),
                f"risparmio_precedente_{prev_year}": float(risp_prev),
                f"saldo_iniziale_{anno_sel}": float(saldo_iniziale_set),
                "budget_mensile_base": float(budget_base_set),
                "Saldo_conto_principale": float(Saldo_conto_principale_set),
                "Saldo_conto_secondario": float(Saldo_conto_secondario_set),
                "pac_quote": float(pac_quote_set),
                "pac_capitale_investito": float(pac_capitale_base_set),
                "pac_versamento_mensile": float(pac_vers_set),
                "fondo_quote": float(fondo_quote_set),
                "fondo_capitale_investito": float(fondo_capitale_base_set),
                "fondo_versamento_mensile": float(fondo_vers_set),
                "aliquota_irpef": float(aliq_irpef_set),
                "pac_rendimento_stimato": float(pac_rend_set),
                "fondo_rendimento_stimato": float(fondo_rend_set),
                "fondo_tfr_versato_anno": float(fondo_tfr_set),
            }
            txt_payload = {
                "pac_ticker": str(pac_ticker_set).strip(),
                "fondo_data_snapshot": str(fondo_snapshot_set),
                "fondo_codice": str(fondo_codice_set).strip().upper(),
                "fondo_previdoc_slug": str(fondo_previdoc_slug_set).strip(),
                "fondo_teleborsa_slug": str(fondo_teleborsa_slug_set).strip(),
            }
            ok, err = _save_settings_batch(num_payload, txt_payload)
            if not ok:
                st.session_state["quick_settings_saved_err"] = f"Salvataggio fallito: {err}"
                st.rerun()
            ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            _save_settings_batch({}, {"quick_settings_last_saved_at": ts})
            st.session_state["quick_settings_saved_msg"] = f"Impostazioni salvate alle {ts}."
            settings = _load_settings_df(user_email)
            st.rerun()
 
# Parametri correnti (prima e dopo il form, usa sempre i valori del DB ricaricato)
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
fondo_codice_corrente = str(fondo_codice_set).strip().upper()
fondo_previdoc_slug_corrente = str(fondo_previdoc_slug_set).strip() or s_txt(
    "fondo_previdoc_slug",
    "_core-pension-azionario-plus-90-esg",
)
fondo_teleborsa_slug_corrente = str(fondo_teleborsa_slug_set).strip() or s_txt(
    "fondo_teleborsa_slug",
    "core-pension-azionario-plus-90percent-esg",
)
_quota_result = _fetch_quota_fondo_pensione(
    fondo_codice_corrente,
    fondo_previdoc_slug_corrente,
    fondo_teleborsa_slug_corrente,
)
_quota_live, _quota_data, _quota_ts = _quota_result if _quota_result else (None, "", "")
fondo_valore_quota_corrente = (
    _quota_live if (_quota_live is not None and _quota_live > 0) else s_num("fondo_valore_quota", 0.0)
)
_quota_saved = s_num("fondo_valore_quota", 0.0)
if _quota_live and _quota_live > 0 and abs(float(_quota_live) - float(_quota_saved)) > 1e-9:
    db.imposta_parametro("fondo_valore_quota", valore_num=_quota_live, user_email=user_email)
    _invalidate_runtime_caches(settings=True)
fondo_rend_corrente = float(fondo_rend_set)
aliquota_irpef_corrente = float(aliq_irpef_set)
budget_base = budget_base_corrente
 
# Pannello residuo mese in sidebar
df_budget = log.budget_spese_annuale(
    df_mov,
    anno_sel,
    budget_base,
    percentuali_override=_get_percentuali_budget_cached(user_email),
)
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

# ── Eliminazione account — sidebar ────────────────────────────────────────────
st.sidebar.markdown("<hr style='border:0;border-top:1px solid rgba(92,118,178,0.18);margin:18px 0 14px;'>", unsafe_allow_html=True)
 
if not is_demo_account:
    del_step = st.session_state.get("_del_account_step")
 
    # STEP 0: bottone iniziale
    if del_step is None:
        if st.sidebar.button(
            "🗑️ Elimina account",
            key="btn_sidebar_del_start",
            use_container_width=True,
        ):
            st.session_state["_del_account_step"] = "confirm"
            st.rerun()
 
    # STEP 1: conferma con password
    elif del_step == "confirm":
        if auth_provider == "google":
            st.sidebar.warning("⚠️ Operazione irreversibile. Conferma l'identità con Google per continuare.")
            st.sidebar.caption(
                "Per gli account Google la password non può essere verificata localmente dall'app. "
                "Serve una nuova conferma OAuth con lo stesso account."
            )
            if OAuth2Component is None:
                st.sidebar.error("Modulo OAuth mancante. Impossibile confermare l'account Google.")
            elif not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
                st.sidebar.error("Credenziali OAuth Google mancanti.")
            else:
                redirect_uri = _redirect_uri()
                if not redirect_uri:
                    st.sidebar.error("APP_BASE_URL non configurato.")
                else:
                    oauth2_delete = OAuth2Component(
                        GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
                        AUTHORIZE_URL, TOKEN_URL, TOKEN_URL, ""
                    )
                    result = _safe_google_authorize_button(
                        oauth2_delete,
                        name="Conferma con Google",
                        scope="openid email profile",
                        redirect_uri=redirect_uri,
                        key="google_delete_confirm",
                        use_container_width=True,
                        extras_params={"prompt": "login", "login_hint": user_email},
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
                        if email_google and email_google == str(user_email).strip().lower():
                            _reset_google_oauth_state("google_delete_confirm")
                            _clear_query_params()
                            st.session_state["_del_account_step"] = "reconfirm"
                            st.rerun()
                        elif email_google:
                            st.sidebar.error("Hai confermato un account Google diverso da quello loggato.")

            if st.sidebar.button("Annulla", key="btn_sidebar_del_cancel_google", use_container_width=True):
                st.session_state.pop("_del_account_step", None)
                st.rerun()
        else:
            st.sidebar.warning("⚠️ Operazione irreversibile. Inserisci la password per confermare.")
            pwd_confirm = st.sidebar.text_input(
                "Password",
                type="password",
                key="del_account_pwd_sidebar",
            )
            col_ok, col_no = st.sidebar.columns(2)
            if col_ok.button("Continua →", key="btn_sidebar_del_ok", use_container_width=True, type="primary"):
                if not pwd_confirm:
                    st.sidebar.error("Inserisci la password.")
                else:
                    from security import verify_password as _vp
                    try:
                        with db.connetti_db() as _conn:
                            with _conn.cursor() as _cur:
                                _cur.execute(
                                    "SELECT password_hash FROM utenti_registrati WHERE email = %s",
                                    (user_email,),
                                )
                                _row = _cur.fetchone()
                    except Exception:
                        _row = None

                    if not _row or not _vp(pwd_confirm, _row[0]):
                        st.sidebar.error("Password non corretta.")
                    else:
                        st.session_state["_del_account_step"] = "reconfirm"
                        st.rerun()

            if col_no.button("Annulla", key="btn_sidebar_del_cancel1", use_container_width=True):
                st.session_state.pop("_del_account_step", None)
                st.rerun()
 
    # STEP 2: ultima conferma
    elif del_step == "reconfirm":
        st.sidebar.error(f"Elimini **{user_email}** e tutti i suoi dati. Impossibile recuperarli.")
        col_yes, col_no = st.sidebar.columns(2)
        if col_yes.button("🗑️ Sì, elimina", key="btn_sidebar_del_final", use_container_width=True, type="primary"):
            try:
                db.elimina_account_utente(user_email)
                _delete_cookie(SESSION_TOKEN_COOKIE)
                for k in list(st.session_state.keys()):
                    del st.session_state[k]
                st.rerun()
            except Exception as exc:
                st.sidebar.error(f"Errore: {exc}")
        if col_no.button("No, annulla", key="btn_sidebar_del_cancel2", use_container_width=True):
            st.session_state.pop("_del_account_step", None)
            st.rerun()
 
# ---------------------------------------------------------------------------
# Header principale
# ---------------------------------------------------------------------------
 
st.markdown(
    f"<div style='font-family:\"Plus Jakarta Sans\",sans-serif;font-size:0.99rem;"
    f"font-weight:700;letter-spacing:2px;text-transform:uppercase;"
    f"color:{Colors.TEXT_MID};margin-bottom:10px;'>"
    f" PERSONAL BUDGET - {MONTH_NAMES.get(mese_sel, mese_sel)} {anno_sel}</div>",
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
        f"""<div style="background:rgba(255,255,255,0.04);backdrop-filter:blur(16px) saturate(150%);-webkit-backdrop-filter:blur(16px) saturate(150%);border:1px solid rgba(92,118,178,0.22);
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
    return st.session_state.setdefault("_cal_cache", {})


def _calcolo_scadenze_mese(mese_ref: int, anno_ref: int):
    key = f"{anno_ref}-{mese_ref}"
    cache = _get_calendario_cached()
    if key not in cache:
        df_ric = _load_spese_ricorrenti_df(user_email).copy()
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


def _fmt_k(v) -> str:
    try:
        v = float(v)
        return f"€{v/1000:.1f}k" if abs(v) >= 1000 else f"€{v:.0f}"
    except Exception:
        return ""


def _fallback_insight_previsione(
    anno: int,
    mese_cutoff: int,
    saldo_osservato: float,
    saldo_dicembre: float,
    delta_previsto: float,
    entrate_attese: float,
    uscite_attese: float,
    metodo: str,
) -> str:
    mese_label = MONTH_NAMES.get(int(mese_cutoff), str(mese_cutoff))
    mesi_restanti = max(12 - int(mese_cutoff), 0)
    verbo = "salire" if saldo_dicembre >= saldo_osservato else "scendere"
    delta_mensile_label = f"€ {abs(delta_previsto):,.0f}"

    if mesi_restanti == 0:
        return (
            f"A dicembre {anno} il saldo si chiude a circa € {saldo_dicembre:,.0f}. "
            f"Il delta mensile osservato finale è circa {delta_previsto:+,.0f} €."
        )

    if "senza entrate recenti" in str(metodo).lower():
        return (
            f"Da {mese_label.upper()} a dicembre il saldo potrebbe {verbo} fino a circa € {saldo_dicembre:,.0f}. "
            f"Non risultano entrate recenti confermate: la proiezione assume € 0 di entrate e circa € {uscite_attese:,.0f} di uscite al mese."
        )

    return (
        f"Da {mese_label.upper()} a dicembre il saldo potrebbe {verbo} fino a circa € {saldo_dicembre:,.0f}. "
        f"La proiezione usa entrate attese di circa € {entrate_attese:,.0f} e uscite di circa € {uscite_attese:,.0f} al mese, "
        f"per un delta mensile stimato di {'+' if delta_previsto >= 0 else '-'}{delta_mensile_label}."
    )


@st.cache_data(ttl=10800, show_spinner=False)
def _genera_insight_previsione(
    anno: int,
    mese_cutoff: int,
    saldo_osservato: float,
    saldo_dicembre: float,
    delta_previsto: float,
    entrate_attese: float,
    uscite_attese: float,
    metodo: str,
) -> str:
    return _fallback_insight_previsione(
        anno=anno,
        mese_cutoff=mese_cutoff,
        saldo_osservato=saldo_osservato,
        saldo_dicembre=saldo_dicembre,
        delta_previsto=delta_previsto,
        entrate_attese=entrate_attese,
        uscite_attese=uscite_attese,
        metodo=metodo,
    )


def _fallback_spiegazione_previsione_ai(
    anno: int,
    mese_cutoff: int,
    saldo_osservato: float,
    saldo_dicembre: float,
    delta_previsto: float,
    entrate_attese: float,
    uscite_attese: float,
    metodo: str,
) -> str:
    mese_label = MONTH_NAMES.get(int(mese_cutoff), str(mese_cutoff))
    saldo_diff = saldo_dicembre - saldo_osservato
    direzione = "cresce" if saldo_diff > 0 else "scende" if saldo_diff < 0 else "resta quasi stabile"
    if "senza entrate recenti" in str(metodo).lower():
        return (
            f"La previsione da {mese_label} a dicembre non assume nuove entrate: usa € 0 di entrate attese "
            f"e circa € {uscite_attese:,.0f} di uscite al mese. Per questo il saldo {direzione} invece di seguire un trend statistico."
        )
    return (
        f"La previsione usa un cash flow mensile stimato di {delta_previsto:+,.0f} €, ottenuto da entrate attese "
        f"di circa € {entrate_attese:,.0f} e uscite attese di circa € {uscite_attese:,.0f}. "
        f"Per questo il saldo a dicembre converge verso € {saldo_dicembre:,.0f}."
    )


@st.cache_data(ttl=10800, show_spinner=False)
def _genera_spiegazione_previsione_ai(
    anno: int,
    mese_cutoff: int,
    saldo_osservato: float,
    saldo_dicembre: float,
    delta_previsto: float,
    entrate_attese: float,
    uscite_attese: float,
    metodo: str,
) -> str:
    import ai_engine

    fallback = _fallback_spiegazione_previsione_ai(
        anno=anno,
        mese_cutoff=mese_cutoff,
        saldo_osservato=saldo_osservato,
        saldo_dicembre=saldo_dicembre,
        delta_previsto=delta_previsto,
        entrate_attese=entrate_attese,
        uscite_attese=uscite_attese,
        metodo=metodo,
    )
    prompt = (
        f"Previsione saldo deterministica dell'utente:\n"
        f"- Anno: {anno}\n"
        f"- Ultimo mese reale: {MONTH_NAMES.get(int(mese_cutoff), mese_cutoff)}\n"
        f"- Saldo osservato attuale: € {saldo_osservato:,.0f}\n"
        f"- Saldo previsto a dicembre: € {saldo_dicembre:,.0f}\n"
        f"- Delta mensile previsto: {delta_previsto:+.0f} €/mese\n"
        f"- Entrate attese: € {entrate_attese:,.0f}/mese\n"
        f"- Uscite attese: € {uscite_attese:,.0f}/mese\n"
        f"- Metodo: {metodo}\n\n"
        "Scrivi 2 frasi in italiano, tono chiaro e pratico. "
        "Spiega perché il saldo sale o scende e indica quale variabile conta di più. "
        "Max 45 parole. Nessun markdown."
    )
    try:
        text = ai_engine._call_gemini("Sei un analista finanziario sintetico.", prompt)
        text = " ".join(str(text or "").split())
        return text or fallback
    except Exception:
        return fallback


def _simula_scenario_previsione(
    df_prev: pd.DataFrame,
    mese_inizio: int,
    entrate_attese: float,
    uscite_attese: float,
    una_tantum: float = 0.0,
) -> pd.DataFrame:
    if df_prev is None or df_prev.empty:
        return pd.DataFrame()

    df_base = df_prev.copy().sort_values("MeseNum")
    df_reale = df_base[df_base["Tipo"] == "Reale"].sort_values("MeseNum")
    if df_reale.empty:
        return pd.DataFrame()

    ultimo_mese_reale = int(df_reale["MeseNum"].max())
    saldo_corrente = float(df_reale["Saldo"].iloc[-1])
    delta_scenario = float(entrate_attese - uscite_attese)
    if entrate_attese <= 1e-9:
        delta_scenario = min(delta_scenario, 0.0)

    rows = []
    for _, row in df_base.iterrows():
        mese_num = int(row["MeseNum"])
        if mese_num <= ultimo_mese_reale:
            saldo_val = float(row["Saldo"])
            tipo = "Reale"
        else:
            if mese_num < mese_inizio:
                delta = float(row.get("DeltaPrevisto") or 0.0)
            else:
                delta = delta_scenario + (una_tantum if mese_num == mese_inizio else 0.0)
            saldo_corrente += delta
            saldo_val = saldo_corrente
            tipo = "Scenario"

        rows.append({
            "Mese": row["Mese"],
            "MeseNum": mese_num,
            "SaldoScenario": round(saldo_val, 2),
            "TipoScenario": tipo,
        })

    return pd.DataFrame(rows)


if "ai_chat_history" not in st.session_state:
    st.session_state["ai_chat_history"] = []


@st.dialog("🤖 Assistente Finanziario", width="large")
def _show_ai_chat():
    import ai_engine

    st.caption(
        "Fai domande sui tuoi dati finanziari in linguaggio naturale. "
        "Attenzione: i dati vengono inviati a un servizio AI esterno per l'elaborazione, ma non vengono memorizzati. (BETA, funzionalità sperimentale) "
    )
    st.caption(
        "_Esempi: 'Quanto ho speso in svago questo mese?' · "
        "'Posso permettermi un acquisto da €1.200?' · "
        "'Perché la previsione del saldo scende?'_"
    )
    st.divider()

    history = st.session_state["ai_chat_history"]
    for msg in history:
        with st.chat_message("user" if msg["role"] == "user" else "assistant"):
            st.markdown(msg.get("content", ""))

    user_input = st.chat_input("Scrivi un messaggio...")
    if user_input:
        with st.chat_message("user"):
            st.markdown(user_input)

        try:
            _df_ric_ai = _load_spese_ricorrenti_df(user_email).copy()
            _oggi_ai = datetime.now()
            _kpi_ai = log.calcola_kpi_dashboard(df_mov, _oggi_ai.month, _oggi_ai.year)
            _saldo_principale = s_num("Saldo_conto_principale", 0.0)
            _saldo_secondario = s_num("Saldo_conto_secondario", 0.0)
            _kpi_ai["saldo_reale_totale"] = round(_saldo_principale + _saldo_secondario, 2)
            _kpi_ai["saldo_fineco"] = _saldo_principale
            _kpi_ai["saldo_revolut"] = _saldo_secondario
            _saldo_iniziale_ai = s_num_candidates(
                [f"saldo_iniziale_{_oggi_ai.year}", f"saldo iniziale_{_oggi_ai.year}"],
                0.0,
            )

            _risp_prec = []
            for _i in range(1, 4):
                _mp = _oggi_ai.month - _i
                _ap = _oggi_ai.year
                if _mp <= 0:
                    _mp += 12
                    _ap -= 1
                _risp_prec.append(log.calcola_kpi_dashboard(df_mov, _mp, _ap).get("risparmio_mese", 0.0))
            _kpi_ai["risparmio_medio_3mesi"] = round(sum(_risp_prec) / len(_risp_prec), 2)

            _df_prev_ai = log.previsione_saldo(
                df_mov,
                _oggi_ai.year,
                saldo_iniziale=_saldo_iniziale_ai,
                mese_riferimento=_oggi_ai.month,
            )
            if not _df_prev_ai.empty:
                _row_dic = _df_prev_ai[_df_prev_ai["MeseNum"] == 12]
                if not _row_dic.empty:
                    _row_dic_0 = _row_dic.iloc[0]
                    _kpi_ai["saldo_proiettato_dicembre"] = float(_row_dic_0["Saldo"])
                    _kpi_ai["slope_risparmio_mensile"] = float(_df_prev_ai["SlopeDelta"].iloc[0])
                    _kpi_ai["r2_previsione"] = float(_df_prev_ai["R2"].iloc[0])
                    _kpi_ai["delta_previsto_mensile"] = float(_row_dic_0.get("DeltaPrevisto") or 0.0)
                    _kpi_ai["entrate_attese_previsione"] = float(_row_dic_0.get("EntrateAttese") or 0.0)
                    _kpi_ai["uscite_attese_previsione"] = float(_row_dic_0.get("UsciteAttese") or 0.0)
                    _kpi_ai["metodo_previsione_saldo"] = str(_row_dic_0.get("Metodo") or "")

            _ob_lista: list[dict] = []
            try:
                _df_ob_ai = _load_obiettivi_df(user_email, solo_attivi=True).copy()
                if not _df_ob_ai.empty:
                    _oggi_ob_ai = datetime.now().date()
                    for _, _ob_r in _df_ob_ai.iterrows():
                        _ob_metrics_ai = _compute_goal_metrics(
                            costo=float(_ob_r["costo"]),
                            accantonato_reale=float(_ob_r.get("accantonato_reale") or 0.0),
                            risparmio_mensile_dedicato=float(_ob_r["risparmio_mensile_dedicato"]),
                            scadenza=_ob_r.get("scadenza"),
                            today=_oggi_ob_ai,
                        )
                        _ob_lista.append({
                            "nome": _ob_r["nome"],
                            "costo": _ob_metrics_ai["costo"],
                            "scadenza": (
                                str(_ob_metrics_ai["scadenza_date"])
                                if _ob_metrics_ai["scadenza_date"] is not None
                                else "nessuna"
                            ),
                            "accantonato_reale": _ob_metrics_ai["accantonato_reale"],
                            "dedicato": _ob_metrics_ai["dedicato_mensile"],
                            "mesi_rim": _ob_metrics_ai["mesi_rimanenti"],
                            "versamenti_previsti": _ob_metrics_ai["versamenti_previsti"],
                            "totale_previsto": _ob_metrics_ai["totale_previsto"],
                            "gap_attuale": _ob_metrics_ai["gap_attuale"],
                            "gap_previsto": _ob_metrics_ai["gap_previsto"],
                            "stato": _ob_metrics_ai["stato"],
                        })
                    _kpi_ai["obiettivi_utente"] = _ob_lista
            except Exception as exc:
                logger.warning("Obiettivi AI: %s", exc)

            _ctx = ai_engine.build_financial_context(
                kpi=_kpi_ai,
                df_mov=df_mov,
                df_ric=_df_ric_ai,
                df_fin=df_fin_db,
                obiettivi_utente=_ob_lista,
            )
        except Exception as exc:
            logger.error("Errore build_financial_context: %s", exc)
            _ctx = "Dati non disponibili."

        with st.chat_message("assistant"):
            with st.spinner("Sto analizzando i tuoi dati..."):
                risposta = ai_engine.chat_financial_advisor(
                    user_message=user_input,
                    financial_context=_ctx,
                    chat_history=history,
                )
            st.markdown(risposta)

        st.session_state["ai_chat_history"].append({"role": "user", "content": user_input})
        st.session_state["ai_chat_history"].append({"role": "assistant", "content": risposta})

    if history:
        st.divider()
        if st.button("🗑️ Nuova conversazione", use_container_width=False):
            st.session_state["ai_chat_history"] = []
            st.rerun()


_ai_col1, _ai_col2 = st.columns([8, 1])
with _ai_col2:
    if st.button("🤖 LUAI", use_container_width=True, help="Apri l'assistente finanziario AI"):
        _show_ai_chat()

st.divider()


@st.fragment(run_every="10s")
def _render_ai_alerts_panel(user_email_param: str, *, has_source_data: bool) -> None:
    snapshot = _ensure_ai_alerts_refresh(user_email_param, has_source_data=has_source_data)
    anomalies = snapshot.get("payload", []) if snapshot.get("has_result") else []
    expanded = bool(anomalies) or snapshot.get("status") in {"refreshing", "error"}
    gravita_cfg = {
        "info": {"bg": "rgba(59,130,246,0.12)", "border": "rgba(59,130,246,0.40)", "icon": "ℹ️"},
        "warning": {"bg": "rgba(251,146,60,0.12)", "border": "rgba(251,146,60,0.45)", "icon": "⚠️"},
        "alert": {"bg": "rgba(239,68,68,0.14)", "border": "rgba(239,68,68,0.50)", "icon": "🚨"},
    }
    default_cfg = {"bg": "rgba(59,130,246,0.12)", "border": "rgba(59,130,246,0.40)", "icon": "ℹ️"}

    with st.expander("🤖 Avvisi del tuo assistente AI", expanded=expanded):
        if snapshot.get("status") == "refreshing":
            if snapshot.get("has_result"):
                st.info("Aggiornamento automatico avvisi AI in corso. Continuo a mostrarti l'ultima analisi disponibile.")
            else:
                st.info("Prima analisi AI in preparazione. La dashboard resta utilizzabile mentre aggiorno gli avvisi.")

        if anomalies:
            for item in anomalies:
                cfg = gravita_cfg.get(item.get("gravita", "info"), default_cfg)
                titolo = item.get("titolo", item.get("categoria", ""))
                message = item.get("messaggio", item.get("testo", ""))
                st.markdown(
                    f"""<div style="
                        background:{cfg['bg']};
                        border:1px solid {cfg['border']};
                        border-radius:10px;padding:10px 14px;margin-bottom:8px;
                        font-family:'Plus Jakarta Sans',sans-serif;font-size:0.88rem;
                        color:rgba(220,230,255,0.90);">
                        {cfg['icon']} <b>{titolo}</b> — {message}
                    </div>""",
                    unsafe_allow_html=True,
                )
        elif snapshot.get("has_result") and snapshot.get("status") == "ready":
            st.success("Nessuna anomalia rilevata sui dati attuali.")
        elif snapshot.get("status") == "error":
            st.warning(snapshot.get("error") or "Aggiornamento AI non disponibile al momento.")
        elif not has_source_data:
            st.info("Aggiungi qualche movimento per attivare gli avvisi automatici dell'assistente AI.")
        else:
            st.info("L'assistente AI non ha ancora prodotto una prima analisi.")

        updated_label = _format_snapshot_ts(snapshot.get("updated_at"))
        if updated_label:
            st.caption(f"Ultimo aggiornamento avvisi AI: {updated_label}")
        elif snapshot.get("status") == "refreshing":
            started_label = _format_snapshot_ts(snapshot.get("refresh_started_at"))
            if started_label:
                st.caption(f"Aggiornamento avviato alle {started_label}")

        if snapshot.get("status") == "error" and anomalies:
            error_text = str(snapshot.get("error") or "").strip()
            if error_text:
                st.caption(f"Ultimo tentativo di refresh non riuscito: {error_text}")


# ---------------------------------------------------------------------------
# Tab layout
# ---------------------------------------------------------------------------

tab_home, tab_charts, tab_assets, tab_debts, tab_admin, tab_settings = st.tabs([
    "🏠 HOME", "📈 ANALISI", "💰 PATRIMONIO", "🔗 DEBITI", "📝 TRANSAZIONI", "⚙️ IMPOSTAZIONI"
])

if st.session_state.get("totp_setup_active"):
    _focus_streamlit_tab("⚙️ IMPOSTAZIONI")
 
# ============================================================
# TAB 1 — HOME
# ============================================================
with tab_home:
    st.markdown("<div class='section-title'>HOME</div>", unsafe_allow_html=True)
    _render_ai_alerts_panel(user_email, has_source_data=not df_mov.empty)

    try:
        _df_ob_home = _load_obiettivi_df(user_email, solo_attivi=True).copy()
    except Exception:
        _df_ob_home = pd.DataFrame()

    if not _df_ob_home.empty:
        _oggi_home = date.today()
        _ob_gia_coperti = []
        _ob_in_linea = []
        _ob_a_rischio = []
        _ob_falliti = []

        for _, _obh in _df_ob_home.iterrows():
            _obh_nome = _obh["nome"]
            _ob_metrics = _compute_goal_metrics(
                costo=float(_obh["costo"]),
                accantonato_reale=float(_obh.get("accantonato_reale") or 0.0),
                risparmio_mensile_dedicato=float(_obh["risparmio_mensile_dedicato"]),
                scadenza=_obh.get("scadenza"),
                today=_oggi_home,
            )

            if _ob_metrics["coperto_oggi"]:
                _ob_gia_coperti.append({
                    "nome": _obh_nome,
                    "costo": _ob_metrics["costo"],
                    "accantonato": _ob_metrics["accantonato_reale"],
                    "id": int(_obh["id"]),
                })
                continue

            if _ob_metrics["scadenza_date"] is None:
                continue

            if _ob_metrics["coperto_previsto"]:
                _ob_in_linea.append({
                    "nome": _obh_nome,
                    "costo": _ob_metrics["costo"],
                    "accantonato": _ob_metrics["accantonato_reale"],
                    "totale_previsto": _ob_metrics["totale_previsto"],
                    "scadenza": _ob_metrics["scadenza_label"],
                })
            elif _ob_metrics["giorni_rimanenti"] is not None and _ob_metrics["giorni_rimanenti"] < 0:
                _ob_falliti.append({
                    "nome": _obh_nome,
                    "costo": _ob_metrics["costo"],
                    "gap": _ob_metrics["gap_attuale"],
                    "scadenza": _ob_metrics["scadenza_date"].strftime("%d/%m/%Y"),
                    "id": int(_obh["id"]),
                })
            elif (
                _ob_metrics["giorni_rimanenti"] is not None
                and _ob_metrics["giorni_rimanenti"] <= 60
                and _ob_metrics["gap_previsto"] > _ob_metrics["costo"] * 0.30
            ):
                _ob_a_rischio.append({
                    "nome": _obh_nome,
                    "costo": _ob_metrics["costo"],
                    "accantonato": _ob_metrics["accantonato_reale"],
                    "gap": _ob_metrics["gap_previsto"],
                    "giorni": _ob_metrics["giorni_rimanenti"],
                    "scadenza": _ob_metrics["scadenza_date"].strftime("%d/%m/%Y"),
                })

        if _ob_gia_coperti or _ob_in_linea or _ob_a_rischio or _ob_falliti:
            with st.expander("🎯 Aggiornamenti sui tuoi obiettivi", expanded=True):
                for _obc in _ob_gia_coperti:
                    st.markdown(
                        f"""<div style="
                            background:rgba(16,217,138,0.10);
                            border:1px solid rgba(16,217,138,0.40);
                            border-radius:10px;padding:10px 14px;margin-bottom:8px;
                            font-family:'Plus Jakarta Sans',sans-serif;font-size:0.88rem;
                            color:rgba(220,230,255,0.90);">
                            🏦 <b>{_obc['nome']}</b> — Obiettivo già coperto con risparmio reale.
                            Hai già accantonato <b>{eur2(_obc['accantonato'])}</b>
                            su un target di <b>{eur2(_obc['costo'])}</b>.
                            Ricordati di segnarlo come completato nel tab Analisi.
                        </div>""",
                        unsafe_allow_html=True,
                    )

                for _obi in _ob_in_linea:
                    st.markdown(
                        f"""<div style="
                            background:rgba(79,142,240,0.10);
                            border:1px solid rgba(79,142,240,0.40);
                            border-radius:10px;padding:10px 14px;margin-bottom:8px;
                            font-family:'Plus Jakarta Sans',sans-serif;font-size:0.88rem;
                            color:rgba(220,230,255,0.90);">
                            🎯 <b>{_obi['nome']}</b> — In linea con il piano.
                            Hai già accantonato <b>{eur2(_obi['accantonato'])}</b> e,
                            continuando con il dedicato mensile, arriverai a
                            <b>{eur2(_obi['totale_previsto'])}</b> entro <b>{_obi['scadenza']}</b>.
                        </div>""",
                        unsafe_allow_html=True,
                    )

                for _obar in _ob_a_rischio:
                    st.markdown(
                        f"""<div style="
                            background:rgba(251,146,60,0.10);
                            border:1px solid rgba(251,146,60,0.42);
                            border-radius:10px;padding:10px 14px;margin-bottom:8px;
                            font-family:'Plus Jakarta Sans',sans-serif;font-size:0.88rem;
                            color:rgba(220,230,255,0.90);">
                            ⚠️ <b>{_obar['nome']}</b> — A rischio!
                            Mancano <b>{_obar['giorni']} giorni</b> alla scadenza
                            ({_obar['scadenza']}) ma il gap residuo è ancora
                            <b>{eur2(_obar['gap'])}</b>.
                            Al momento hai accantonato <b>{eur2(_obar['accantonato'])}</b>.
                            Considera di aumentare il risparmio mensile dedicato.
                        </div>""",
                        unsafe_allow_html=True,
                    )

                for _obf in _ob_falliti:
                    _obf_cols = st.columns([5, 1.4])
                    with _obf_cols[0]:
                        st.markdown(
                            f"""<div style="
                                background:rgba(239,68,68,0.10);
                                border:1px solid rgba(239,68,68,0.45);
                                border-radius:10px;padding:10px 14px;
                                font-family:'Plus Jakarta Sans',sans-serif;font-size:0.88rem;
                                color:rgba(220,230,255,0.90);">
                                ❌ <b>{_obf['nome']}</b> — Scadenza superata ({_obf['scadenza']}).
                                Gap non colmato: <b>{eur2(_obf['gap'])}</b>.
                                Puoi aggiornare la scadenza o eliminare l'obiettivo dal tab Analisi.
                            </div>""",
                            unsafe_allow_html=True,
                        )
                    with _obf_cols[1]:
                        if st.button("🗑️ Elimina", key=f"ob_home_del_{_obf['id']}", use_container_width=True):
                            db.elimina_obiettivo(_obf["id"], user_email=user_email)
                            _invalidate_runtime_caches(obiettivi=True)
                            st.rerun()

    mesi_labels = list(MONTH_SHORT.values())
    _perc_att = _get_percentuali_budget_cached(user_email)
 
    c1, c2 = st.columns([1.35, 1.2])
 
    with c1:
        st.markdown("<div class='panel-title'>📊 Budget di spesa (50/30/20)</div>", unsafe_allow_html=True)
        if not df_budget.empty:
            cat_order = list(_perc_att.keys())
            _y_order    = list(reversed(mesi_labels))   # ["Dic","Nov",...,"Gen"]
            fig_budget  = go.Figure()

            for cat in cat_order:
                df_cat   = df_budget[df_budget["Categoria"] == cat].set_index("Mese").reindex(mesi_labels)
                budget_c = df_cat["BudgetCategoria"].fillna(budget_base * _perc_att[cat])
                speso    = df_cat["Speso"].fillna(0)
                residuo  = (budget_c - speso).clip(lower=0)
                spesa_ok = speso.where(speso <= budget_c, budget_c)
                extra    = (speso - budget_c).clip(lower=0)
                col_bright, col_dark = Colors.BUDGET_COLORS[cat]
                fig_budget.add_bar(
                    x=list(residuo), y=mesi_labels, orientation="h", width=0.70,
                    name=f"{cat}", marker_color=col_bright,
                    marker_cornerradius=4, showlegend=True,
                    text=[f"{eur0(v)}" if v >= 1 else "" for v in residuo],
                    textposition="inside", insidetextanchor="middle",
                    textfont=dict(color="#0B1020", size=13, weight="bold",family="'Plus Jakarta Sans',sans-serif"),
                    hovertemplate=f"<b>{cat} residuo</b>: €%{{x:.0f}}<extra></extra>",
                )
                fig_budget.add_bar(
                    x=list(spesa_ok), y=mesi_labels, orientation="h", width=0.70,
                    name=cat, marker_color=col_dark,
                    marker_cornerradius=4, showlegend=False,
                    text=[f"€ {int(v):,}".replace(",", ".") if v >= 1 else "" for v in spesa_ok],
                    textposition="inside", insidetextanchor="middle",
                    textfont=dict(color="#ffffff", size=18, weight="bold",family="'Plus Jakarta Sans',sans-serif"),
                    hovertemplate=f"<b>{cat} speso</b>: €%{{x:,.0f}}<extra></extra>",
                )
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
            st.info("Imposta 'budget mensile base' nelle impostazioni rapide.")
 
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
        ordine_mesi_prev = [MONTH_SHORT.get(m, str(m)) for m in range(1, 13)]
        df_reale = df_prev[df_prev["Tipo"] == "Reale"].sort_values("MeseNum")
        ultimo_punto_reale = df_reale.iloc[[-1]] if not df_reale.empty else None
        _tipos = df_prev["Tipo"].unique()
        _colors_prev = {"Reale": "#4f8ef0", "Previsione": "#f5a623"}
        fig_prev = go.Figure()

        _df_band = df_prev[df_prev["Tipo"] == "Previsione"][["Mese", "MeseNum", "SaldoMin", "SaldoMax"]].copy()
        _df_band = _df_band.sort_values("MeseNum")
        if not _df_band.empty and _df_band["SaldoMin"].notna().any():
            if ultimo_punto_reale is not None:
                _anchor_band = ultimo_punto_reale[["Mese", "MeseNum", "Saldo"]].copy()
                _anchor_band["SaldoMin"] = _anchor_band["Saldo"]
                _anchor_band["SaldoMax"] = _anchor_band["Saldo"]
                _df_band = pd.concat(
                    [_anchor_band[["Mese", "MeseNum", "SaldoMin", "SaldoMax"]], _df_band],
                    ignore_index=True,
                )
            fig_prev.add_trace(go.Scatter(
                x=_df_band["Mese"],
                y=_df_band["SaldoMax"],
                mode="lines",
                line=dict(width=0),
                hoverinfo="skip",
                showlegend=False,
            ))
            fig_prev.add_trace(go.Scatter(
                x=_df_band["Mese"],
                y=_df_band["SaldoMin"],
                mode="lines",
                line=dict(color=hex_to_rgba(_colors_prev["Previsione"], 0.50), width=1, dash="dot"),
                fill="tonexty",
                fillcolor=hex_to_rgba(_colors_prev["Previsione"], 0.14),
                name="Intervallo ±1σ",
                hovertemplate="Limite stimato: € %{y:,.0f}<extra></extra>",
            ))

        for _tipo in _tipos:
            _df_t = df_prev[df_prev["Tipo"] == _tipo].copy().sort_values("MeseNum")
            if _tipo == "Previsione" and ultimo_punto_reale is not None:
                _df_t = pd.concat([ultimo_punto_reale, _df_t]).drop_duplicates(subset=["Mese"], keep="last")
                _df_t = _df_t.sort_values("MeseNum")
            _color = _colors_prev.get(str(_tipo), "#f5a623")
            _y = _df_t["Saldo"].tolist()
            fig_prev.add_trace(go.Scatter(
                x=_df_t["Mese"],
                y=_y,
                name=str(_tipo),
                mode="lines+markers+text",
                line=dict(color=_color, width=3, dash="dash" if _tipo == "Previsione" else "solid"),
                fill="tozeroy" if _tipo == "Reale" else None,
                fillcolor=hex_to_rgba(_color, 0.05) if _tipo == "Reale" else None,
                marker=dict(color=_color, size=6),
                text=[eur0(v) for v in _y],
                textposition="top center",
                textfont=dict(size=10, color=_color),
            ))
        fig_prev.update_xaxes(categoryorder="array", categoryarray=ordine_mesi_prev)
        fig_prev.update_yaxes(tickprefix="€ ", tickformat=",.0f")
        style_fig(fig_prev, height=320, show_legend=True)
        st.plotly_chart(fig_prev, use_container_width=True, config=PLOTLY_CONFIG)

        _row_dic = df_prev[df_prev["MeseNum"] == 12]
        if not _row_dic.empty and not df_reale.empty:
            _mese_cutoff = int(df_reale["MeseNum"].max())
            _row_dic_0 = _row_dic.iloc[0]
            _saldo_osservato_prev = float(df_reale["Saldo"].iloc[-1])
            _saldo_dicembre_prev = float(_row_dic_0["Saldo"])
            _delta_previsto = float(_row_dic_0.get("DeltaPrevisto") or 0.0)
            _entrate_attese_prev = float(_row_dic_0.get("EntrateAttese") or 0.0)
            _uscite_attese_prev = float(_row_dic_0.get("UsciteAttese") or 0.0)
            _metodo_prev = str(_row_dic_0.get("Metodo") or "")
            _insight_prev = _genera_insight_previsione(
                anno=int(anno_sel),
                mese_cutoff=_mese_cutoff,
                saldo_osservato=_saldo_osservato_prev,
                saldo_dicembre=_saldo_dicembre_prev,
                delta_previsto=_delta_previsto,
                entrate_attese=_entrate_attese_prev,
                uscite_attese=_uscite_attese_prev,
                metodo=_metodo_prev,
            )
            if _insight_prev:
                st.caption(_insight_prev)

            _ai_key = f"_forecast_ai_expl_{anno_sel}_{_mese_cutoff}"
            _ai_btn_col, _ai_txt_col = st.columns([1.2, 4.8], gap="small")
            with _ai_btn_col:
                if st.button("Spiega con LUAI", key=f"btn{_ai_key}", use_container_width=True):
                    with st.spinner("Sto leggendo la previsione..."):
                        st.session_state[_ai_key] = _genera_spiegazione_previsione_ai(
                            anno=int(anno_sel),
                            mese_cutoff=_mese_cutoff,
                            saldo_osservato=_saldo_osservato_prev,
                            saldo_dicembre=_saldo_dicembre_prev,
                            delta_previsto=_delta_previsto,
                            entrate_attese=_entrate_attese_prev,
                            uscite_attese=_uscite_attese_prev,
                            metodo=_metodo_prev,
                        )
            with _ai_txt_col:
                _ai_text = st.session_state.get(_ai_key)
                if _ai_text:
                    st.caption(_ai_text)

            if _mese_cutoff < 12:
                with st.expander("🧪 Simula saldo what-if", expanded=False):
                    st.caption("Questa simulazione non modifica la previsione base. Serve solo a confrontare uno scenario alternativo.")
                    _mese_start_default = min(max(_mese_cutoff + 1, 1), 12)
                    _what_if_key = f"_what_if_forecast_{anno_sel}"
                    _what_if_saved = st.session_state.get(_what_if_key, {})
                    _what_if_options = list(range(_mese_start_default, 13))
                    _what_if_saved_month = int(_what_if_saved.get("mese_inizio", _mese_start_default))
                    if _what_if_saved_month not in _what_if_options:
                        _what_if_saved_month = _mese_start_default
                    _what_if_index = _what_if_options.index(_what_if_saved_month)

                    with st.form(key=f"form_what_if_{anno_sel}"):
                        _wf_cols = st.columns(4, gap="small")
                        _wf_mese = _wf_cols[0].selectbox(
                            "Da quale mese?",
                            options=_what_if_options,
                            index=_what_if_index,
                            format_func=lambda m: MONTH_NAMES.get(int(m), str(m)),
                        )
                        _wf_entrate = _wf_cols[1].number_input(
                            "Entrate mensili scenario (€)",
                            min_value=0.0,
                            value=float(_what_if_saved.get("entrate_attese", _entrate_attese_prev)),
                            step=50.0,
                        )
                        _wf_uscite = _wf_cols[2].number_input(
                            "Uscite mensili scenario (€)",
                            min_value=0.0,
                            value=float(_what_if_saved.get("uscite_attese", _uscite_attese_prev)),
                            step=50.0,
                        )
                        _wf_una_tantum = _wf_cols[3].number_input(
                            "Una tantum al mese di avvio (€)",
                            value=float(_what_if_saved.get("una_tantum", 0.0)),
                            step=100.0,
                            help="Usa un valore positivo per un bonus, negativo per una spesa straordinaria.",
                        )
                        _wf_submit = st.form_submit_button("Aggiorna scenario", use_container_width=True)

                    if _wf_submit:
                        st.session_state[_what_if_key] = {
                            "mese_inizio": int(_wf_mese),
                            "entrate_attese": float(_wf_entrate),
                            "uscite_attese": float(_wf_uscite),
                            "una_tantum": float(_wf_una_tantum),
                        }

                    _what_if_params = st.session_state.get(_what_if_key)
                    if _what_if_params:
                        _df_scenario = _simula_scenario_previsione(
                            df_prev=df_prev,
                            mese_inizio=int(_what_if_params["mese_inizio"]),
                            entrate_attese=float(_what_if_params["entrate_attese"]),
                            uscite_attese=float(_what_if_params["uscite_attese"]),
                            una_tantum=float(_what_if_params.get("una_tantum", 0.0)),
                        )
                        if not _df_scenario.empty:
                            _scenario_dic = _df_scenario[_df_scenario["MeseNum"] == 12]
                            if not _scenario_dic.empty:
                                _saldo_dic_scenario = float(_scenario_dic["SaldoScenario"].iloc[0])
                                _delta_vs_base = _saldo_dic_scenario - _saldo_dicembre_prev

                                fig_wf = go.Figure()
                                fig_wf.add_trace(go.Scatter(
                                    x=df_prev["Mese"],
                                    y=df_prev["Saldo"],
                                    name="Previsione base",
                                    mode="lines+markers",
                                    line=dict(color="#f5a623", width=3, dash="dash"),
                                    marker=dict(color="#f5a623", size=6),
                                ))
                                fig_wf.add_trace(go.Scatter(
                                    x=_df_scenario["Mese"],
                                    y=_df_scenario["SaldoScenario"],
                                    name="Scenario",
                                    mode="lines+markers",
                                    line=dict(color="#10d98a", width=3),
                                    marker=dict(color="#10d98a", size=6),
                                ))
                                fig_wf.update_xaxes(categoryorder="array", categoryarray=ordine_mesi_prev)
                                fig_wf.update_yaxes(tickprefix="€ ", tickformat=",.0f")
                                show_chart(fig_wf, height=280, show_legend=True)

                                st.caption(
                                    f"Scenario da {MONTH_NAMES.get(int(_what_if_params['mese_inizio']), _what_if_params['mese_inizio'])}: "
                                    f"saldo previsto a dicembre {eur2(_saldo_dic_scenario)} "
                                    f"({eur2(_delta_vs_base, signed=True)} rispetto alla previsione base)."
                                )
    else:
        st.info("Dati insufficienti per la previsione saldo.")

    st.divider()
    st.markdown(
        """
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
          <span style="font-size:18px;">🎯</span>
          <span class="section-title" style="margin-bottom:0;">OBIETTIVI FINANZIARI</span>
        </div>
        <p style="color:rgba(220,200,255,0.50);font-size:12px;margin-bottom:16px;">
          Definisci i tuoi traguardi economici e monitora sia l'accantonato reale,
          sia la proiezione futura basata sul risparmio mensile dedicato.
          Gli obiettivi vengono utilizzati anche dall'assistente AI per risponderti in modo più preciso.
        </p>
        """,
        unsafe_allow_html=True,
    )

    _df_ob = _load_obiettivi_df(user_email, solo_attivi=False).copy()

    with st.expander("➕ Aggiungi nuovo obiettivo", expanded=False):
        with st.form("form_nuovo_obiettivo", clear_on_submit=True):
            _oc1, _oc2 = st.columns(2)
            _ob_nome = _oc1.text_input("Descrizione *", placeholder="Es. Vacanza Giappone")
            _ob_costo = _oc2.number_input("Costo target (€) *", min_value=0.0, step=50.0, format="%.2f")
            _oc3, _oc4, _oc5, _oc6, _oc7 = st.columns(5)
            _ob_senza_scadenza = _oc3.checkbox("Senza scadenza", value=False)
            _ob_scad = None if _ob_senza_scadenza else _oc4.date_input("Scadenza", min_value=date.today())
            _ob_acc = _oc5.number_input(
                "Accantonato reale (€)",
                min_value=0.0,
                step=50.0,
                format="%.2f",
                help="Quanto hai già realmente messo da parte per questo obiettivo",
            )
            _ob_ded = _oc6.number_input(
                "Risparmio mensile dedicato (€)",
                min_value=0.0,
                step=10.0,
                format="%.2f",
                help="Quanto prevedi di dedicare ogni mese da oggi in avanti",
            )
            _ob_note = _oc7.text_input("Note", placeholder="Opzionale")

            if st.form_submit_button("💾 Salva obiettivo", use_container_width=True):
                if not _ob_nome or _ob_costo <= 0:
                    st.error("Descrizione e costo sono obbligatori.")
                else:
                    _new_id = db.salva_obiettivo(
                        nome=_ob_nome,
                        costo=_ob_costo,
                        scadenza=_ob_scad,
                        accantonato_reale=_ob_acc,
                        risparmio_mensile_dedicato=_ob_ded,
                        note=_ob_note,
                        user_email=user_email,
                    )
                    if _new_id:
                        _invalidate_runtime_caches(obiettivi=True)
                        st.success(f"✅ Obiettivo '{_ob_nome}' salvato.")
                        st.rerun()
                    else:
                        st.error("Errore nel salvataggio dell'obiettivo.")

    if _df_ob.empty:
        st.info("Nessun obiettivo ancora. Aggiungine uno con il form qui sopra.")
    else:
        _oggi_ob = date.today()
        _df_attivi = _df_ob[_df_ob["completato"] == False].copy()
        _df_compl = _df_ob[_df_ob["completato"] == True].copy()

        for _, _ob_row in _df_attivi.iterrows():
            _ob_id = int(_ob_row["id"])
            _ob_name = _ob_row["nome"]
            _ob_metrics = _compute_goal_metrics(
                costo=float(_ob_row["costo"]),
                accantonato_reale=float(_ob_row.get("accantonato_reale") or 0.0),
                risparmio_mensile_dedicato=float(_ob_row["risparmio_mensile_dedicato"]),
                scadenza=_ob_row["scadenza"],
                today=_oggi_ob,
            )
            _ob_cost = _ob_metrics["costo"]
            _ob_acc_v = _ob_metrics["accantonato_reale"]
            _ob_ded_v = _ob_metrics["dedicato_mensile"]
            _ob_note_v = str(_ob_row.get("note") or "")
            _ob_scad_v = _ob_row["scadenza"]
            _scad_lbl = _ob_metrics["scadenza_label"]
            _mesi_rim = _ob_metrics["mesi_rimanenti"]
            _perc_reale = _ob_metrics["perc_reale"]
            _perc_prev = _ob_metrics["perc_previsto"]
            _tot_prev = _ob_metrics["totale_previsto"]
            _gap_att = _ob_metrics["gap_attuale"]
            _gap_prev = _ob_metrics["gap_previsto"]
            _vers_prev = _ob_metrics["versamenti_previsti"]
            _coperto_oggi = _ob_metrics["coperto_oggi"]
            _coperto_prev = _ob_metrics["coperto_previsto"]
            _gap_icon = "🟢" if _coperto_prev else ("🟡" if _gap_prev < _ob_cost * 0.3 else "🔴")

            with st.container(border=True):
                _hc1, _hc2 = st.columns([6, 2])
                with _hc1:
                    st.markdown(f"**{_ob_name}**")
                    _cap_parts = [
                        f"Target: **{eur2(_ob_cost)}**",
                        f"Scadenza: **{_scad_lbl}**",
                        f"Accantonato: **{eur2(_ob_acc_v)}**",
                        f"Dedicato: **{eur2(_ob_ded_v)}/mese**",
                    ]
                    if _ob_note_v:
                        _cap_parts.append(f"_{_ob_note_v}_")
                    st.caption(" · ".join(_cap_parts))
                with _hc2:
                    if _coperto_oggi:
                        _gap_lbl = "🏦 Già finanziato"
                    elif _coperto_prev:
                        _gap_lbl = "✅ In linea"
                    elif _mesi_rim is None:
                        _gap_lbl = f"🟡 Gap attuale: {eur2(_gap_att)}"
                    else:
                        _gap_lbl = f"{_gap_icon} Gap previsto: {eur2(_gap_prev)}"
                    st.markdown(f"<div style='text-align:right;font-weight:600;'>{_gap_lbl}</div>", unsafe_allow_html=True)
                    if _mesi_rim is not None:
                        st.markdown(
                            f"<div style='text-align:right;font-size:0.80em;color:rgba(180,200,240,0.55);'>{_mesi_rim} mesi rimanenti · versamenti previsti {eur2(_vers_prev)}</div>",
                            unsafe_allow_html=True,
                        )

                st.progress(
                    int(_perc_reale),
                    text=f"{_perc_reale:.0f}% del target già coperto dall'accantonato reale",
                )
                if _mesi_rim is not None:
                    st.progress(
                        int(_perc_prev),
                        text=f"{_perc_prev:.0f}% previsto a scadenza con il piano attuale",
                    )
                    if _coperto_prev:
                        st.caption(
                            f"Totale previsto entro la scadenza: {eur2(_tot_prev)}. "
                            f"Gap attuale: {eur2(_gap_att)}."
                        )
                    else:
                        st.caption(
                            f"Totale previsto entro la scadenza: {eur2(_tot_prev)}. "
                            f"Gap attuale: {eur2(_gap_att)} · gap previsto: {eur2(_gap_prev)}."
                        )
                else:
                    st.caption(
                        f"Gap attuale: {eur2(_gap_att)}. "
                        "Senza scadenza la proiezione futura non viene stimata automaticamente."
                    )

                _ac1, _ac2, _ac3, _ = st.columns([1.5, 1.5, 1.5, 5])
                if _ac1.button("✅ Completato", key=f"ob_compl_{_ob_id}", use_container_width=True):
                    db.segna_obiettivo_completato(_ob_id, user_email=user_email)
                    _invalidate_runtime_caches(obiettivi=True)
                    st.rerun()
                if _ac2.button("🗑️ Elimina", key=f"ob_del_{_ob_id}", use_container_width=True):
                    db.elimina_obiettivo(_ob_id, user_email=user_email)
                    _invalidate_runtime_caches(obiettivi=True)
                    st.rerun()
                if _ac3.button("✏️ Modifica", key=f"ob_edit_btn_{_ob_id}", use_container_width=True):
                    st.session_state[f"ob_edit_open_{_ob_id}"] = not st.session_state.get(f"ob_edit_open_{_ob_id}", False)

                if st.session_state.get(f"ob_edit_open_{_ob_id}", False):
                    with st.form(f"form_ob_edit_{_ob_id}"):
                        _ec1, _ec2 = st.columns(2)
                        _e_nome = _ec1.text_input("Descrizione", value=_ob_name)
                        _e_costo = _ec2.number_input("Costo (€)", value=_ob_cost, step=50.0, format="%.2f")
                        _ec3, _ec4, _ec5, _ec6, _ec7 = st.columns(5)
                        _e_senza_scad = _ec3.checkbox("Senza scadenza", value=pd.isna(_ob_scad_v), key=f"ob_edit_noscad_{_ob_id}")
                        _e_scad = None if _e_senza_scad else _ec4.date_input(
                            "Scadenza",
                            value=pd.to_datetime(_ob_scad_v).date() if pd.notna(_ob_scad_v) else date.today(),
                            key=f"ob_edit_scad_{_ob_id}",
                        )
                        _e_acc = _ec5.number_input("Accantonato reale (€)", value=_ob_acc_v, step=50.0, format="%.2f")
                        _e_ded = _ec6.number_input("Dedicato (€/mese)", value=_ob_ded_v, step=10.0, format="%.2f")
                        _e_note = _ec7.text_input("Note", value=_ob_note_v)
                        if st.form_submit_button("💾 Aggiorna"):
                            db.aggiorna_obiettivo(
                                _ob_id,
                                _e_nome,
                                _e_costo,
                                _e_scad,
                                _e_acc,
                                _e_ded,
                                _e_note,
                                user_email=user_email,
                            )
                            _invalidate_runtime_caches(obiettivi=True)
                            st.session_state[f"ob_edit_open_{_ob_id}"] = False
                            st.rerun()

        if not _df_compl.empty:
            with st.expander(f"🏆 Obiettivi completati ({len(_df_compl)})", expanded=False):
                for _, _cr in _df_compl.iterrows():
                    _data_compl = pd.to_datetime(_cr["aggiornato_il"]).strftime("%d/%m/%Y")
                    st.markdown(
                        f"~~{_cr['nome']}~~ — {eur2(float(_cr['costo']))} · completato il {_data_compl}"
                    )
 
 
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
                f"""<div style="background:rgba(255,255,255,0.04);backdrop-filter:blur(16px) saturate(150%);-webkit-backdrop-filter:blur(16px) saturate(150%);border:1px solid rgba(92,118,178,0.22);
                border-radius:16px;padding:22px 18px 18px;text-align:center;
                box-shadow:0 4px 28px rgba(0,0,0,0.45),0 0 32px {_glow};position:relative;overflow:hidden;">
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
    _fp_title_col, _fp_badge_col = st.columns([3, 2])
    with _fp_title_col:
        st.markdown("<div class='panel-title'>🏦 Fondo Pensione</div>", unsafe_allow_html=True)
    with _fp_badge_col:
        if _quota_live and _quota_live > 0:
            st.markdown(
                f"<div style='text-align:right'>"
                f"{badge_html(f'🟢 NAV {_quota_live:.3f} € · {_quota_data}', 'badge-red')}"
                f"<div style='font-size:0.72rem;color:rgba(180,200,240,0.40);margin-top:2px;'>"
                f"PreviDoc/Teleborsa · {_quota_ts}</div></div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div style='text-align:right'>{badge_html('⚠️ Quota da DB · aggiornamento offline', 'badge-red')}</div>",
                unsafe_allow_html=True,
            )
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
                f"""<div style="background:rgba(255,255,255,0.04);backdrop-filter:blur(16px) saturate(150%);-webkit-backdrop-filter:blur(16px) saturate(150%);border:1px solid rgba(92,118,178,0.22);
                border-radius:16px;padding:22px 18px 18px;text-align:center;
                box-shadow:0 4px 28px rgba(0,0,0,0.45),0 0 32px {_glow};position:relative;overflow:hidden;">
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
        st.info("Imposta codice fondo e quote nelle impostazioni rapide per visualizzare il fondo pensione.")
 
    st.divider()
 
    # Composizione portafoglio
    r1, r2 = st.columns(2)
    with r1:
        st.markdown("<div class='panel-title'>Composizione portafoglio</div>", unsafe_allow_html=True)
        comp = log.composizione_portafoglio(
            float(saldo_disponibile), float(Saldo_conto_secondario_set),
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
                f"""<div style="background:rgba(255,255,255,0.04);backdrop-filter:blur(16px) saturate(150%);-webkit-backdrop-filter:blur(16px) saturate(150%);border:1px solid rgba(92,118,178,0.22);
                border-radius:16px;padding:22px 18px 18px;text-align:center;
                box-shadow:0 4px 28px rgba(0,0,0,0.45),0 0 32px {_glow};position:relative;overflow:hidden;">
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
                        _td(
                            f"<strong>{escape(str(row['Nome']))}</strong>",
                            color=Colors.TEXT,
                            weight=600,
                            title=str(row["Nome"]),
                        ),
                        _td(f"<span style='white-space:nowrap'>{eur2(row['Rata'])}</span>",    color=Colors.RED,  mono=True, weight=600),
                        _td(f"<span style='white-space:nowrap'>{eur2(row['Residuo'])}</span>", color=Colors.TEXT, mono=True),
                        _td(f"<span style='white-space:nowrap'>{perc:.1f}%</span>",            color=perc_color,  mono=True, align="center"),
                        _td(str(mesi_r),                                                        color=mesi_color,  mono=True, align="center"),
                    ]))
                st.markdown(scroll_table(
                    title="Riepilogo finanziamenti", right_html="",
                    columns=[("Nome","center"),("Rata","center"),("Resid.","center"),("%","center"),("Mesi","center")],
                    widths=[0.8, 0.8, 0.90, 0.60, 0.60],
                    rows_html=debt_rows, height_px=300,
                    min_table_width_px=0,
                    shell_class="reg-html-compact reg-html-fin-summary",
                ), unsafe_allow_html=True)
            else:
                st.info("Nessun dettaglio rate disponibile.")

# ============================================================
# TAB 5 — TRANSAZIONI
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
        _struttura_cat = _get_struttura_categorie_cached(user_email)
        categoria_scelta  = col_cat.selectbox("Categoria", list(_struttura_cat.keys()), key="reg_categoria")
        dettagli_filtrati = _struttura_cat[categoria_scelta]
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
                    _invalidate_runtime_caches(movimenti=True)
                    st.session_state["_banner_mov"] = True
                    for k in ["reg_importo", "reg_note", "reg_data"]:
                        st.session_state.pop(k, None)
                    st.rerun()
                except Exception as exc:
                    logger.error("Errore registrazione movimento per %s: %s", user_email, exc)
                    st.error("Errore durante il salvataggio del movimento. Riprova.")
        if col_ann.button("Annulla", key="btn_annulla_mov", use_container_width=True):
            for k in ["reg_importo", "reg_note", "reg_data"]:
                st.session_state.pop(k, None)
            st.rerun()
 
    # ── Spese ricorrenti ──
    with st.container(border=True):
        df_ric_view = _load_spese_ricorrenti_df(user_email).copy()
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
                        _invalidate_runtime_caches(ricorrenti=True)
                        for k in ["ric_desc", "ric_importo", "ric_giorno"]:
                            st.session_state.pop(k, None)
                        st.session_state["_banner_ric"] = True
                        st.rerun()
                    except Exception as exc:
                        logger.error("Errore salvataggio spesa ricorrente per %s: %s", user_email, exc)
                        st.error("Errore durante il salvataggio della spesa ricorrente. Riprova.")
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
                widths=[0.45, 2.6, 1.1, 1.25, 0.7, 1.1, 1.8],
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
                    _invalidate_runtime_caches(ricorrenti=True)
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
                        _invalidate_runtime_caches(finanziamenti=True)
                        for k in ["fin_nome","fin_capitale","fin_taeg","fin_durata","fin_rate","fin_giorno"]:
                            st.session_state.pop(k, None)
                        st.success("✅ Finanziamento salvato!")
                        st.rerun()
                    except Exception as exc:
                        logger.error("Errore salvataggio finanziamento per %s: %s", user_email, exc)
                        st.error("Errore durante il salvataggio del finanziamento. Riprova.")
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
                columns=[("Nome","center"),("Capitale","center"),("TAEG","center"),("Durata","center"),("Inizio","center"),("Rata","center"),("Rate pag.","center")],
                widths=[2.0, 1.2, 0.9, 0.8, 1.1, 1.5, 1.5],
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
                    _invalidate_runtime_caches(finanziamenti=True)
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
                _invalidate_runtime_caches(movimenti=True)
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
# ============================================================
# TAB 6 — IMPOSTAZIONI
# ============================================================
# Colori per categoria (usati nei badge e nelle preview card budget)
_CAT_COLORS = {
    "NECESSITÀ":   {"accent": "#4f8ef0", "bg": "rgba(79,142,240,0.12)",  "card": "rgba(79,142,240,0.08)"},
    "SVAGO":       {"accent": "#f472b6", "bg": "rgba(244,114,182,0.12)", "card": "rgba(244,114,182,0.08)"},
    "INVESTIMENTI":{"accent": "#10d98a", "bg": "rgba(16,217,138,0.12)",  "card": "rgba(16,217,138,0.08)"},
}

with tab_settings:
    st.markdown(
        "<div style='display:flex;align-items:center;gap:10px;margin-bottom:4px;'>"
        "<span style='font-size:1.4rem;'>⚙️</span>"
        "<span style='font-size:1.25rem;font-weight:700;color:#dde6f5;'>Impostazioni</span>"
        "</div>"
        "<p style='font-size:0.88rem;color:#5a6f8c;margin-bottom:20px;'>"
        "Personalizza le categorie di spesa, la distribuzione del budget e gestisci il backup dei tuoi dati."
        "</p>",
        unsafe_allow_html=True,
    )

    # ── Feedback banner (add/remove) ──────────────────────────────────────────
    if st.session_state.get("_impost_ok"):
        st.success(st.session_state.pop("_impost_ok"))
    if st.session_state.get("_impost_err"):
        st.error(st.session_state.pop("_impost_err"))

    # ── Gestione Voci di Spesa ────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(
            "<div style='display:flex;align-items:center;gap:8px;margin-bottom:6px;'>"
            "<span style='font-size:1.1rem;'>🗂️</span>"
            "<span style='font-size:0.97rem;font-weight:700;color:#dde6f5;'>Gestione Voci di Spesa</span>"
            "</div>"
            "<p style='font-size:0.82rem;color:#5a6f8c;margin-bottom:16px;'>"
            "Aggiungi o rimuovi voci di dettaglio per ogni categoria. "
            "Le voci <em>predefinite</em> non possono essere rimosse."
            "</p>",
            unsafe_allow_html=True,
        )

        # Selezione categoria via radio orizzontale
        st.markdown("<div style='font-size:0.85rem;color:#8ba3c7;margin-bottom:6px;'>Seleziona categoria</div>", unsafe_allow_html=True)
        _cat_sel = st.radio(
            "cat_radio",
            CATEGORIE_MODIFICABILI,
            horizontal=True,
            label_visibility="collapsed",
            key="impost_cat_radio",
        )

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        # Carica struttura e custom per la categoria selezionata
        _struttura_full = _get_struttura_categorie_cached(user_email)
        _default_voci    = STRUTTURA_CATEGORIE.get(_cat_sel, [])
        _default_lower   = {v.lower() for v in _default_voci}
        _tutte_voci      = _struttura_full.get(_cat_sel, [])
        _accent          = _CAT_COLORS[_cat_sel]["accent"]

        col_lista, col_add = st.columns([1, 1], gap="large")

        # ── Colonna sinistra: lista voci ──────────────────────────────────────
        with col_lista:
            st.markdown(
                f"<div style='font-size:0.90rem;font-weight:700;color:#dde6f5;margin-bottom:10px;'>"
                f"Voci in {_cat_sel}</div>",
                unsafe_allow_html=True,
            )
            for _v in _tutte_voci:
                _is_default = _v.lower() in _default_lower
                if _is_default:
                    st.markdown(
                        f"<div style='display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid rgba(92,118,178,0.10);'>"
                        f"<span style='color:#dde6f5;font-size:0.88rem;'>{escape(str(_v))}</span>"
                        f"<span style='font-size:0.68rem;padding:1px 7px;border-radius:20px;"
                        f"background:rgba(92,118,178,0.15);color:#5a6f8c;border:1px solid rgba(92,118,178,0.25);'>default</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    _col_v, _col_x = st.columns([5, 1], vertical_alignment="center")
                    _col_v.markdown(
                        f"<div style='color:#dde6f5;font-size:0.88rem;padding:4px 0;'>{escape(str(_v))}</div>",
                        unsafe_allow_html=True,
                    )
                    if _col_x.button("✕", key=f"impost_rem_{_cat_sel}_{_v}", help=f"Rimuovi '{_v}'"):
                        ok, msg = _rimuovi_dettaglio(_cat_sel, _v, user_email)
                        _invalidate_runtime_caches(user_settings=True)
                        st.session_state["_impost_ok" if ok else "_impost_err"] = msg
                        st.rerun()

        # ── Colonna destra: aggiungi voce ─────────────────────────────────────
        with col_add:
            st.markdown(
                f"<div style='font-size:0.90rem;font-weight:700;color:#dde6f5;margin-bottom:10px;'>"
                f"Aggiungi voce a {_cat_sel}</div>",
                unsafe_allow_html=True,
            )
            _nuova_voce = st.text_input(
                "nuova_voce",
                placeholder=f"es. Abbonamento Palestra Elite",
                label_visibility="collapsed",
                key="impost_det_new",
            )
            if st.button("＋ Aggiungi", key="impost_btn_add", use_container_width=True, type="primary"):
                ok, msg = _aggiungi_dettaglio(_cat_sel, _nuova_voce, user_email)
                _invalidate_runtime_caches(user_settings=True)
                st.session_state["_impost_ok" if ok else "_impost_err"] = msg
                st.rerun()

    # ── Distribuzione Budget Mensile ──────────────────────────────────────────
    with st.container(border=True):
        st.markdown(
            "<div style='display:flex;align-items:center;gap:8px;margin-bottom:6px;'>"
            "<span style='font-size:1.1rem;'>🎯</span>"
            "<span style='font-size:0.97rem;font-weight:700;color:#dde6f5;'>Distribuzione Budget Mensile</span>"
            "</div>"
            "<p style='font-size:0.82rem;color:#5a6f8c;margin-bottom:16px;'>"
            "Imposta la percentuale del reddito mensile da assegnare a ogni categoria. "
            "La somma deve essere esattamente <strong style='color:#dde6f5;'>100%</strong>."
            "</p>",
            unsafe_allow_html=True,
        )

        # Carica percentuali correnti dal DB
        _perc_correnti = _get_percentuali_budget_cached(user_email)

        from utils.constants import PERCENTUALI_BUDGET as _DEF_PERC
        _cats_perc = list(_DEF_PERC.keys())  # ["NECESSITÀ", "SVAGO", "INVESTIMENTI"]

        # Slider per ciascuna categoria
        col_n, col_s, col_i = st.columns(3)
        _slider_cols = [col_n, col_s, col_i]
        _slider_vals: dict[str, int] = {}

        for _col_p, _cat_p in zip(_slider_cols, _cats_perc):
            _acc = _CAT_COLORS[_cat_p]["accent"]
            with _col_p:
                st.markdown(
                    f"<div style='font-size:0.80rem;font-weight:700;letter-spacing:1px;"
                    f"color:{_acc};margin-bottom:4px;'>{_cat_p}</div>",
                    unsafe_allow_html=True,
                )
                _default_int = int(round(_perc_correnti.get(_cat_p, _DEF_PERC[_cat_p]) * 100))
                _slider_vals[_cat_p] = st.slider(
                    _cat_p,
                    min_value=0,
                    max_value=100,
                    value=_default_int,
                    step=1,
                    label_visibility="collapsed",
                    key=f"impost_slider_{_cat_p}",
                )

        # Validazione totale
        _totale_perc = sum(_slider_vals.values())
        _valid = (_totale_perc == 100)
        if _valid:
            st.markdown(
                "<div style='text-align:center;padding:10px;border-radius:10px;margin:10px 0;"
                "background:rgba(16,217,138,0.10);border:1px solid rgba(16,217,138,0.30);'>"
                "<span style='color:#10d98a;font-weight:700;font-size:0.92rem;'>"
                f"✓ Totale: {_totale_perc}% — Distribuzione valida</span></div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div style='text-align:center;padding:10px;border-radius:10px;margin:10px 0;"
                "background:rgba(250,89,142,0.10);border:1px solid rgba(250,89,142,0.30);'>"
                "<span style='color:#fa598e;font-weight:700;font-size:0.92rem;'>"
                f"⚠ Totale: {_totale_perc}% — La somma deve essere 100%</span></div>",
                unsafe_allow_html=True,
            )

        # Bottoni salva / ripristina
        col_save_p, col_reset_p = st.columns([1, 1])
        if col_save_p.button("💾 Salva percentuali", key="impost_btn_save_perc", use_container_width=True, type="primary", disabled=not _valid):
            _new_perc = {cat: _slider_vals[cat] / 100.0 for cat in _cats_perc}
            ok, msg = _salva_percentuali_budget(_new_perc, user_email)
            _invalidate_runtime_caches(user_settings=True)
            st.session_state["_impost_ok" if ok else "_impost_err"] = msg
            st.rerun()
        if col_reset_p.button("↩ Ripristina default (50/30/20)", key="impost_btn_reset_perc", use_container_width=True):
            ok, msg = _ripristina_percentuali_default(user_email)
            _invalidate_runtime_caches(user_settings=True)
            st.session_state["_impost_ok" if ok else "_impost_err"] = msg
            st.rerun()

        # Preview card per categoria
        st.markdown("<div style='font-size:0.82rem;color:#5a6f8c;margin-top:14px;margin-bottom:8px;'>Anteprima distribuzione:</div>", unsafe_allow_html=True)
        _prev_cols = st.columns(3)
        for _pc, _cat_p in zip(_prev_cols, _cats_perc):
            _acc   = _CAT_COLORS[_cat_p]["accent"]
            _cbg   = _CAT_COLORS[_cat_p]["card"]
            _pval  = _slider_vals[_cat_p]
            _is_def = (_perc_correnti.get(_cat_p, _DEF_PERC[_cat_p]) == _DEF_PERC[_cat_p])
            _lbl   = "default" if _is_def else "personalizzato"
            _pc.markdown(
                f"<div style='border-radius:14px;padding:20px 16px;text-align:center;"
                f"background:{_cbg};border:1px solid {_acc}33;'>"
                f"<div style='font-size:0.72rem;font-weight:700;letter-spacing:1.5px;color:{_acc};margin-bottom:8px;'>{_cat_p}</div>"
                f"<div style='font-size:2rem;font-weight:800;color:#ffffff;line-height:1.1;'>{_pval}%</div>"
                f"<div style='font-size:0.70rem;color:#5a6f8c;margin-top:6px;'>{_lbl}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # ── Autenticazione a due fattori ──────────────────────────────────────────
    with st.container(border=True):
        st.markdown(
            "<div style='display:flex;align-items:center;gap:8px;margin-bottom:6px;'>"
            "<span style='font-size:1.1rem;'>🔐</span>"
            "<span style='font-size:0.97rem;font-weight:700;color:#dde6f5;'>Autenticazione a due fattori (2FA)</span>"
            "</div>"
            "<p style='font-size:0.82rem;color:#5a6f8c;margin-bottom:16px;'>"
            "Proteggi il tuo account con un codice temporaneo generato da Google Authenticator, Authy o app compatibili."
            "</p>",
            unsafe_allow_html=True,
        )

        _email_settings = user_email
        _totp_attivo = is_totp_enabled(_email_settings)

        if is_demo_account:
            st.caption("Il 2FA non è disponibile per l'account demo.")
        elif _totp_attivo:
            st.success("✅ La verifica in due passaggi è attiva sul tuo account.")
            if auth_provider == "google":
                with st.expander("Disabilita 2FA"):
                    st.caption(
                        "Per gli account Google la disattivazione richiede una nuova conferma OAuth con lo stesso account."
                    )
                    if OAuth2Component is None:
                        st.error("Modulo OAuth mancante. Impossibile confermare l'account Google.")
                    elif not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
                        st.error("Credenziali OAuth Google mancanti.")
                    else:
                        redirect_uri = _redirect_uri()
                        if not redirect_uri:
                            st.error("APP_BASE_URL non configurato.")
                        else:
                            oauth2_totp_disable = OAuth2Component(
                                GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
                                AUTHORIZE_URL, TOKEN_URL, TOKEN_URL, ""
                            )
                            result_totp_disable = _safe_google_authorize_button(
                                oauth2_totp_disable,
                                name="Conferma con Google per disabilitare",
                                scope="openid email profile",
                                redirect_uri=redirect_uri,
                                key="google_totp_disable_confirm",
                                use_container_width=True,
                                extras_params={"prompt": "login", "login_hint": _email_settings},
                            )
                            if result_totp_disable:
                                id_token = result_totp_disable.get("id_token")
                                if not id_token and isinstance(result_totp_disable.get("token"), dict):
                                    id_token = result_totp_disable["token"].get("id_token")
                                email_google = _decode_id_token_email(id_token)
                                if not email_google:
                                    acc = result_totp_disable.get("access_token") or (result_totp_disable.get("token") or {}).get("access_token")
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
                                if email_google and email_google == str(_email_settings).strip().lower():
                                    ok, msg = disable_totp_for_google_user(_email_settings)
                                    _reset_google_oauth_state("google_totp_disable_confirm")
                                    _clear_query_params()
                                    if ok:
                                        st.success(msg)
                                        st.rerun()
                                    else:
                                        st.error(msg)
                                elif email_google:
                                    st.error("Hai confermato un account Google diverso da quello loggato.")
            else:
                with st.expander("Disabilita 2FA"):
                    _pwd_disable = st.text_input(
                        "Conferma la tua password per disabilitare",
                        type="password",
                        key="totp_disable_pwd",
                    )
                    if st.button("Disabilita autenticazione a due fattori", type="secondary", key="btn_totp_disable"):
                        ok, msg = disable_totp_for_user(_email_settings, _pwd_disable)
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
        else:
            st.info(
                "La verifica in due passaggi non è attiva. "
                "Aggiunge un livello di sicurezza extra: oltre al primo login, "
                "sarà richiesto un codice temporaneo dall'app Authenticator."
            )
            if auth_provider == "google":
                st.caption("Sugli account Google il codice TOTP verrà richiesto dopo il login OAuth, come secondo passaggio.")
            if st.button("⚙️ Configura autenticazione a due fattori", type="primary", key="btn_totp_setup_start"):
                st.session_state["totp_setup_active"] = True
                st.rerun()

            if st.session_state.get("totp_setup_active"):
                if "totp_setup_secret" not in st.session_state:
                    try:
                        secret, uri = setup_totp_begin(_email_settings)
                        st.session_state["totp_setup_secret"] = secret
                        st.session_state["totp_setup_uri"] = uri
                    except AuthError as e:
                        st.error(str(e))
                        st.session_state.pop("totp_setup_active", None)
                        st.session_state.pop("totp_setup_secret", None)
                        st.session_state.pop("totp_setup_uri", None)

                secret = st.session_state.get("totp_setup_secret", "")
                uri = st.session_state.get("totp_setup_uri", "")
                if secret and uri:
                    st.markdown("**1. Scansiona il QR code con Google Authenticator o Authy:**")

                    import io
                    import qrcode

                    qr_img = qrcode.make(uri)
                    buf = io.BytesIO()
                    qr_img.save(buf, format="PNG")
                    st.image(buf.getvalue(), width=220)

                    with st.expander("Non riesci a scansionare? Inserisci il codice manualmente"):
                        st.code(secret, language=None)

                    st.markdown("**2. Inserisci il codice a 6 cifre mostrato dall'app per confermare:**")
                    _totp_confirm_code = st.text_input(
                        "Codice di conferma",
                        max_chars=6,
                        placeholder="000000",
                        key="totp_confirm_input",
                    )

                    col_ok, col_cancel = st.columns(2)
                    with col_ok:
                        if st.button("Attiva 2FA", type="primary", use_container_width=True, key="btn_totp_enable"):
                            if setup_totp_confirm(_email_settings, _totp_confirm_code):
                                st.success("🎉 Autenticazione a due fattori attivata con successo!")
                                for k in ("totp_setup_active", "totp_setup_secret", "totp_setup_uri", "totp_confirm_input"):
                                    st.session_state.pop(k, None)
                                st.rerun()
                            else:
                                st.error("Codice non valido. Riprova con il codice attuale dall'app.")
                    with col_cancel:
                        if st.button("Annulla", use_container_width=True, key="btn_totp_cancel"):
                            for k in ("totp_setup_active", "totp_setup_secret", "totp_setup_uri", "totp_confirm_input"):
                                st.session_state.pop(k, None)
                            st.rerun()

    # ── Backup Dati ───────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(
            "<div style='display:flex;align-items:center;gap:8px;margin-bottom:6px;'>"
            "<span style='font-size:1.1rem;'>🗄️</span>"
            "<span style='font-size:0.97rem;font-weight:700;color:#dde6f5;'>Backup Dati</span>"
            "</div>",
            unsafe_allow_html=True,
        )

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
            "<div style='font-size:0.90rem;color:#5a6f8c;line-height:1.6;'>"
            "Scarica una <strong style='color:#dde6f5;font-weight:600;'>copia completa</strong> dei tuoi dati in formato SQL. "
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

_render_app_footer()
