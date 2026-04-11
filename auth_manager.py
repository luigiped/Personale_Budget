"""
auth_manager.py 
---------------
Gestione autenticazione e sessioni — FRAMEWORK AGNOSTIC.

Questo modulo implementa la logica di autenticazione indipendentemente dal
framework UI.
Gestisce esclusivamente:
  - Creazione / verifica / cancellazione sessioni nel DB
  - Login email+password (con migrazione automatica SHA-256 → bcrypt) e recupero password
  - Registrazione utenti
  - Modalità accesso (normal / demo_only / pilot_only / closed)

La gestione di cookie e session state lato client è delegata al layer UI
(interfaccia Streamlit o NiceGUI), che chiama le funzioni di questo modulo
e usa i token restituiti per gestire i propri cookie/storage.

Funzioni pubbliche principali:
    create_session(email)          → (token, expiry) | raises AuthError
    validate_session(token)        → email | None
    delete_session(token)          → None
    login_email_password(email, pw) → (email_norm, token, expiry) | raises AuthError
    login_google_user(email, nome)  → (email_norm, token, expiry) | raises AuthError
    login_totp_step(email, code, challenge) → (email_norm, token, expiry) | raises AuthError
    register_user(email, pw, nome)  → None | raises AuthError
    setup_totp_begin(email)         → (secret, uri) | raises AuthError
    setup_totp_confirm(email, code) → bool
    cancel_totp_login_challenge(challenge)  → None
    disable_totp_for_user(email, password) → (bool, msg)
    disable_totp_for_google_user(email)    → (bool, msg)
    is_totp_enabled(email)          → bool
    request_totp_recovery(email, challenge, provider) → (bool, msg)
    confirm_totp_recovery(email, otp, challenge, provider) → (email, token, expiry)
    TwoFactorRequired               → eccezione per secondo step TOTP
"""

import logging
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
import Database as db
from config_runtime import (
    auth_access_mode, get_secret,
    allowed_login_emails, allowed_registration_emails,
)
from security import (
    hash_password, needs_rehash, verify_password,
    generate_totp_secret, get_totp_uri, verify_totp_code,
)
from gmail_sender import send_email

logger = logging.getLogger(__name__)

SESSION_TOKEN_COOKIE = "pb_session_token"
ACCOUNT_USERS_TABLE = "utenti_registrati"
SESSION_DURATION_DAYS = 1
PENDING_2FA_TTL_MINUTES = 10
MIN_PASSWORD_LEN = 8
LOGIN_WINDOW_MINUTES = 15
LOGIN_MAX_ATTEMPTS = 5
TOTP_WINDOW_MINUTES = 10
TOTP_MAX_ATTEMPTS = 6
RESET_REQUEST_WINDOW_MINUTES = 15
RESET_REQUEST_MAX_ATTEMPTS = 3
RESET_CONFIRM_WINDOW_MINUTES = 15
RESET_CONFIRM_MAX_ATTEMPTS = 6
TOTP_RECOVERY_TTL_MINUTES = 10
TOTP_RECOVERY_REQUEST_WINDOW_MINUTES = 15
TOTP_RECOVERY_REQUEST_MAX_ATTEMPTS = 3
TOTP_RECOVERY_CONFIRM_WINDOW_MINUTES = 15
TOTP_RECOVERY_CONFIRM_MAX_ATTEMPTS = 6
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


class TwoFactorRequired(AuthError):
    """
    Sollevata quando le credenziali principali sono corrette ma l'utente ha
    il TOTP abilitato.
    Il layer UI deve chiedere il codice e chiamare login_totp_step().

    Attributo .email contiene l'email normalizzata già verificata.
    """
    def __init__(self, email: str, challenge_token: str):
        super().__init__("Autenticazione a due fattori richiesta.")
        self.email = email
        self.challenge_token = challenge_token


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


def _pilot_login_allowlist() -> set[str]:
    emails = {_normalize_email(email) for email in allowed_login_emails()}
    emails.update(_normalize_email(email) for email in allowed_registration_emails())
    return {email for email in emails if email}


def _pilot_registration_allowlist() -> set[str]:
    return {email for email in (_normalize_email(item) for item in allowed_registration_emails()) if email}


def _is_pilot_login_allowed(email_norm: str) -> bool:
    demo_email = _demo_email_norm()
    if demo_email and email_norm == demo_email:
        return True
    return email_norm in _pilot_login_allowlist()


def _is_pilot_registration_allowed(email_norm: str) -> bool:
    return email_norm in _pilot_registration_allowlist()


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


def _issue_totp_challenge(email_norm: str, provider: str) -> str:
    """Crea una challenge temporanea server-side per il secondo step 2FA."""
    challenge_token = secrets.token_urlsafe(32)
    if not db.create_pending_2fa_challenge(
        email_norm,
        challenge_token,
        provider=provider,
        ttl_minutes=PENDING_2FA_TTL_MINUTES,
    ):
        raise AuthError("Errore temporaneo durante la verifica 2FA. Riprova.")
    return challenge_token


