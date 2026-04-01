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
from gmail_sender import send_email

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


# ---------------------------------------------------------------------------
# Gestione reset password
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)
 
# Requisiti minimi password (coerenti con register_user esistente)
_MIN_PWD_LEN = 8
 
 
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
        logger.error("Invio OTP fallito per %s: %s", email_norm, msg)
        return False, f"Errore nell'invio dell'email: {msg}"
 
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
 
    # ── Validazione password ──────────────────────────────────────────────
    if len(nuova_password) < _MIN_PWD_LEN:
        return False, f"La password deve essere di almeno {_MIN_PWD_LEN} caratteri."
 
    # ── Verifica OTP (atomico nel DB) ─────────────────────────────────────
    valido = db.verifica_e_consuma_token(email_norm, otp_clean)
    if not valido:
        return False, "Codice non valido o scaduto. Richiedi un nuovo codice."
 
    # ── Aggiornamento hash ────────────────────────────────────────────────
    nuovo_hash = hash_password(nuova_password)
    aggiornato = db.aggiorna_password_hash(email_norm, nuovo_hash)
    if not aggiornato:
        logger.error("aggiorna_password_hash fallito per %s", email_norm)
        return False, "Errore interno durante l'aggiornamento. Riprova."
 
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
