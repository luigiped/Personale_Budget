import logging
import secrets
from datetime import datetime, timedelta, timezone

import streamlit as st
import streamlit.components.v1 as components
import Database as db
from config_runtime import auth_access_mode, get_secret

logger = logging.getLogger(__name__)

try:
    import extra_streamlit_components as stx
except Exception:
    stx = None


SESSION_TOKEN_COOKIE = "pb_session_token"
ACCOUNT_USERS_TABLE = "utenti_registrati"
SESSION_RECHECK_SECONDS = 20


def _normalize_email(email):
    if not email:
        return None
    value = str(email).strip().lower()
    if "@" not in value:
        return None
    return value


def _current_auth_mode():
    return auth_access_mode()


def _demo_email_norm():
    return _normalize_email(get_secret("DEMO_USER_EMAIL"))


def _parse_datetime_utc(value):
    """Converte una data ISO (naive o aware) in datetime UTC aware."""
    if not value:
        return None
    try:
        if isinstance(value, datetime):
            dt = value
        else:
            raw = str(value).strip()
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _read_session_state_scalar(name):
    try:
        value = st.session_state.get(name)
    except Exception:
        value = None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _get_cookie_manager():
    if stx is None:
        return None
    try:
        # Non cacheare l'istanza: getAll va riallineato ad ogni run.
        return stx.CookieManager(key="pb_cookie_manager")
    except Exception:
        return None


def _read_cookie_scalar(name):
    # streamlit >= 1.30 espone i cookie della request in sola lettura.
    try:
        cookies = getattr(st.context, "cookies", None)
    except Exception:
        cookies = None
    if cookies:
        value = cookies.get(name)
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
        if value is not None:
            text = str(value).strip()
            if text:
                return text

    cookie_manager = _get_cookie_manager()
    if cookie_manager is None:
        return None
    try:
        cookie_manager.get_all(key=f"cookie_get_all_{name}")
        value = cookie_manager.get(name)
    except Exception:
        value = None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _js_set_cookie(name, value, expires_at=None, secure=False, same_site="Lax"):
    """Fallback Javascript snippet to set a cookie in the browser.

    This is used when the Python-side cookie manager is not available or fails.  The
    snippet runs in the page and writes a standard cookie with attributes similar
    to those requested by the caller.
    """
    max_age = None
    if expires_at is not None:
        try:
            max_age = int((expires_at - datetime.now(timezone.utc)).total_seconds())
            if max_age < 0:
                max_age = 0
        except Exception:
            max_age = None
    attrs = f"SameSite={same_site};path=/;"
    if max_age is not None:
        attrs += f"max-age={max_age};"
    if secure:
        attrs += "secure;"
    
    html = f"<script>document.cookie = '{name}={value};{attrs}';</script>"
    try:
        components.html(html, height=0)
    except Exception:
       
        pass


def _set_cookie(name, value, expires_at=None):
    """Scrive un cookie lato client.  Restituisce True se l'operazione è stata
    tentata (non necessariamente riuscita).  In caso di problemi con il
    `CookieManager` di extra-streamlit-components si utilizza il fallback JS.
    """
    # Determiniamo se stiamo servendo via https per il flag `secure`.
    is_https = False
    try:
        headers = getattr(st.context, "headers", None) or {}
        proto = str(headers.get("x-forwarded-proto", "")).lower()
        is_https = proto == "https"
    except Exception:
        is_https = False

    cookie_manager = _get_cookie_manager()
    if cookie_manager is not None:
        try:
            kwargs = {"key": f"cookie_set_{name}"}
            if expires_at is not None:
                kwargs["expires_at"] = expires_at
            kwargs["same_site"] = "lax"  # allow post-OAuth redirect
            kwargs["path"] = "/"
            try:
                cookie_manager.set(name, value, secure=is_https, **kwargs)
            except TypeError:
                cookie_manager.set(name, value, **kwargs)
            return True
        except Exception:
            # fall through to javascript fallback
            pass

    # se siamo qui, manager mancante o fallito: usiamo JS per scrivere il cookie
    logger.debug("CookieManager non disponibile, uso fallback JS per il cookie '%s'.", name)
    _js_set_cookie(name, value, expires_at=expires_at, secure=is_https)
    return True