def _hash_session_token(token: str) -> str:
    """Hash SHA-256 del token di sessione per storage sicuro nel DB."""
    return hashlib.sha256(str(token or "").strip().encode("utf-8")).hexdigest()


def _hash_user_agent(user_agent: str | None) -> str | None:
    """Hash stabile dello user-agent per legare la sessione al client corrente."""
    raw = str(user_agent or "").strip()
    if not raw:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
    if mode == "pilot_only" and not _is_pilot_login_allowed(email_norm):
        raise AccessDeniedError(
            "Accesso reale riservato agli account autorizzati per questa fase di test."
        )


def _ensure_auth_tables(conn) -> None:
    """Crea le tabelle di sessione se non esistono. Idempotente."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS active_sessions (
                token       TEXT PRIMARY KEY,
                user_email  TEXT NOT NULL,
                expires_at  TIMESTAMPTZ NOT NULL,
                user_agent_hash TEXT
            )
        """)
        cur.execute("ALTER TABLE active_sessions ADD COLUMN IF NOT EXISTS user_agent_hash TEXT")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_active_sessions_expires ON active_sessions (expires_at)")
        try:
            cur.execute(
                "ALTER TABLE active_sessions "
                "DROP CONSTRAINT IF EXISTS active_sessions_user_email_fkey"
            )
        except Exception:
            pass


def _table_columns(conn, table_name: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table_name,),
        )
        return {str(r[0]).strip().lower() for r in cur.fetchall() if r and r[0]}


def _user_account_exists(conn, email_norm: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT 1 FROM {ACCOUNT_USERS_TABLE} WHERE email = %s LIMIT 1",
            (email_norm,),
        )
        return cur.fetchone() is not None


def _user_has_existing_data(conn, email_norm: str) -> bool:
    checks = [
        ("movimenti", "user_email"),
        ("asset_settings", "user_email"),
        ("finanziamenti", "user_email"),
        ("spese_ricorrenti", "user_email"),
        ("obiettivi_utente", "user_email"),
    ]
    for table_name, column_name in checks:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT 1 FROM {table_name} "
                    f"WHERE LOWER(TRIM({column_name})) = %s LIMIT 1",
                    (email_norm,),
                )
                if cur.fetchone() is not None:
                    return True
        except Exception as exc:
            logger.debug("_user_has_existing_data(%s.%s): %s", table_name, column_name, exc)
    return False


def _ensure_google_account(conn, email_norm: str, nome: str = "") -> None:
    if _user_account_exists(conn, email_norm):
        return

    cols = _table_columns(conn, ACCOUNT_USERS_TABLE)
    nome_clean = (nome or "").strip() or email_norm.split("@")[0]
    onboarding_completed = _user_has_existing_data(conn, email_norm)

    insert_cols = ["email", "password_hash"]
    insert_vals: list = [email_norm, hash_password(secrets.token_urlsafe(32))]

    if "nome_utente" in cols:
        insert_cols.append("nome_utente")
        insert_vals.append(nome_clean)
    if "auth_provider" in cols:
        insert_cols.append("auth_provider")
        insert_vals.append("google")
    if "onboarding_completed" in cols:
        insert_cols.append("onboarding_completed")
        insert_vals.append(bool(onboarding_completed))

    placeholders = ", ".join(["%s"] * len(insert_vals))
    query = (
        f"INSERT INTO {ACCOUNT_USERS_TABLE} "
        f"({', '.join(insert_cols)}) VALUES ({placeholders}) "
        "ON CONFLICT (email) DO NOTHING"
    )
    with conn.cursor() as cur:
        cur.execute(query, tuple(insert_vals))

    logger.info(
        "Account Google inizializzato per %s (onboarding_completed=%s).",
        email_norm,
        bool(onboarding_completed),
    )


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

def create_session(email: str, user_agent: str | None = None) -> tuple[str, datetime]:
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
    token_hash = _hash_session_token(token)
    user_agent_hash = _hash_user_agent(user_agent)
    expiry = datetime.now(timezone.utc) + timedelta(days=SESSION_DURATION_DAYS)

    try:
        with db.connetti_db() as conn:
            _ensure_auth_tables(conn)
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO active_sessions (token, user_email, expires_at, user_agent_hash) "
                    "VALUES (%s, %s, %s, %s)",
                    (token_hash, email_norm, expiry.isoformat(), user_agent_hash),
                )
            _register_utenti_notifiche(conn, email_norm)
    except (AuthError, AccessDeniedError):
        raise
    except Exception as exc:
        logger.error("create_session: errore per %s: %s", email_norm, exc)
        raise AuthError("Errore tecnico durante la creazione sessione. Riprova.") from exc

    logger.info("Sessione creata per %s (scade %s)", email_norm, expiry.date())
    return token, expiry


