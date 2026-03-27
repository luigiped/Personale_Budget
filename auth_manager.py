"""
auth_manager.py 
---------------
Gestione autenticazione e sessioni — FRAMEWORK AGNOSTIC.

Questo modulo implementa la logica di autenticazione indipendentemente dal
framework UI.
Gestisce esclusivamente:
  - Creazione / verifica / cancellazione sessioni nel DB
  - Login email+password (con migrazione automatica SHA-256 → bcrypt)
  - Registrazione utenti
  - Modalità accesso (normal / demo_only / closed)

La gestione di cookie e session state lato client è delegata al layer UI
(interfaccia Streamlit o NiceGUI), che chiama le funzioni di questo modulo
e usa i token restituiti per gestire i propri cookie/storage.

Funzioni pubbliche principali:
    create_session(email)          → (token, expiry) | raises AuthError
    validate_session(token)        → email | None
    delete_session(token)          → None
    login_email_password(email, pw) → (email_norm, token, expiry) | raises AuthError
    register_user(email, pw, nome)  → None | raises AuthError
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
import Database as db
from config_runtime import auth_access_mode, get_secret
from security import hash_password, needs_rehash, verify_password

logger = logging.getLogger(__name__)

SESSION_TOKEN_COOKIE = "pb_session_token"
ACCOUNT_USERS_TABLE = "utenti_registrati"
SESSION_DURATION_DAYS = 7
# Intervallo minimo tra due verifiche DB della stessa sessione (cache locale).
# Il layer UI può implementare una cache in memoria usando questo valore.
SESSION_RECHECK_SECONDS = 20


# ---------------------------------------------------------------------------
# Eccezioni pubbliche
# ---------------------------------------------------------------------------

class AuthError(Exception):
    """Errore di autenticazione con messaggio leggibile dall'utente."""


class AccessDeniedError(AuthError):
    """Accesso negato per modalità o permessi."""


# ---------------------------------------------------------------------------
# Helpers interni
# ---------------------------------------------------------------------------

def _normalize_email(email: str | None) -> str | None:
    if not email:
        return None
    value = str(email).strip().lower()
    return value if "@" in value else None


def _current_auth_mode() -> str:
    return auth_access_mode()


def _demo_email_norm() -> str | None:
    return _normalize_email(get_secret("DEMO_USER_EMAIL"))


def _parse_datetime_utc(value) -> datetime | None:
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
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except Exception:
        return None


def _check_access_mode(email_norm: str) -> None:
    """
    Verifica che la modalità di accesso corrente permetta il login per email_norm.
    Solleva AccessDeniedError se non permesso.
    """
    mode = _current_auth_mode()
    if mode == "closed":
        raise AccessDeniedError("Accesso temporaneamente disabilitato.")
    if mode == "demo_only":
        demo_email = _demo_email_norm()
        if not demo_email or email_norm != demo_email:
            raise AccessDeniedError("Modalità demo attiva: solo l'account demo può accedere.")