def _delete_cookie(name):
    cookie_manager = _get_cookie_manager()
    if cookie_manager is None:
        return False
    try:
        cookie_manager.delete(name, key=f"cookie_del_{name}")
        return True
    except Exception:
        return False


def _clear_local_session_state():
    st.session_state.pop("session_token", None)
    st.session_state.pop("auth_user_email", None)
    st.session_state.pop("_auth_cache_token", None)
    st.session_state.pop("_auth_cache_user", None)
    st.session_state.pop("_auth_cache_expires_at", None)
    st.session_state.pop("_auth_cache_checked_at", None)


def _clear_local_auth_storage():
    _delete_cookie(SESSION_TOKEN_COOKIE)
    _clear_local_session_state()


def _ensure_auth_tables(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS active_sessions (
            token TEXT PRIMARY KEY,
            user_email TEXT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_active_sessions_expires ON active_sessions (expires_at)")
    # Se esiste una FK legacy verso whitelist la rimuoviamo:
    # la sessione deve dipendere dagli account registrati, non dalla whitelist.
    try:
        cursor.execute("ALTER TABLE active_sessions DROP CONSTRAINT IF EXISTS active_sessions_user_email_fkey")
    except Exception:
        pass


@st.cache_resource
def _ensure_auth_schema_ready():
    try:
        with db.connetti_db() as conn:
            cursor = conn.cursor()
            _ensure_auth_tables(cursor)
            cursor.close()
    except Exception as exc:
        logger.error("_ensure_auth_schema_ready: %s", exc)
    return True


def _get_cached_session_user(token):
    """Ritorna l'utente cacheato se la validazione recente è ancora affidabile."""
    try:
        cache_token = st.session_state.get("_auth_cache_token")
        cache_user = st.session_state.get("_auth_cache_user")
        cache_exp = st.session_state.get("_auth_cache_expires_at")
        cache_checked = st.session_state.get("_auth_cache_checked_at")
    except Exception:
        return None

    if not token or token != cache_token or not cache_user:
        return None

    exp_dt = _parse_datetime_utc(cache_exp)
    checked_dt = _parse_datetime_utc(cache_checked)
    now = datetime.now(timezone.utc)
    if exp_dt is None or checked_dt is None:
        return None
    if exp_dt <= now:
        return None
    if (now - checked_dt) > timedelta(seconds=SESSION_RECHECK_SECONDS):
        return None
    return _normalize_email(cache_user)


def _store_cached_session_user(token, email_norm, expires_at):
    now = datetime.now(timezone.utc)
    st.session_state["_auth_cache_token"] = token
    st.session_state["_auth_cache_user"] = email_norm
    st.session_state["_auth_cache_expires_at"] = expires_at.isoformat() if hasattr(expires_at, "isoformat") else str(expires_at)
    st.session_state["_auth_cache_checked_at"] = now.isoformat()


def get_session_user():
    """Controlla se esiste una sessione valida nel database."""
    state_token = _read_session_state_scalar("session_token")
    cookie_token = _read_cookie_scalar(SESSION_TOKEN_COOKIE)

    token = state_token or cookie_token
    if not token:
        return None
    cached_user = _get_cached_session_user(token)
    if cached_user:
        st.session_state["session_token"] = token
        st.session_state["auth_user_email"] = cached_user
        return cached_user

    try:
        _ensure_auth_schema_ready()
        with db.connetti_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT LOWER(TRIM(user_email)) AS user_email, expires_at
                FROM active_sessions
                WHERE token = %s
                LIMIT 1
                """,
                (token,),
            )
            row = cursor.fetchone()
            cursor.close()
        if not row:
            _clear_local_auth_storage()
            return None
        user_email, expires_at_raw = row
        expires_at = _parse_datetime_utc(expires_at_raw)
        if expires_at and expires_at > datetime.now(timezone.utc):
            email_norm = _normalize_email(user_email)
            if email_norm:
                st.session_state["session_token"] = token
                st.session_state["auth_user_email"] = email_norm
                _store_cached_session_user(token, email_norm, expires_at)
                _set_cookie(SESSION_TOKEN_COOKIE, token, expires_at=expires_at)
            return email_norm
        _clear_local_auth_storage()
        return None
    except Exception as exc:
        logger.debug("get_session_user: errore verifica sessione: %s", exc)
        return None

def create_new_session(email):
    """Crea una sessione di 7 giorni senza controllo preventivo su whitelist."""
    email_norm = _normalize_email(email)
    if not email_norm:
        st.error("Email non valida.")
        return False
    mode = _current_auth_mode()
    if mode == "closed":
        st.error("Accesso temporaneamente disabilitato.")
        return False
    if mode == "demo_only":
        demo_email = _demo_email_norm()
        if not demo_email or email_norm != demo_email:
            st.error("Accesso utenti disabilitato: è attiva solo la modalità demo.")
            return False

    new_token = secrets.token_urlsafe(32)
    expiry = datetime.now(timezone.utc) + timedelta(days=7)

    try:
        _ensure_auth_schema_ready()
        with db.connetti_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO active_sessions (token, user_email, expires_at)
                VALUES (%s, %s, %s)
                """,
                (new_token, email_norm, expiry.isoformat()),
            )
            try:
                cursor.execute(
                    """
                    INSERT INTO utenti_notifiche (email, attivo, ultimo_login)
                    VALUES (%s, TRUE, CURRENT_TIMESTAMP)
                    ON CONFLICT (email) DO UPDATE SET
                        attivo = TRUE,
                        ultimo_login = CURRENT_TIMESTAMP
                    """,
                    (email_norm,),
                )
            except Exception:
                pass
            cursor.close()

        st.session_state["session_token"] = new_token
        st.session_state["auth_user_email"] = email_norm
        _store_cached_session_user(new_token, email_norm, expiry)
        _set_cookie(SESSION_TOKEN_COOKIE, new_token, expires_at=expiry)
        return True

    except Exception as exc:
        logger.error("create_new_session: errore per %s: %s", email_norm, exc)
        st.error(f"Errore tecnico durante la creazione sessione: {exc}")
        return False


def clear_session():
    """Rimuove la sessione corrente da Supabase e dal client."""
    token = (
        _read_session_state_scalar("session_token")
        or _read_cookie_scalar(SESSION_TOKEN_COOKIE)
    )
    if token:
        try:
            _ensure_auth_schema_ready()
            with db.connetti_db() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM active_sessions WHERE token = %s", (token,))
                cursor.close()
        except Exception as exc:
            logger.warning("clear_session: impossibile rimuovere sessione dal DB: %s", exc)

    _clear_local_auth_storage()

################ ── DEMO & EMAIL LOGIN (aggiunto per demo) -- ###########################

def create_demo_session(email):
    """
    Come create_new_session ma SENZA controllo whitelist.
    Usata per l'utente demo e per utenti registrati nella demo.
    """
    email_norm = _normalize_email(email)
    if not email_norm:
        st.error("Email non valida.")
        return False
    mode = _current_auth_mode()
    if mode == "closed":
        st.error("Accesso temporaneamente disabilitato.")
        return False
    if mode == "demo_only":
        demo_email = _demo_email_norm()
        if not demo_email or email_norm != demo_email:
            st.error("Modalità demo attiva: solo l'account demo può accedere.")
            return False

    new_token = secrets.token_urlsafe(32)
    expiry = datetime.now(timezone.utc) + timedelta(days=7)

    try:
        _ensure_auth_schema_ready()
        with db.connetti_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO active_sessions (token, user_email, expires_at)
                VALUES (%s, %s, %s)
                """,
                (new_token, email_norm, expiry.isoformat()),
            )
            try:
                cursor.execute(
                    """
                    INSERT INTO utenti_notifiche (email, attivo, ultimo_login)
                    VALUES (%s, TRUE, CURRENT_TIMESTAMP)
                    ON CONFLICT (email) DO UPDATE SET
                        attivo = TRUE,
                        ultimo_login = CURRENT_TIMESTAMP
                    """,
                    (email_norm,),
                )
            except Exception:
                pass
            cursor.close()
    except Exception as exc:
        logger.error("create_demo_session: errore per %s: %s", email_norm, exc)
        st.error(f"Errore login demo: {exc}")
        return False
    st.session_state["session_token"] = new_token
    st.session_state["auth_user_email"] = email_norm
    _store_cached_session_user(new_token, email_norm, expiry)
    _set_cookie(SESSION_TOKEN_COOKIE, new_token, expires_at=expiry)
    return True


def login_email_password(email, password):
    """
    Login email + password contro la tabella utenti_registrati.
    Struttura tabella attesa (minima):
        CREATE TABLE utenti_registrati (
            email TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            creato_il TIMESTAMPTZ DEFAULT NOW()
        );
    """
    import hashlib
    email_norm = _normalize_email(email)
    if not email_norm:
        return False, "Email non valida."
    mode = _current_auth_mode()
    if mode == "closed":
        return False, "Accesso temporaneamente disabilitato."
    if mode == "demo_only":
        demo_email = _demo_email_norm()
        if not demo_email or email_norm != demo_email:
            return False, "Accesso utenti disabilitato: è attiva solo la modalità demo."

    try:
        with db.connetti_db() as conn:
            cursor = conn.cursor()
            pwd_hash = hashlib.sha256(password.encode()).hexdigest()
            cursor.execute(
                f"SELECT email FROM {ACCOUNT_USERS_TABLE} WHERE email = %s AND password_hash = %s LIMIT 1",
                (email_norm, pwd_hash),
            )
            row = cursor.fetchone()
            if not row:
                cursor.execute(
                    "SELECT email FROM utenti_demo WHERE email = %s AND password_hash = %s LIMIT 1",
                    (email_norm, pwd_hash),
                )
                row = cursor.fetchone()
            cursor.close()
        if not row:
            return False, "Email o password non corretti."
    except Exception as exc:
        logger.error("login_email_password: %s", exc)
        return False, f"Errore DB: {exc}"

    ok = create_demo_session(email_norm)
    return ok, "" if ok else "Errore creazione sessione."


def register_demo_user(email, password, nome=""):
    """
    Registra un nuovo utente nella tabella utenti_registrati.
    """
    import hashlib
    email_norm = _normalize_email(email)
    if not email_norm:
        return False, "Email non valida."
    mode = _current_auth_mode()
    if mode in {"demo_only", "closed"}:
        return False, "Registrazione temporaneamente disabilitata."
    if not password or len(password) < 6:
        return False, "Password troppo corta (minimo 6 caratteri)."

    try:
        with db.connetti_db() as conn:
            cursor = conn.cursor()
            pwd_hash = hashlib.sha256(password.encode()).hexdigest()
            columns = {"email", "password_hash"}
            try:
                cursor.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s
                    """,
                    (ACCOUNT_USERS_TABLE,),
                )
                discovered = {str(r[0]).strip().lower() for r in cursor.fetchall() if r and r[0]}
                if discovered:
                    columns = discovered
            except Exception:
                pass
            insert_cols = ["email", "password_hash"]
            insert_vals = [email_norm, pwd_hash]
            if "nome_utente" in columns:
                insert_cols.append("nome_utente")
                insert_vals.append(nome.strip() or email_norm.split("@")[0])
            placeholders = ", ".join(["%s"] * len(insert_vals))
            query = f"INSERT INTO {ACCOUNT_USERS_TABLE} ({', '.join(insert_cols)}) VALUES ({placeholders})"
            cursor.execute(query, tuple(insert_vals))
            cursor.close()
        return True, ""
    except Exception as exc:
        logger.error("register_demo_user: %s", exc)
        err = str(exc)
        if "unique" in err.lower() or "duplicate" in err.lower():
            return False, "Email già registrata."
        return False, f"Errore registrazione: {exc}"

# Per registrazione utenti in autonomia senza whitelist
def register_user(email, password):
    import hashlib
    email_norm = _normalize_email(email)
    if not email_norm or len(password) < 6:
        return False, "Email o password non valide."
    mode = _current_auth_mode()
    if mode in {"demo_only", "closed"}:
        return False, "Registrazione temporaneamente disabilitata."

    try:
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        with db.connetti_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO utenti_registrati (email, password_hash)
                VALUES (%s, %s)
                """,
                (email_norm, pwd_hash),
            )
            cursor.close()
        return True, "Registrazione completata!"
    except Exception as exc:
        logger.error("register_user: %s", exc)
        return False, f"Errore: {exc}"