def validate_session(token: str, user_agent: str | None = None) -> str | None:
    """
    Verifica che il token sia presente e non scaduto nel DB.

    Restituisce l'email normalizzata dell'utente, oppure None se il token
    non è valido o è scaduto.
    Non solleva mai eccezioni.
    """
    if not token or not token.strip():
        return None
    token = token.strip()
    token_hash = _hash_session_token(token)
    current_user_agent_hash = _hash_user_agent(user_agent)
    try:
        with db.connetti_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT LOWER(TRIM(user_email)), expires_at, user_agent_hash "
                    "FROM active_sessions WHERE token IN (%s, %s) LIMIT 1",
                    (token_hash, token),
                )
                row = cur.fetchone()
        if not row:
            return None
        user_email_raw, expires_at_raw, stored_user_agent_hash = row
        expires_at = _parse_datetime_utc(expires_at_raw)
        if not expires_at or expires_at <= datetime.now(timezone.utc):
            return None
        if stored_user_agent_hash and current_user_agent_hash and stored_user_agent_hash != current_user_agent_hash:
            logger.warning("validate_session: fingerprint user-agent non corrispondente.")
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
        token_hash = _hash_session_token(token)
        with db.connetti_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM active_sessions WHERE token IN (%s, %s)",
                    (token_hash, token.strip()),
                )
        logger.info("Sessione rimossa dal DB.")
    except Exception as exc:
        logger.warning("delete_session: %s", exc)


# ---------------------------------------------------------------------------
# API pubblica — autenticazione
# ---------------------------------------------------------------------------

def login_email_password(email: str, password: str, user_agent: str | None = None) -> tuple[str, str, datetime]:
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
    if db.is_auth_rate_limited("login_password", email_norm, LOGIN_MAX_ATTEMPTS, LOGIN_WINDOW_MINUTES):
        raise AuthError("Troppi tentativi di accesso. Attendi qualche minuto e riprova.")

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
                db.register_auth_failure("login_password", email_norm, LOGIN_WINDOW_MINUTES)
                raise AuthError("Email o password non corretti.")

            _, stored_hash = row

            if not verify_password(password, stored_hash):
                db.register_auth_failure("login_password", email_norm, LOGIN_WINDOW_MINUTES)
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
        raise AuthError("Errore tecnico durante il login. Riprova.") from exc

    # ── Controllo 2FA ────────────────────────────────────────────────────
    if email_norm != _demo_email_norm():
        totp_record = db.get_totp_record(email_norm)
        if totp_record and totp_record["enabled"]:
            db.clear_auth_rate_limit("login_password", email_norm)
            raise TwoFactorRequired(email_norm, _issue_totp_challenge(email_norm, "password"))

    db.clear_auth_rate_limit("login_password", email_norm)
    token, expiry = create_session(email_norm, user_agent=user_agent)
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
    if mode == "closed":
        raise AccessDeniedError("Registrazione temporaneamente disabilitata.")
    if mode == "demo_only":
        raise AccessDeniedError("Registrazione temporaneamente disabilitata.")
    if mode == "pilot_only" and not _is_pilot_registration_allowed(email_norm):
        raise AccessDeniedError(
            "Registrazione riservata agli account invitati per questa fase di test."
        )

    if not password or len(password) < MIN_PASSWORD_LEN:
        raise AuthError(f"Password troppo corta (minimo {MIN_PASSWORD_LEN} caratteri).")

    pwd_hash = hash_password(password)
    nome_clean = (nome or "").strip() or email_norm.split("@")[0]

    try:
        with db.connetti_db() as conn:
            # Rileva le colonne disponibili (schema flessibile)
            cols = _table_columns(conn, ACCOUNT_USERS_TABLE)

            insert_cols = ["email", "password_hash"]
            insert_vals: list = [email_norm, pwd_hash]

            if "nome_utente" in cols:
                insert_cols.append("nome_utente")
                insert_vals.append(nome_clean)
            if "auth_provider" in cols:
                insert_cols.append("auth_provider")
                insert_vals.append("password")
            if "onboarding_completed" in cols:
                insert_cols.append("onboarding_completed")
                insert_vals.append(False)

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
        raise AuthError("Errore tecnico durante la registrazione. Riprova.") from exc

    logger.info("Nuovo utente registrato: %s", email_norm)


def login_google_user(email: str, nome: str = "", user_agent: str | None = None) -> tuple[str, str, datetime]:
    """
    Esegue login/provisioning per un utente Google OAuth.

    Se l'utente non esiste ancora in utenti_registrati viene creato:
      - onboarding_completed = FALSE se non ha alcun dato pregresso
      - onboarding_completed = TRUE se esistono già dati associati a quell'email
        (caso di retrocompatibilità con account Google usati prima del provisioning locale)
    """
    email_norm = _normalize_email(email)
    if not email_norm:
        raise AuthError("Email Google non valida.")

    _check_access_mode(email_norm)

    try:
        with db.connetti_db() as conn:
            _ensure_google_account(conn, email_norm, nome=nome)
    except (AuthError, AccessDeniedError):
        raise
    except Exception as exc:
        logger.error("login_google_user: %s", exc)
        raise AuthError("Errore tecnico durante il login Google. Riprova.") from exc

    if email_norm != _demo_email_norm():
        totp_record = db.get_totp_record(email_norm)
        if totp_record and totp_record["enabled"]:
            raise TwoFactorRequired(email_norm, _issue_totp_challenge(email_norm, "google"))

    token, expiry = create_session(email_norm, user_agent=user_agent)
    return email_norm, token, expiry