def _ensure_auth_tables(conn) -> None:
    """Crea le tabelle di sessione se non esistono. Idempotente."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS active_sessions (
                token       TEXT PRIMARY KEY,
                user_email  TEXT NOT NULL,
                expires_at  TIMESTAMPTZ NOT NULL
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_active_sessions_expires "
            "ON active_sessions (expires_at)"
        )
        try:
            cur.execute(
                "ALTER TABLE active_sessions "
                "DROP CONSTRAINT IF EXISTS active_sessions_user_email_fkey"
            )
        except Exception:
            pass


def _register_utenti_notifiche(conn, email_norm: str) -> None:
    """Registra / aggiorna l'utente nella tabella notifiche. Non blocca mai."""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO utenti_notifiche (email, attivo, ultimo_login)
                VALUES (%s, TRUE, CURRENT_TIMESTAMP)
                ON CONFLICT (email) DO UPDATE SET
                    attivo = TRUE,
                    ultimo_login = CURRENT_TIMESTAMP
            """, (email_norm,))
    except Exception as exc:
        logger.warning("_register_utenti_notifiche: %s", exc)


# ---------------------------------------------------------------------------
# API pubblica — sessioni
# ---------------------------------------------------------------------------

def create_session(email: str) -> tuple[str, datetime]:
    """
    Crea una nuova sessione DB per email.

    Restituisce (token, expiry) dove:
        token  : stringa urlsafe da salvare nel cookie lato client
        expiry : datetime UTC con scadenza

    Solleva AuthError / AccessDeniedError in caso di errore.
    """
    email_norm = _normalize_email(email)
    if not email_norm:
        raise AuthError("Email non valida.")
    _check_access_mode(email_norm)

    token = secrets.token_urlsafe(32)
    expiry = datetime.now(timezone.utc) + timedelta(days=SESSION_DURATION_DAYS)

    try:
        with db.connetti_db() as conn:
            _ensure_auth_tables(conn)
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO active_sessions (token, user_email, expires_at) "
                    "VALUES (%s, %s, %s)",
                    (token, email_norm, expiry.isoformat()),
                )
            _register_utenti_notifiche(conn, email_norm)
    except (AuthError, AccessDeniedError):
        raise
    except Exception as exc:
        logger.error("create_session: errore per %s: %s", email_norm, exc)
        raise AuthError(f"Errore tecnico durante la creazione sessione: {exc}") from exc

    logger.info("Sessione creata per %s (scade %s)", email_norm, expiry.date())
    return token, expiry


def validate_session(token: str) -> str | None:
    """
    Verifica che il token sia presente e non scaduto nel DB.

    Restituisce l'email normalizzata dell'utente, oppure None se il token
    non è valido o è scaduto.
    Non solleva mai eccezioni.
    """
    if not token or not token.strip():
        return None
    token = token.strip()
    try:
        with db.connetti_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT LOWER(TRIM(user_email)), expires_at "
                    "FROM active_sessions WHERE token = %s LIMIT 1",
                    (token,),
                )
                row = cur.fetchone()
        if not row:
            return None
        user_email_raw, expires_at_raw = row
        expires_at = _parse_datetime_utc(expires_at_raw)
        if not expires_at or expires_at <= datetime.now(timezone.utc):
            return None
        return _normalize_email(user_email_raw)
    except Exception as exc:
        logger.debug("validate_session: %s", exc)
        return None


def delete_session(token: str) -> None:
    """
    Cancella la sessione dal DB. Non solleva mai eccezioni.
    La rimozione del cookie lato client è responsabilità del layer UI.
    """
    if not token:
        return
    try:
        with db.connetti_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM active_sessions WHERE token = %s", (token.strip(),))
        logger.info("Sessione rimossa dal DB.")
    except Exception as exc:
        logger.warning("delete_session: %s", exc)


# ---------------------------------------------------------------------------
# API pubblica — autenticazione
# ---------------------------------------------------------------------------

def login_email_password(email: str, password: str) -> tuple[str, str, datetime]:
    """
    Esegue il login con email + password.

    Restituisce (email_norm, token, expiry).
    Solleva AuthError con messaggio leggibile dall'utente in caso di errore.

    Migra automaticamente gli hash SHA-256 legacy a bcrypt al primo login
    riuscito.
    """
    email_norm = _normalize_email(email)
    if not email_norm:
        raise AuthError("Email non valida.")
    if not password:
        raise AuthError("Password mancante.")

    _check_access_mode(email_norm)

    try:
        with db.connetti_db() as conn:
            with conn.cursor() as cur:
                # Cerca prima in utenti_registrati
                cur.execute(
                    f"SELECT email, password_hash FROM {ACCOUNT_USERS_TABLE} "
                    "WHERE email = %s LIMIT 1",
                    (email_norm,),
                )
                row = cur.fetchone()
                source_table = ACCOUNT_USERS_TABLE

                # Fallback: utenti_demo (se la tabella esiste)
                if not row:
                    try:
                        cur.execute(
                            "SELECT email, password_hash FROM utenti_demo "
                            "WHERE email = %s LIMIT 1",
                            (email_norm,),
                        )
                        row = cur.fetchone()
                        source_table = "utenti_demo"
                    except Exception:
                        pass

            if not row:
                raise AuthError("Email o password non corretti.")

            _, stored_hash = row

            if not verify_password(password, stored_hash):
                raise AuthError("Email o password non corretti.")

            # Migrazione automatica hash legacy → bcrypt
            if needs_rehash(stored_hash):
                try:
                    new_hash = hash_password(password)
                    with conn.cursor() as cur:
                        cur.execute(
                            f"UPDATE {source_table} SET password_hash = %s WHERE email = %s",
                            (new_hash, email_norm),
                        )
                    logger.info("Hash migrato a bcrypt per %s", email_norm)
                except Exception as exc:
                    logger.warning("Migrazione hash fallita per %s: %s", email_norm, exc)

    except AuthError:
        raise
    except Exception as exc:
        logger.error("login_email_password: %s", exc)
        raise AuthError(f"Errore DB: {exc}") from exc

    token, expiry = create_session(email_norm)
    return email_norm, token, expiry


def register_user(email: str, password: str, nome: str = "") -> None:
    """
    Registra un nuovo utente in utenti_registrati.

    Solleva AuthError con messaggio leggibile dall'utente in caso di errore.
    """
    email_norm = _normalize_email(email)
    if not email_norm:
        raise AuthError("Email non valida.")

    mode = _current_auth_mode()
    if mode in {"demo_only", "closed"}:
        raise AccessDeniedError("Registrazione temporaneamente disabilitata.")

    if not password or len(password) < 6:
        raise AuthError("Password troppo corta (minimo 6 caratteri).")

    pwd_hash = hash_password(password)
    nome_clean = (nome or "").strip() or email_norm.split("@")[0]

    try:
        with db.connetti_db() as conn:
            # Rileva le colonne disponibili (schema flessibile)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s",
                    (ACCOUNT_USERS_TABLE,),
                )
                cols = {str(r[0]).strip().lower() for r in cur.fetchall() if r and r[0]}

            insert_cols = ["email", "password_hash"]
            insert_vals: list = [email_norm, pwd_hash]

            if "nome_utente" in cols:
                insert_cols.append("nome_utente")
                insert_vals.append(nome_clean)

            placeholders = ", ".join(["%s"] * len(insert_vals))
            query = (
                f"INSERT INTO {ACCOUNT_USERS_TABLE} "
                f"({', '.join(insert_cols)}) VALUES ({placeholders})"
            )
            with conn.cursor() as cur:
                cur.execute(query, tuple(insert_vals))

    except Exception as exc:
        err = str(exc)
        if "unique" in err.lower() or "duplicate" in err.lower():
            raise AuthError("Email già registrata.")
        logger.error("register_user: %s", exc)
        raise AuthError(f"Errore registrazione: {exc}") from exc

    logger.info("Nuovo utente registrato: %s", email_norm)


def get_display_name(email: str, is_demo_account: bool = False) -> str:
    """
    Recupera il nome visualizzato dell'utente dal DB.
    Restituisce email.split('@')[0].upper() come fallback sicuro.
    """
    default = email.split("@")[0].upper() if email else "UTENTE"
    try:
        table = "utenti_demo" if is_demo_account else ACCOUNT_USERS_TABLE
        with db.connetti_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT nome_utente FROM {table} WHERE email = %s LIMIT 1",
                    (email,),
                )
                row = cur.fetchone()
        if row and row[0]:
            return str(row[0]).strip().upper() or default
    except Exception as exc:
        logger.debug("get_display_name: %s", exc)
    return default