def is_onboarding_completed(email: str) -> bool:
    """
    Restituisce True se l'utente ha completato l'onboarding.

    In caso di schema legacy, utente mancante o errore DB restituisce True
    per non bloccare utenti esistenti.
    """
    email_norm = _normalize_email(email)
    if not email_norm:
        return True

    try:
        with db.connetti_db() as conn:
            cols = _table_columns(conn, ACCOUNT_USERS_TABLE)
            if "onboarding_completed" not in cols:
                return True
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT onboarding_completed FROM {ACCOUNT_USERS_TABLE} "
                    "WHERE email = %s LIMIT 1",
                    (email_norm,),
                )
                row = cur.fetchone()
        if not row or row[0] is None:
            return True
        return bool(row[0])
    except Exception as exc:
        logger.warning("is_onboarding_completed: %s", exc)
        return True


def get_auth_provider(email: str) -> str:
    """
    Restituisce il provider di autenticazione dell'utente.

    Valori attesi:
      - "password"
      - "google"

    In caso di schema legacy o errore restituisce "password".
    """
    email_norm = _normalize_email(email)
    if not email_norm:
        return "password"

    try:
        with db.connetti_db() as conn:
            cols = _table_columns(conn, ACCOUNT_USERS_TABLE)
            if "auth_provider" not in cols:
                return "password"
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT auth_provider FROM {ACCOUNT_USERS_TABLE} "
                    "WHERE email = %s LIMIT 1",
                    (email_norm,),
                )
                row = cur.fetchone()
        provider = str(row[0]).strip().lower() if row and row[0] else "password"
        return provider if provider in {"password", "google"} else "password"
    except Exception as exc:
        logger.warning("get_auth_provider: %s", exc)
        return "password"


def mark_onboarding_completed(email: str, completed: bool = True) -> bool:
    """Aggiorna il flag onboarding_completed per l'utente indicato."""
    email_norm = _normalize_email(email)
    if not email_norm:
        return False

    try:
        with db.connetti_db() as conn:
            cols = _table_columns(conn, ACCOUNT_USERS_TABLE)
            if "onboarding_completed" not in cols:
                return True
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE {ACCOUNT_USERS_TABLE} "
                    "SET onboarding_completed = %s WHERE email = %s",
                    (bool(completed), email_norm),
                )
                return cur.rowcount == 1
    except Exception as exc:
        logger.error("mark_onboarding_completed: %s", exc)
        return False


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


# ---------------------------------------------------------------------------
# 2FA — TOTP
# ---------------------------------------------------------------------------

def login_totp_step(
    email: str,
    totp_code: str,
    challenge_token: str,
    user_agent: str | None = None,
) -> tuple[str, str, datetime]:
    """
    Secondo step del login: verifica il codice TOTP e crea la sessione.

    Deve essere chiamata SOLO dopo che il primo step di autenticazione ha
    sollevato TwoFactorRequired per la stessa email.

    Restituisce (email_norm, token, expiry).
    Solleva AuthError se il codice è errato o il 2FA non è configurato.
    """
    email_norm = _normalize_email(email)
    if not email_norm:
        raise AuthError("Email non valida.")
    if db.is_auth_rate_limited("login_totp", email_norm, TOTP_MAX_ATTEMPTS, TOTP_WINDOW_MINUTES):
        raise AuthError("Troppi tentativi sul codice 2FA. Attendi qualche minuto e riprova.")

    challenge = db.get_pending_2fa_challenge(challenge_token)
    if not challenge or challenge["email"] != email_norm:
        raise AuthError("Verifica 2FA scaduta o non valida. Ripeti l'accesso.")

    totp_record = db.get_totp_record(email_norm)
    if not totp_record or not totp_record["enabled"]:
        raise AuthError("2FA non configurato per questo account.")

    if not verify_totp_code(totp_record["secret"], totp_code):
        db.register_auth_failure("login_totp", email_norm, TOTP_WINDOW_MINUTES)
        raise AuthError("Codice non valido. Riprova o attendi il prossimo codice.")

    if not db.consume_pending_2fa_challenge(challenge_token, email_norm):
        raise AuthError("Verifica 2FA scaduta o non valida. Ripeti l'accesso.")

    db.clear_auth_rate_limit("login_totp", email_norm)
    token, expiry = create_session(email_norm, user_agent=user_agent)
    return email_norm, token, expiry


def setup_totp_begin(email: str) -> tuple[str, str]:
    """
    Avvia il setup TOTP per l'utente:
      1. Genera un nuovo secret casuale
      2. Lo salva nel DB con enabled=FALSE
      3. Restituisce (secret_base32, otpauth_uri)

    L'URI va codificato in QR code e mostrato all'utente.
    Il setup si completa solo dopo setup_totp_confirm().
    """
    email_norm = _normalize_email(email)
    if not email_norm:
        raise AuthError("Email non valida.")
    if email_norm == _demo_email_norm():
        raise AuthError("Il 2FA non è disponibile per l'account demo.")

    secret = generate_totp_secret()
    if not db.upsert_totp_secret(email_norm, secret):
        raise AuthError("Errore durante il salvataggio del secret TOTP. Riprova tra qualche secondo.")

    uri = get_totp_uri(secret, email_norm)
    return secret, uri


def cancel_totp_login_challenge(challenge_token: str) -> None:
    """Best effort cleanup di una challenge 2FA pendente."""
    try:
        db.delete_pending_2fa_challenge(challenge_token)
    except Exception:
        pass


def setup_totp_confirm(email: str, code: str) -> bool:
    """
    Conferma il setup TOTP: verifica il codice inserito dall'utente e,
    se corretto, porta enabled=TRUE nel DB.

    Restituisce True se il codice è valido e il 2FA è stato attivato,
    False altrimenti. Non solleva mai eccezioni.
    """
    email_norm = _normalize_email(email)
    if not email_norm or email_norm == _demo_email_norm():
        return False

    record = db.get_totp_record(email_norm)
    if not record:
        return False

    if not verify_totp_code(record["secret"], code):
        return False

    return db.enable_totp(email_norm)


def disable_totp_for_user(email: str, password: str) -> tuple[bool, str]:
    """
    Disabilita il 2FA per l'utente, previa verifica della password corrente.
    La verifica password è obbligatoria come secondo fattore di sicurezza.

    Restituisce (True, messaggio_ok) oppure (False, messaggio_errore).
    """
    if not email or not password:
        return False, "Email e password sono obbligatorie."

    email_norm = _normalize_email(email)
    if not email_norm:
        return False, "Email non valida."
    if email_norm == _demo_email_norm():
        return False, "Il 2FA non è disponibile per l'account demo."

    try:
        with db.connetti_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT password_hash FROM {ACCOUNT_USERS_TABLE} WHERE email = %s",
                    (email_norm,),
                )
                row = cur.fetchone()
    except Exception as exc:
        logger.error("disable_totp_for_user — errore lettura DB: %s", exc)
        return False, "Errore interno. Riprova più tardi."

    if not row:
        return False, "Account non trovato."

    if not verify_password(password, row[0]):
        return False, "Password non corretta."

    if not db.disable_totp(email_norm):
        return False, "2FA non era attivo o errore durante la disattivazione."

    logger.info("2FA disabilitato per %s", email_norm)
    return True, "Autenticazione a due fattori disabilitata con successo."


def disable_totp_for_google_user(email: str) -> tuple[bool, str]:
    """
    Disabilita il 2FA per un account Google.

    Deve essere chiamata solo dopo che il layer UI ha confermato
    nuovamente l'identità dell'utente via OAuth Google.
    """
    email_norm = _normalize_email(email)
    if not email_norm:
        return False, "Email non valida."
    if email_norm == _demo_email_norm():
        return False, "Il 2FA non è disponibile per l'account demo."

    if not db.disable_totp(email_norm):
        return False, "2FA non era attivo o errore durante la disattivazione."

    logger.info("2FA disabilitato per account Google %s", email_norm)
    return True, "Autenticazione a due fattori disabilitata con successo."


def is_totp_enabled(email: str) -> bool:
    """
    Restituisce True se l'utente ha il TOTP abilitato.
    Utile per il layer UI (mostrare banner, stato nelle impostazioni).
    Non solleva mai eccezioni.
    """
    email_norm = _normalize_email(email)
    if not email_norm or email_norm == _demo_email_norm():
        return False
    record = db.get_totp_record(email_norm)
    return bool(record and record["enabled"])


# ---------------------------------------------------------------------------
# Recovery 2FA via email
# ---------------------------------------------------------------------------

def _provider_label(provider: str | None) -> str:
    return "Google" if str(provider or "").strip().lower() == "google" else "password"


def _email_totp_recovery_body(otp: str, ttl_minuti: int = 10, provider: str = "password") -> str:
    """Corpo HTML dell'email con il codice di recovery 2FA."""
    provider_label = _provider_label(provider)
    return (
        "<div style='font-family: sans-serif; color: #333; max-width: 480px;'>"
        "<h2 style='color:#f59e0b;'>📲 Recovery verifica in due passaggi</h2>"
        f"<p>Hai completato il primo accesso via <strong>{provider_label}</strong> "
        "e richiesto il reset del codice Authenticator.</p>"
        "<p>Usa il codice qui sotto nell'app entro "
        f"<strong>{ttl_minuti} minuti</strong> per disattivare il 2FA attuale:</p>"
        "<div style='font-size:2.2rem;font-weight:700;letter-spacing:0.3rem;"
        "color:#1a1a2e;background:#fff7e8;border-radius:10px;"
        f"padding:18px 28px;display:inline-block;margin:16px 0;'>{otp}</div>"
        "<p style='color:#888;font-size:0.85rem;'>"
        "Se non sei stato tu a richiedere questo recupero, non inserire il codice "
        "e cambia subito le credenziali del tuo account.</p>"
        "<hr style='border:0;border-top:1px solid #eee;margin:20px 0;'>"
        "<small style='color:#aaa;'>Personal Budget — assistente automatico 🤖</small>"
        "</div>"
    )


def _email_totp_recovery_confirmed_body(email: str) -> str:
    """Corpo HTML dell'email di conferma del recovery 2FA."""
    return (
        "<div style='font-family: sans-serif; color: #333; max-width: 480px;'>"
        "<h2 style='color:#10d98a;'>✅ Recovery 2FA completato</h2>"
        f"<p>La verifica in due passaggi per l'account <strong>{email}</strong> "
        "è stata disattivata con successo.</p>"
        "<p>Accedi all'app e configura nuovamente il tuo Authenticator dalle impostazioni "
        "per ripristinare la protezione a due fattori.</p>"
        "<p style='color:#e05c5c;font-size:0.88rem;'>"
        "⚠️ Se non hai richiesto tu questo recupero, cambia subito password e contatta il supporto.</p>"
        "<hr style='border:0;border-top:1px solid #eee;margin:20px 0;'>"
        "<small style='color:#aaa;'>Personal Budget — assistente automatico 🤖</small>"
        "</div>"
    )


def request_totp_recovery(
    email: str,
    challenge_token: str,
    provider: str = "password",
) -> tuple[bool, str]:
    """
    Avvia il recovery del 2FA solo dopo che il primo fattore di accesso
    è già stato superato e la challenge TOTP è ancora valida.
    """
    email_norm = _normalize_email(email)
    challenge_clean = str(challenge_token or "").strip()
    provider_norm = str(provider or "password").strip().lower() or "password"
    if provider_norm not in {"password", "google"}:
        provider_norm = "password"

    if not email_norm or not challenge_clean:
        return False, "Sessione di verifica non valida. Ripeti l'accesso."
    if email_norm == _demo_email_norm():
        return False, "Il recovery 2FA non è disponibile per l'account demo."
    if db.is_auth_rate_limited(
        "totp_recovery_request",
        email_norm,
        TOTP_RECOVERY_REQUEST_MAX_ATTEMPTS,
        TOTP_RECOVERY_REQUEST_WINDOW_MINUTES,
    ):
        return False, "Troppi invii richiesti. Attendi qualche minuto e riprova."

    challenge = db.get_pending_2fa_challenge(challenge_clean)
    if not challenge or challenge["email"] != email_norm or challenge["provider"] != provider_norm:
        return False, "Verifica 2FA scaduta o non valida. Ripeti l'accesso."

    totp_record = db.get_totp_record(email_norm)
    if not totp_record or not totp_record["enabled"]:
        return False, "2FA non configurato per questo account."

    if not db.create_pending_2fa_challenge(
        email_norm,
        challenge_clean,
        provider=provider_norm,
        ttl_minutes=TOTP_RECOVERY_TTL_MINUTES,
    ):
        return False, "Errore temporaneo durante il recovery 2FA. Riprova."

    otp = db.create_totp_recovery_token(
        email_norm,
        challenge_clean,
        provider=provider_norm,
        ttl_minuti=TOTP_RECOVERY_TTL_MINUTES,
    )
    if not otp:
        logger.error("Impossibile creare token recovery 2FA per %s", email_norm)
        return False, "Errore interno. Riprova tra qualche minuto."

    ok, msg = send_email(
        email_norm,
        "📲 Codice recovery 2FA — Personal Budget",
        _email_totp_recovery_body(otp, ttl_minuti=TOTP_RECOVERY_TTL_MINUTES, provider=provider_norm),
    )
    if not ok:
        db.register_auth_failure("totp_recovery_request", email_norm, TOTP_RECOVERY_REQUEST_WINDOW_MINUTES)
        logger.error("Invio recovery 2FA fallito per %s: %s", email_norm, msg)
        return False, f"Errore nell'invio dell'email: {msg}"

    db.register_auth_failure("totp_recovery_request", email_norm, TOTP_RECOVERY_REQUEST_WINDOW_MINUTES)
    logger.info("OTP recovery 2FA inviato a %s.", email_norm)
    return True, "Ti abbiamo inviato un codice via email per recuperare l'accesso."


def confirm_totp_recovery(
    email: str,
    otp: str,
    challenge_token: str,
    provider: str = "password",
    user_agent: str | None = None,
) -> tuple[str, str, datetime]:
    """
    Conferma il recovery 2FA: valida il codice email, disabilita il TOTP
    attuale e completa il login con una nuova sessione.
    """
    email_norm = _normalize_email(email)
    challenge_clean = str(challenge_token or "").strip()
    otp_clean = str(otp or "").strip()
    provider_norm = str(provider or "password").strip().lower() or "password"
    if provider_norm not in {"password", "google"}:
        provider_norm = "password"

    if not email_norm or not challenge_clean or not otp_clean:
        raise AuthError("Tutti i campi recovery sono obbligatori.")
    if db.is_auth_rate_limited(
        "totp_recovery_confirm",
        email_norm,
        TOTP_RECOVERY_CONFIRM_MAX_ATTEMPTS,
        TOTP_RECOVERY_CONFIRM_WINDOW_MINUTES,
    ):
        raise AuthError("Troppi tentativi di recovery 2FA. Attendi qualche minuto e richiedi un nuovo codice.")

    challenge = db.get_pending_2fa_challenge(challenge_clean)
    if not challenge or challenge["email"] != email_norm or challenge["provider"] != provider_norm:
        raise AuthError("Verifica 2FA scaduta o non valida. Ripeti l'accesso.")

    totp_record = db.get_totp_record(email_norm)
    if not totp_record or not totp_record["enabled"]:
        raise AuthError("2FA non configurato per questo account.")

    recovered = db.consume_totp_recovery_token_and_disable_totp(
        email_norm,
        challenge_clean,
        otp_clean,
        provider=provider_norm,
    )
    if not recovered:
        db.register_auth_failure("totp_recovery_confirm", email_norm, TOTP_RECOVERY_CONFIRM_WINDOW_MINUTES)
        raise AuthError("Codice recovery non valido o scaduto. Richiedi un nuovo codice.")

    db.clear_auth_rate_limit("totp_recovery_confirm", email_norm)
    db.clear_auth_rate_limit("totp_recovery_request", email_norm)
    db.clear_auth_rate_limit("login_totp", email_norm)

    token, expiry = create_session(email_norm, user_agent=user_agent)
    try:
        send_email(
            email_norm,
            "✅ Recovery 2FA completato — Personal Budget",
            _email_totp_recovery_confirmed_body(email_norm),
        )
    except Exception as exc:
        logger.warning("Email conferma recovery 2FA non inviata a %s: %s", email_norm, exc)

    logger.info("Recovery 2FA completato con successo per %s.", email_norm)
    return email_norm, token, expiry


# ---------------------------------------------------------------------------
# Gestione reset password
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)
 
# Requisiti minimi password (coerenti con register_user esistente)
_MIN_PWD_LEN = MIN_PASSWORD_LEN
 
 
def _email_otp_body(otp: str, ttl_minuti: int = 15) -> str:
    """Corpo HTML dell'email con il codice OTP."""
    return (
        "<div style='font-family: sans-serif; color: #333; max-width: 480px;'>"
        "<h2 style='color:#4f8ef0;'>🔐 Reset Password — Personal Budget</h2>"
        "<p>Hai richiesto il reset della password.<br>"
        "Usa il codice qui sotto nell'app entro "
        f"<strong>{ttl_minuti} minuti</strong>:</p>"
        "<div style='font-size:2.2rem;font-weight:700;letter-spacing:0.3rem;"
        "color:#1a1a2e;background:#f0f4ff;border-radius:10px;"
        f"padding:18px 28px;display:inline-block;margin:16px 0;'>{otp}</div>"
        "<p style='color:#888;font-size:0.85rem;'>"
        "Se non sei stato tu a richiedere il reset, ignora questa email.<br>"
        "La tua password rimane invariata.</p>"
        "<hr style='border:0;border-top:1px solid #eee;margin:20px 0;'>"
        "<small style='color:#aaa;'>Personal Budget — assistente automatico 🤖</small>"
        "</div>"
    )
 
 
def _email_conferma_body(email: str) -> str:
    """Corpo HTML dell'email di conferma avvenuto reset."""
    return (
        "<div style='font-family: sans-serif; color: #333; max-width: 480px;'>"
        "<h2 style='color:#10d98a;'>✅ Password aggiornata</h2>"
        f"<p>La password dell'account <strong>{email}</strong> è stata "
        "aggiornata con successo.</p>"
        "<p>Puoi ora accedere con la tua nuova password.</p>"
        "<p style='color:#e05c5c;font-size:0.88rem;'>"
        "⚠️ Se non hai eseguito questa operazione, contatta subito "
        "il supporto o accedi e cambia nuovamente la password.</p>"
        "<hr style='border:0;border-top:1px solid #eee;margin:20px 0;'>"
        "<small style='color:#aaa;'>Personal Budget — assistente automatico 🤖</small>"
        "</div>"
    )
 
 
def request_password_reset(email: str) -> tuple[bool, str]:
    """
    Avvia il flusso di reset password:
      1. Controlla che l'email esista (senza rivelarlo all'utente per sicurezza)
      2. Genera un OTP a 6 cifre con scadenza 15 minuti
      3. Invia l'OTP via email
 
    Restituisce (True, messaggio_ok) oppure (False, messaggio_errore).
 
    Nota di sicurezza: in caso di email inesistente restituisce comunque
    True con lo stesso messaggio, per non rivelare quali email sono registrate.
    """
    if not email:
        return False, "Inserisci un indirizzo email."
 
    email_norm = str(email).strip().lower()
    if db.is_auth_rate_limited("reset_request", email_norm, RESET_REQUEST_MAX_ATTEMPTS, RESET_REQUEST_WINDOW_MINUTES):
        logger.warning("Reset password throttled per %s", email_norm)
        return True, "Se l'indirizzo è registrato, riceverai un'email con il codice."
 
    # Controllo silenzioso: se l'email non esiste, facciamo finta di niente
    esiste = db.email_utente_esiste(email_norm)
 
    if not esiste:
        # Risposta generica per non rivelare se l'account esiste
        logger.info("Reset richiesto per email inesistente: %s", email_norm)
        return True, "Se l'indirizzo è registrato, riceverai un'email con il codice."
 
    otp = db.crea_reset_token(email_norm, ttl_minuti=15)
    if not otp:
        logger.error("Impossibile creare token reset per %s", email_norm)
        return False, "Errore interno. Riprova tra qualche minuto."
 
    ok, msg = send_email(
        email_norm,
        "🔐 Codice di reset password — Personal Budget",
        _email_otp_body(otp, ttl_minuti=15),
    )
    if not ok:
        db.register_auth_failure("reset_request", email_norm, RESET_REQUEST_WINDOW_MINUTES)
        logger.error("Invio OTP fallito per %s: %s", email_norm, msg)
        return False, f"Errore nell'invio dell'email: {msg}"
 
    db.register_auth_failure("reset_request", email_norm, RESET_REQUEST_WINDOW_MINUTES)
    logger.info("OTP reset inviato a %s.", email_norm)
    return True, "Se l'indirizzo è registrato, riceverai un'email con il codice."
 
 
def confirm_password_reset(email: str, otp: str, nuova_password: str) -> tuple[bool, str]:
    """
    Conferma il reset password:
      1. Valida i requisiti della nuova password
      2. Verifica l'OTP (valido, non scaduto, non usato) e lo consuma
      3. Aggiorna il password_hash in DB
      4. Invia email di conferma
 
    Restituisce (True, messaggio_ok) oppure (False, messaggio_errore).
    """
    if not email or not otp or not nuova_password:
        return False, "Tutti i campi sono obbligatori."
 
    email_norm = str(email).strip().lower()
    otp_clean = str(otp).strip()
    if db.is_auth_rate_limited("reset_confirm", email_norm, RESET_CONFIRM_MAX_ATTEMPTS, RESET_CONFIRM_WINDOW_MINUTES):
        return False, "Troppi tentativi di reset. Attendi qualche minuto e richiedi un nuovo codice."
 
    # ── Validazione password ──────────────────────────────────────────────
    if len(nuova_password) < _MIN_PWD_LEN:
        return False, f"La password deve essere di almeno {_MIN_PWD_LEN} caratteri."
 
    # ── Verifica OTP (atomico nel DB) ─────────────────────────────────────
    valido = db.verifica_e_consuma_token(email_norm, otp_clean)
    if not valido:
        db.register_auth_failure("reset_confirm", email_norm, RESET_CONFIRM_WINDOW_MINUTES)
        return False, "Codice non valido o scaduto. Richiedi un nuovo codice."
 
    # ── Aggiornamento hash ────────────────────────────────────────────────
    nuovo_hash = hash_password(nuova_password)
    aggiornato = db.aggiorna_password_hash(email_norm, nuovo_hash)
    if not aggiornato:
        logger.error("aggiorna_password_hash fallito per %s", email_norm)
        return False, "Errore interno durante l'aggiornamento. Riprova."

    db.delete_sessions_for_user(email_norm)
    db.delete_pending_2fa_for_user(email_norm)
    db.clear_auth_rate_limit("reset_confirm", email_norm)
 
    # ── Email di conferma (best-effort, non blocca il flusso) ────────────
    try:
        send_email(
            email_norm,
            "✅ Password aggiornata — Personal Budget",
            _email_conferma_body(email_norm),
        )
    except Exception as exc:
        logger.warning("Email conferma reset non inviata a %s: %s", email_norm, exc)
 
    logger.info("Password aggiornata con successo per %s.", email_norm)
    return True, "Password aggiornata con successo! Ora puoi accedere."

# ── Elimina account utente ──────────────────────────────────────────────

def delete_user_account(email: str, password: str) -> tuple[bool, str]:
    """
    Elimina l'account utente previa verifica della password.
 
    Flusso:
      1. Verifica che email e password siano corrette (richiede login valido)
      2. Chiama db.elimina_account_utente() che rimuove tutti i dati
      3. Restituisce (True, messaggio) o (False, errore)
 
    La verifica della password è obbligatoria come secondo fattore
    di sicurezza prima di un'operazione irreversibile.
    """
    if not email or not password:
        return False, "Email e password sono obbligatorie."
 
    email_norm = str(email).strip().lower()
 
    # Recupera l'hash dal DB e verifica la password
    try:
        with db.connetti_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT password_hash FROM utenti_registrati WHERE email = %s",
                    (email_norm,),
                )
                row = cursor.fetchone()
    except Exception as exc:
        logger.error("delete_user_account — errore lettura DB: %s", exc)
        return False, "Errore interno. Riprova più tardi."
 
    if not row:
        return False, "Account non trovato."
 
    stored_hash = row[0]
    if not verify_password(password, stored_hash):
        return False, "Password non corretta."
 
    # Eliminazione completa
    try:
        conteggio = db.elimina_account_utente(email_norm)
    except Exception as exc:
        logger.error("delete_user_account — eliminazione fallita per %s: %s", email_norm, exc)
        return False, f"Errore durante l'eliminazione: {exc}"
 
    totale = sum(conteggio.values())
    logger.info(
        "Account %s eliminato con successo. Totale righe rimosse: %d",
        email_norm, totale,
    )
    return True, "Account eliminato con successo."
