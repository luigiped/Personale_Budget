"""
Database.py
-----------
Layer di accesso ai dati — FRAMEWORK AGNOSTIC.

Non importa framework UI.
Dipende solo da: psycopg2, pandas, config_runtime.

Novità rispetto alla versione precedente:
  - Rimosso import streamlit — usa config_runtime.get_secret()
  - Connection pooling con psycopg2.pool.ThreadedConnectionPool
  - Cache dati con TTL esplicito (no st.cache_data)
  - Migrazioni versionizzate tramite tabella schema_migrations
  - verifica_password() rimossa (spostata in security.py)
"""

import logging
import random
import string
import os
import re
import threading
import time
from datetime import date as dt_date
from datetime import datetime
from urllib.parse import urlsplit

import pandas as pd
import psycopg2
import psycopg2.pool

from config_runtime import get_secret

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection pool
# ---------------------------------------------------------------------------

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()

_POOL_MIN = 1
_POOL_MAX = 8  # adeguato a Supabase free tier (max 15 connessioni)


def _sanitize_db_url(db_url: str) -> str:
    if not db_url:
        return db_url
    return re.sub(r"@\[([A-Za-z0-9.\-]+)\]", r"@\1", str(db_url).strip())


def _extract_host(db_url: str) -> str:
    try:
        host = urlsplit(db_url).hostname
    except Exception:
        host = None
    if host:
        return host
    tail = str(db_url).split("@", 1)[-1].split("/", 1)[0]
    if tail.startswith("[") and "]" in tail:
        return tail[1:tail.index("]")]
    return tail.split(":", 1)[0]


def _candidate_db_urls() -> list[str]:
    """Legge i candidati URL dal sistema di configurazione unificato."""
    seen: set[str] = set()
    urls: list[str] = []
    for key in ("DATABASE_URL", "DATABASE_URL_POOLER"):
        raw = get_secret(key)
        if raw:
            url = _sanitize_db_url(raw)
            if url not in seen:
                urls.append(url)
                seen.add(url)
    return urls


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Restituisce il pool condiviso, creandolo se necessario."""
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is not None:
            return _pool
        candidates = _candidate_db_urls()
        if not candidates:
            raise RuntimeError("Nessuna stringa DB trovata nelle variabili d'ambiente o secrets.")
        errors = []
        for uri in candidates:
            host = _extract_host(uri)
            try:
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    _POOL_MIN, _POOL_MAX, uri
                )
                logger.info("Pool DB creato su %s (min=%d, max=%d).", host, _POOL_MIN, _POOL_MAX)
                return _pool
            except Exception as exc:
                errors.append(f"{host}: {str(exc).splitlines()[0]}")
        raise RuntimeError(f"Connessione DB fallita: {' | '.join(errors)}")


class _DBConn:
    """
    Context manager che prende una connessione dal pool al __enter__
    e la rilascia al __exit__ (con commit o rollback automatico).
    """

    def __init__(self):
        self._conn = None

    def __enter__(self):
        self._conn = _get_pool().getconn()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._conn is None:
            return False
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            _get_pool().putconn(self._conn)
            self._conn = None
        return False

    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    # Supporto pd.read_sql_query che usa il connection object direttamente
    def __getattr__(self, name):
        return getattr(self._conn, name)


def connetti_db() -> _DBConn:
    """
    Restituisce un context manager che gestisce una connessione dal pool.

    Uso:
        with connetti_db() as conn:
            with conn.cursor() as cur:
                cur.execute(...)
    """
    return _DBConn()


# ---------------------------------------------------------------------------
# Cache dati in memoria con TTL
# ---------------------------------------------------------------------------

class _TTLCache:
    """
    Cache dizionario thread-safe con TTL per chiave.
    Usata al posto di st.cache_data per rendere il layer dati framework-agnostic.
    """

    def __init__(self, ttl_seconds: int = 60):
        self._store: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def get(self, key: str):
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, value = entry
            if time.monotonic() - ts > self._ttl:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value) -> None:
        with self._lock:
            self._store[key] = (time.monotonic(), value)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> None:
        with self._lock:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


_cache_movimenti = _TTLCache(ttl_seconds=60)
_cache_spese = _TTLCache(ttl_seconds=60)
_cache_finanziamenti = _TTLCache(ttl_seconds=60)
_cache_pac = _TTLCache(ttl_seconds=300)


# ---------------------------------------------------------------------------
# Migrazioni DB versionizzate
# ---------------------------------------------------------------------------

def _ensure_migrations_table(cursor) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     INTEGER PRIMARY KEY,
            applied_at  TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            description TEXT
        )
    """)


def _applied_versions(cursor) -> set[int]:
    cursor.execute("SELECT version FROM schema_migrations")
    return {row[0] for row in cursor.fetchall()}


def _mark_applied(cursor, version: int, description: str) -> None:
    cursor.execute(
        "INSERT INTO schema_migrations (version, description) VALUES (%s, %s) "
        "ON CONFLICT (version) DO NOTHING",
        (version, description),
    )


# Ogni migrazione è (version: int, description: str, sql_statements: list[str])
# Aggiungi sempre in fondo — non modificare le migrazioni già applicate.
_MIGRATIONS: list[tuple[int, str, list[str]]] = [
    (1, "Aggiunta colonna user_email a tutte le tabelle principali", [
        "ALTER TABLE movimenti ADD COLUMN IF NOT EXISTS user_email TEXT DEFAULT 'admin'",
        "ALTER TABLE asset_settings ADD COLUMN IF NOT EXISTS user_email TEXT DEFAULT 'admin'",
        "ALTER TABLE finanziamenti ADD COLUMN IF NOT EXISTS user_email TEXT DEFAULT 'admin'",
        "ALTER TABLE spese_ricorrenti ADD COLUMN IF NOT EXISTS user_email TEXT DEFAULT 'admin'",
        "ALTER TABLE movimenti ALTER COLUMN user_email DROP DEFAULT",
        "ALTER TABLE asset_settings ALTER COLUMN user_email DROP DEFAULT",
        "ALTER TABLE finanziamenti ALTER COLUMN user_email DROP DEFAULT",
        "ALTER TABLE spese_ricorrenti ALTER COLUMN user_email DROP DEFAULT",
    ]),
    (2, "Aggiornamento PK composte per asset_settings e finanziamenti", [
        "ALTER TABLE asset_settings DROP CONSTRAINT IF EXISTS asset_settings_pkey CASCADE",
        "ALTER TABLE asset_settings ADD PRIMARY KEY (chiave, user_email)",
        "ALTER TABLE finanziamenti DROP CONSTRAINT IF EXISTS finanziamenti_pkey CASCADE",
        "ALTER TABLE finanziamenti ADD PRIMARY KEY (nome, user_email)",
    ]),
    (3, "Aggiunta colonne mancanti a tutte le tabelle", [
        "ALTER TABLE movimenti ADD COLUMN IF NOT EXISTS data TIMESTAMP",
        "ALTER TABLE movimenti ADD COLUMN IF NOT EXISTS tipo TEXT",
        "ALTER TABLE movimenti ADD COLUMN IF NOT EXISTS categoria TEXT",
        "ALTER TABLE movimenti ADD COLUMN IF NOT EXISTS dettaglio TEXT",
        "ALTER TABLE movimenti ADD COLUMN IF NOT EXISTS importo DOUBLE PRECISION",
        "ALTER TABLE movimenti ADD COLUMN IF NOT EXISTS note TEXT",
        "ALTER TABLE asset_settings ADD COLUMN IF NOT EXISTS valore_numerico DOUBLE PRECISION",
        "ALTER TABLE asset_settings ADD COLUMN IF NOT EXISTS valore_testo TEXT",
        "ALTER TABLE finanziamenti ADD COLUMN IF NOT EXISTS capitale_iniziale DOUBLE PRECISION",
        "ALTER TABLE finanziamenti ADD COLUMN IF NOT EXISTS taeg DOUBLE PRECISION",
        "ALTER TABLE finanziamenti ADD COLUMN IF NOT EXISTS durata_mesi INTEGER",
        "ALTER TABLE finanziamenti ADD COLUMN IF NOT EXISTS data_inizio DATE",
        "ALTER TABLE finanziamenti ADD COLUMN IF NOT EXISTS giorno_scadenza INTEGER",
        "ALTER TABLE finanziamenti ADD COLUMN IF NOT EXISTS rate_pagate INTEGER",
        "ALTER TABLE spese_ricorrenti ADD COLUMN IF NOT EXISTS descrizione TEXT",
        "ALTER TABLE spese_ricorrenti ADD COLUMN IF NOT EXISTS importo DOUBLE PRECISION",
        "ALTER TABLE spese_ricorrenti ADD COLUMN IF NOT EXISTS giorno_scadenza INTEGER",
        "ALTER TABLE spese_ricorrenti ADD COLUMN IF NOT EXISTS frequenza_mesi INTEGER",
        "ALTER TABLE spese_ricorrenti ADD COLUMN IF NOT EXISTS data_inizio DATE",
        "ALTER TABLE spese_ricorrenti ADD COLUMN IF NOT EXISTS data_fine DATE",
        "ALTER TABLE notifiche_scadenze ADD COLUMN IF NOT EXISTS chiave_evento TEXT",
        "ALTER TABLE notifiche_scadenze ADD COLUMN IF NOT EXISTS destinatario TEXT",
        "ALTER TABLE notifiche_scadenze ADD COLUMN IF NOT EXISTS data_scadenza DATE",
        "ALTER TABLE notifiche_scadenze ADD COLUMN IF NOT EXISTS inviato_il TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE utenti_notifiche ADD COLUMN IF NOT EXISTS email TEXT",
        "ALTER TABLE utenti_notifiche ADD COLUMN IF NOT EXISTS attivo BOOLEAN DEFAULT TRUE",
        "ALTER TABLE utenti_notifiche ADD COLUMN IF NOT EXISTS ultimo_login TIMESTAMP",
    ]),
    (4, "Creazione indici per performance", [
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_utenti_notifiche_email ON utenti_notifiche (email)",
        "CREATE INDEX IF NOT EXISTS idx_movimenti_data_id ON movimenti (data DESC, id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_movimenti_user_email_data_id ON movimenti (user_email, data DESC, id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_movimenti_user_email_categoria_upper ON movimenti (user_email, UPPER(categoria))",
        "CREATE INDEX IF NOT EXISTS idx_finanziamenti_user_email ON finanziamenti (user_email)",
        "CREATE INDEX IF NOT EXISTS idx_spese_ricorrenti_user_email_descrizione ON spese_ricorrenti (user_email, descrizione)",
    ]),
    (5, "Aggiunta tabella utenti_registrati se non esiste", [
        """CREATE TABLE IF NOT EXISTS utenti_registrati (
            email           TEXT PRIMARY KEY,
            password_hash   TEXT NOT NULL,
            nome_utente     TEXT,
            creato_il       TIMESTAMPTZ DEFAULT NOW()
        )""",
    ]),
    (6, "Aggiunta user_email e FK a notifiche_scadenze", [
    "ALTER TABLE notifiche_scadenze ADD COLUMN IF NOT EXISTS user_email TEXT",
    "UPDATE notifiche_scadenze SET user_email = LOWER(TRIM(destinatario)) WHERE user_email IS NULL AND destinatario IS NOT NULL",
    "DELETE FROM notifiche_scadenze n WHERE user_email IS NOT NULL AND NOT EXISTS (SELECT 1 FROM utenti_registrati u WHERE LOWER(TRIM(u.email)) = LOWER(TRIM(n.user_email)))",
    "ALTER TABLE notifiche_scadenze DROP CONSTRAINT IF EXISTS fk_notifiche_scadenze_user_email",
    "ALTER TABLE notifiche_scadenze ADD CONSTRAINT fk_notifiche_scadenze_user_email FOREIGN KEY (user_email) REFERENCES utenti_registrati(email) ON DELETE CASCADE",
    "CREATE INDEX IF NOT EXISTS idx_notifiche_scadenze_user_email ON notifiche_scadenze (user_email)",
]),
    (7, "Creazione tabella password_reset_tokens", [
    """CREATE TABLE IF NOT EXISTS password_reset_tokens (
        id          SERIAL PRIMARY KEY,
        email       TEXT NOT NULL
                        REFERENCES utenti_registrati(email)
                        ON DELETE CASCADE,
        otp         TEXT NOT NULL,
        expires_at  TIMESTAMPTZ NOT NULL,
        used        BOOLEAN DEFAULT FALSE,
        created_at  TIMESTAMPTZ DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_prt_email ON password_reset_tokens (email)",
    "CREATE INDEX IF NOT EXISTS idx_prt_expires ON password_reset_tokens (expires_at)",
])
]


def _applica_migrazioni(cursor) -> None:
    """Applica solo le migrazioni non ancora applicate. Idempotente."""
    _ensure_migrations_table(cursor)
    applied = _applied_versions(cursor)

    for version, description, statements in _MIGRATIONS:
        if version in applied:
            continue
        logger.info("Applicazione migrazione v%d: %s", version, description)
        for sql in statements:
            try:
                cursor.execute(sql)
            except Exception as exc:
                # Alcune migrazioni DDL possono fallire se già applicate
                # (es. DROP CONSTRAINT su tabelle nuove). Logghiamo e continuiamo.
                logger.warning("Migrazione v%d: istruzione ignorata (%s): %s", version, sql[:60], exc)
        _mark_applied(cursor, version, description)
        logger.info("Migrazione v%d applicata.", version)


# ---------------------------------------------------------------------------
# Inizializzazione DB
# ---------------------------------------------------------------------------

def inizializza_db() -> None:
    """
    Crea le tabelle principali e applica le migrazioni pendenti.
    Sicuro da chiamare a ogni avvio — tutte le operazioni sono idempotenti.
    """
    with connetti_db() as conn:
        with conn.cursor() as cursor:
            # Tabelle base (CREATE IF NOT EXISTS — idempotenti)
            cursor.execute("""CREATE TABLE IF NOT EXISTS movimenti (
                id SERIAL PRIMARY KEY, data TIMESTAMP, tipo TEXT, categoria TEXT,
                dettaglio TEXT, importo DOUBLE PRECISION, note TEXT, user_email TEXT)""")

            cursor.execute("""CREATE TABLE IF NOT EXISTS asset_settings (
                chiave TEXT, user_email TEXT, valore_numerico DOUBLE PRECISION,
                valore_testo TEXT, PRIMARY KEY (chiave, user_email))""")

            cursor.execute("""CREATE TABLE IF NOT EXISTS finanziamenti (
                nome TEXT, user_email TEXT, capitale_iniziale DOUBLE PRECISION,
                taeg DOUBLE PRECISION, durata_mesi INTEGER, data_inizio DATE,
                giorno_scadenza INTEGER, rate_pagate INTEGER,
                PRIMARY KEY (nome, user_email))""")

            cursor.execute("""CREATE TABLE IF NOT EXISTS spese_ricorrenti (
                id SERIAL PRIMARY KEY, descrizione TEXT, importo DOUBLE PRECISION,
                giorno_scadenza INTEGER, frequenza_mesi INTEGER,
                data_inizio DATE, data_fine DATE, user_email TEXT)""")

            cursor.execute("""CREATE TABLE IF NOT EXISTS notifiche_scadenze (
            id SERIAL PRIMARY KEY, chiave_evento TEXT UNIQUE, destinatario TEXT,
            data_scadenza DATE, inviato_il TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_email TEXT)""")

            cursor.execute("""CREATE TABLE IF NOT EXISTS utenti_notifiche (
                email TEXT PRIMARY KEY, attivo BOOLEAN DEFAULT TRUE,
                ultimo_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

            cursor.execute("""CREATE TABLE IF NOT EXISTS active_sessions (
                token TEXT PRIMARY KEY, user_email TEXT NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL)""")

            _applica_migrazioni(cursor)


def pulisci_sessioni_scadute() -> None:
    """Elimina sessioni scadute e notifiche vecchie (> 90 giorni)."""
    try:
        with connetti_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM active_sessions WHERE expires_at < NOW()")
                sessioni = cursor.rowcount
                cursor.execute(
                    "DELETE FROM notifiche_scadenze "
                    "WHERE inviato_il < NOW() - INTERVAL '90 days'"
                )
                notifiche = cursor.rowcount
        if sessioni > 0 or notifiche > 0:
            logger.info(
                "Pulizia DB: %d sessioni scadute, %d notifiche vecchie rimosse.",
                sessioni, notifiche,
            )
    except Exception as exc:
        logger.warning("pulisci_sessioni_scadute: %s", exc)


# ---------------------------------------------------------------------------
# Scrittura dati
# ---------------------------------------------------------------------------

def aggiungi_movimento(data, tipo, categoria, dettaglio, importo, note, user_email: str) -> None:
    now = datetime.now().replace(microsecond=0)
    try:
        if isinstance(data, datetime):
            dt_value = data
        elif isinstance(data, dt_date):
            dt_value = datetime.combine(data, now.time())
        else:
            parsed = pd.to_datetime(data, errors="coerce")
            dt_value = parsed.to_pydatetime() if not pd.isna(parsed) else now
        if isinstance(data, str) and ":" not in str(data):
            dt_value = dt_value.replace(hour=now.hour, minute=now.minute, second=now.second)
        data_db = dt_value.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        data_db = now.strftime("%Y-%m-%d %H:%M:%S")

    tipo_norm = str(tipo).upper().strip().replace("ENTRATE", "ENTRATA").replace("USCITE", "USCITA")
    cat_norm = str(categoria).upper().strip()

    with connetti_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO movimenti "
                "(data, tipo, categoria, dettaglio, importo, note, user_email) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (data_db, tipo_norm, cat_norm, dettaglio, importo, note, user_email),
            )
    _cache_movimenti.invalidate(user_email)
    _cache_pac.invalidate(user_email)


def imposta_parametro(chiave: str, valore_num=None, valore_txt=None, user_email: str = "admin") -> None:
    user_email_norm = str(user_email).strip().lower() if user_email else "admin"
    chiave_norm = str(chiave).strip()
    if not chiave_norm:
        raise ValueError("Chiave parametro non valida.")
    with connetti_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO asset_settings (chiave, valore_numerico, valore_testo, user_email) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (chiave, user_email) DO UPDATE SET "
                "valore_numerico = EXCLUDED.valore_numerico, "
                "valore_testo = EXCLUDED.valore_testo",
                (chiave_norm, valore_num, valore_txt, user_email_norm),
            )


def aggiungi_finanziamento(nome, capitale, taeg, durata, data_inizio, scadenza, rate_pagate, user_email: str) -> None:
    with connetti_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO finanziamenti "
                "(nome, capitale_iniziale, taeg, durata_mesi, data_inizio, giorno_scadenza, rate_pagate, user_email) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (nome, user_email) DO UPDATE SET "
                "capitale_iniziale = EXCLUDED.capitale_iniziale, taeg = EXCLUDED.taeg, "
                "durata_mesi = EXCLUDED.durata_mesi, data_inizio = EXCLUDED.data_inizio, "
                "giorno_scadenza = EXCLUDED.giorno_scadenza, rate_pagate = EXCLUDED.rate_pagate",
                (nome, capitale, taeg, durata, data_inizio, scadenza, rate_pagate, user_email),
            )
    _cache_finanziamenti.invalidate(user_email)


def aggiungi_spesa_ricorrente(descrizione, importo, giorno_scadenza, frequenza_mesi, data_inizio, data_fine, user_email: str) -> None:
    with connetti_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO spese_ricorrenti "
                "(descrizione, importo, giorno_scadenza, frequenza_mesi, data_inizio, data_fine, user_email) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (descrizione, importo, giorno_scadenza, frequenza_mesi, data_inizio, data_fine, user_email),
            )
    _cache_spese.invalidate(user_email)


# ---------------------------------------------------------------------------
# Eliminazione dati
# ---------------------------------------------------------------------------

def elimina_movimento(mov_id: int, user_email: str) -> None:
    with connetti_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM movimenti WHERE id = %s AND user_email = %s",
                (mov_id, user_email),
            )
    _cache_movimenti.invalidate(user_email)
    _cache_pac.invalidate(user_email)


def elimina_finanziamento(nome: str, user_email: str) -> None:
    with connetti_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM finanziamenti WHERE nome = %s AND user_email = %s",
                (nome, user_email),
            )
    _cache_finanziamenti.invalidate(user_email)


def elimina_spesa_ricorrente(spesa_id: int, user_email: str) -> None:
    with connetti_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM spese_ricorrenti WHERE id = %s AND user_email = %s",
                (spesa_id, user_email),
            )
    _cache_spese.invalidate(user_email)


# ---------------------------------------------------------------------------
# Lettura dati (con cache TTL)
# ---------------------------------------------------------------------------

def carica_dati(user_email: str) -> pd.DataFrame:
    cached = _cache_movimenti.get(user_email)
    if cached is not None:
        return cached
    with connetti_db() as conn:
        df = pd.read_sql_query(
            "SELECT * FROM movimenti WHERE user_email = %s ORDER BY data DESC, id DESC",
            conn,
            params=(user_email,),
        )
    _cache_movimenti.set(user_email, df)
    return df


def carica_spese_ricorrenti(user_email: str) -> pd.DataFrame:
    cached = _cache_spese.get(user_email)
    if cached is not None:
        return cached
    try:
        with connetti_db() as conn:
            df = pd.read_sql_query(
                "SELECT * FROM spese_ricorrenti WHERE user_email = %s ORDER BY descrizione ASC",
                conn,
                params=(user_email,),
            )
    except Exception:
        df = pd.DataFrame()
    _cache_spese.set(user_email, df)
    return df


def carica_finanziamenti(user_email: str) -> pd.DataFrame:
    cached = _cache_finanziamenti.get(user_email)
    if cached is not None:
        return cached
    with connetti_db() as conn:
        df = pd.read_sql_query(
            "SELECT * FROM finanziamenti WHERE user_email = %s",
            conn,
            params=(user_email,),
        )
    _cache_finanziamenti.set(user_email, df)
    return df


def recupera_investimento_pac_db(user_email: str) -> float:
    cached = _cache_pac.get(user_email)
    if cached is not None:
        return cached
    with connetti_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT SUM(importo) FROM movimenti "
                "WHERE (categoria = 'PAC' OR dettaglio = 'PAC' OR tipo = 'PAC') "
                "AND user_email = %s",
                (user_email,),
            )
            risultato = cursor.fetchone()[0]
    value = float(risultato) if risultato else 0.0
    _cache_pac.set(user_email, value)
    return value


def recupera_totale_per_categoria(categoria: str, user_email: str) -> float:
    with connetti_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT SUM(importo) FROM movimenti WHERE UPPER(categoria) = %s AND user_email = %s",
                (categoria.upper(), user_email),
            )
            risultato = cursor.fetchone()[0]
    return float(risultato) if risultato else 0.0


# ---------------------------------------------------------------------------
# Notifiche e sessioni
# ---------------------------------------------------------------------------

def registra_notifica_scadenza(
    chiave_evento: str,
    destinatario: str,
    data_scadenza=None,
    user_email: str | None = None,
) -> None:
    destinatario_norm = str(destinatario).strip().lower() if destinatario else None
    user_email_norm = str(user_email).strip().lower() if user_email else destinatario_norm

    with connetti_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO notifiche_scadenze "
                "(chiave_evento, destinatario, data_scadenza, user_email) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (chiave_evento) DO NOTHING",
                (chiave_evento, destinatario_norm, data_scadenza, user_email_norm),
            )


def registra_utente_notifiche(email: str, attivo: bool = True) -> None:
    if not email:
        return
    email_norm = str(email).strip().lower()
    if not email_norm:
        return
    with connetti_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO utenti_notifiche (email, attivo, ultimo_login) "
                "VALUES (%s, %s, CURRENT_TIMESTAMP) "
                "ON CONFLICT (email) DO UPDATE SET "
                "attivo = EXCLUDED.attivo, ultimo_login = CURRENT_TIMESTAMP",
                (email_norm, bool(attivo)),
            )


def notifica_scadenza_gia_inviata(chiave_evento: str) -> bool:
    with connetti_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM notifiche_scadenze WHERE chiave_evento = %s LIMIT 1",
                (chiave_evento,),
            )
            return cursor.fetchone() is not None


def lista_destinatari_notifiche() -> list[str]:
    with connetti_db() as conn:
        with conn.cursor() as cursor:
            destinatari: set[str] = set()
            try:
                cursor.execute(
                    "SELECT DISTINCT LOWER(TRIM(email)) FROM utenti_notifiche "
                    "WHERE attivo = TRUE AND email IS NOT NULL"
                )
                for (email,) in cursor.fetchall():
                    if email:
                        destinatari.add(str(email).strip().lower())
            except Exception:
                pass
    return sorted(destinatari)

# ---------------------------------------------------------------------------
# Reset password token management
# ---------------------------------------------------------------------------
def email_utente_esiste(email: str) -> bool:
    """
    Restituisce True se l'email è registrata in utenti_registrati.
    Usata prima di generare un OTP per non rivelare indirizzi inesistenti
    nel messaggio di errore (sicurezza: rispondi sempre "se esiste, riceverai…").
    """
    if not email:
        return False
    email_norm = str(email).strip().lower()
    try:
        with connetti_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM utenti_registrati WHERE email = %s LIMIT 1",
                    (email_norm,),
                )
                return cursor.fetchone() is not None
    except Exception as exc:
        logger.error("email_utente_esiste: %s", exc)
        return False
 
 
def crea_reset_token(email: str, ttl_minuti: int = 15) -> str | None:
    """
    Genera un OTP numerico a 6 cifre, lo salva nel DB con scadenza
    `ttl_minuti` e restituisce l'OTP in chiaro (da inviare via email).
 
    Prima di inserire il nuovo token, invalida tutti i token precedenti
    non ancora scaduti per la stessa email (evita accumulo).
 
    Restituisce None in caso di errore.
    """
    if not email:
        return None
    email_norm = str(email).strip().lower()
    otp = "".join(random.choices(string.digits, k=6))
 
    try:
        with connetti_db() as conn:
            with conn.cursor() as cursor:
                # Invalida i token precedenti ancora attivi
                cursor.execute(
                    "UPDATE password_reset_tokens SET used = TRUE "
                    "WHERE email = %s AND used = FALSE AND expires_at > NOW()",
                    (email_norm,),
                )
                # Inserisce il nuovo token
                cursor.execute(
                    "INSERT INTO password_reset_tokens (email, otp, expires_at) "
                    "VALUES (%s, %s, NOW() + INTERVAL '%s minutes')",
                    (email_norm, otp, ttl_minuti),
                )
        logger.info("Reset token creato per %s (scade in %d min).", email_norm, ttl_minuti)
        return otp
    except Exception as exc:
        logger.error("crea_reset_token: %s", exc)
        return None
 
 
def verifica_e_consuma_token(email: str, otp: str) -> bool:
    """
    Verifica che l'OTP sia valido (corretto, non scaduto, non già usato)
    e lo marca come 'used = TRUE' in modo atomico.
 
    Restituisce True solo se tutto è corretto.
    """
    if not email or not otp:
        return False
    email_norm = str(email).strip().lower()
    otp_clean = str(otp).strip()
 
    try:
        with connetti_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE password_reset_tokens
                    SET    used = TRUE
                    WHERE  email      = %s
                      AND  otp        = %s
                      AND  used       = FALSE
                      AND  expires_at > NOW()
                    """,
                    (email_norm, otp_clean),
                )
                return cursor.rowcount == 1
    except Exception as exc:
        logger.error("verifica_e_consuma_token: %s", exc)
        return False
 
 
def aggiorna_password_hash(email: str, nuovo_hash: str) -> bool:
    """
    Aggiorna il campo password_hash in utenti_registrati.
    Da chiamare SOLO dopo aver verificato con successo il token OTP.
 
    Restituisce True se la riga è stata aggiornata, False altrimenti.
    """
    if not email or not nuovo_hash:
        return False
    email_norm = str(email).strip().lower()
 
    try:
        with connetti_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE utenti_registrati SET password_hash = %s WHERE email = %s",
                    (nuovo_hash, email_norm),
                )
                return cursor.rowcount == 1
    except Exception as exc:
        logger.error("aggiorna_password_hash: %s", exc)
        return False

# ---------------------------------------------------------------------------
# Eliminazione account utente e dati collegati
# ---------------------------------------------------------------------------

def elimina_account_utente(email: str) -> dict:
    """
    Elimina l'account utente e TUTTI i dati collegati nel DB.
 
    Ordine di eliminazione (rispetta le FK):
      1. movimenti           — user_email (no FK, manuale)
      2. asset_settings      — user_email (no FK, manuale)
      3. finanziamenti       — user_email (no FK, manuale)
      4. spese_ricorrenti    — user_email (no FK, manuale)
      5. active_sessions     — user_email (no FK, manuale)
      6. utenti_notifiche    — email PK   (no FK, manuale)
      7. utenti_registrati   — email PK   (CASCADE su notifiche_scadenze
                                           e password_reset_tokens)
 
    Restituisce un dizionario con il conteggio delle righe eliminate
    per tabella, utile per il log e l'eventuale UI di conferma.
    Solleva un'eccezione in caso di errore — il chiamante decide come gestirla.
    """
    if not email:
        raise ValueError("Email non fornita.")
 
    email_norm = str(email).strip().lower()
    conteggio: dict[str, int] = {}
 
    with connetti_db() as conn:
        with conn.cursor() as cursor:
 
            # 1. movimenti
            cursor.execute(
                "DELETE FROM movimenti WHERE LOWER(TRIM(user_email)) = %s",
                (email_norm,),
            )
            conteggio["movimenti"] = cursor.rowcount
 
            # 2. asset_settings
            cursor.execute(
                "DELETE FROM asset_settings WHERE LOWER(TRIM(user_email)) = %s",
                (email_norm,),
            )
            conteggio["asset_settings"] = cursor.rowcount
 
            # 3. finanziamenti
            cursor.execute(
                "DELETE FROM finanziamenti WHERE LOWER(TRIM(user_email)) = %s",
                (email_norm,),
            )
            conteggio["finanziamenti"] = cursor.rowcount
 
            # 4. spese_ricorrenti
            cursor.execute(
                "DELETE FROM spese_ricorrenti WHERE LOWER(TRIM(user_email)) = %s",
                (email_norm,),
            )
            conteggio["spese_ricorrenti"] = cursor.rowcount
 
            # 5. active_sessions
            cursor.execute(
                "DELETE FROM active_sessions WHERE LOWER(TRIM(user_email)) = %s",
                (email_norm,),
            )
            conteggio["active_sessions"] = cursor.rowcount
 
            # 6. utenti_notifiche (PK = email, nessuna FK verso utenti_registrati)
            cursor.execute(
                "DELETE FROM utenti_notifiche WHERE LOWER(TRIM(email)) = %s",
                (email_norm,),
            )
            conteggio["utenti_notifiche"] = cursor.rowcount
 
            # 7. utenti_registrati — CASCADE elimina automaticamente:
            #    - notifiche_scadenze (FK ON DELETE CASCADE)
            #    - password_reset_tokens (FK ON DELETE CASCADE)
            cursor.execute(
                "DELETE FROM utenti_registrati WHERE LOWER(TRIM(email)) = %s",
                (email_norm,),
            )
            conteggio["utenti_registrati"] = cursor.rowcount
 
    # Invalida tutte le cache per questo utente
    _cache_movimenti.invalidate(email_norm)
    _cache_spese.invalidate(email_norm)
    _cache_finanziamenti.invalidate(email_norm)
    _cache_pac.invalidate(email_norm)
 
    logger.info(
        "Account eliminato: %s — righe rimosse: %s",
        email_norm,
        ", ".join(f"{t}={n}" for t, n in conteggio.items()),
    )
    return conteggio

# ---------------------------------------------------------------------------
# Import CSV
# ---------------------------------------------------------------------------

def importa_csv_storici(lista_file_csv, user_email: str = "admin") -> int:
    totale = 0
    with connetti_db() as conn:
        with conn.cursor() as cursor:
            for file in lista_file_csv:
                file_name = getattr(file, "name", str(file))
                try:
                    df = pd.read_csv(file, sep=None, engine="python", encoding="utf-8")
                    df.columns = df.columns.str.strip()
                    mappa = {
                        "DATA": "data", "TIPO": "tipo", "CATEGORIA": "categoria",
                        "DETTAGLIO SPESA": "dettaglio", "IMPORTO": "importo",
                    }
                    df = df.rename(columns=mappa)
                    if "tipo" in df.columns:
                        df["tipo"] = (df["tipo"].astype(str).str.upper().str.strip()
                                      .replace({"ENTRATE": "ENTRATA", "USCITE": "USCITA"}))
                    if "categoria" in df.columns:
                        df["categoria"] = df["categoria"].astype(str).str.upper().str.strip()
                    if df["importo"].dtype == object:
                        df["importo"] = (df["importo"].str.replace("€", "", regex=False)
                                         .str.replace(".", "", regex=False)
                                         .str.replace(",", ".", regex=False)
                                         .str.strip().astype(float))
                    df["data"] = pd.to_datetime(df["data"], dayfirst=True).dt.strftime("%Y-%m-%d %H:%M:%S")
                    for _, row in df.iterrows():
                        cursor.execute(
                            "INSERT INTO movimenti "
                            "(data, tipo, categoria, dettaglio, importo, note, user_email) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                            (row["data"], row["tipo"], row["categoria"],
                             row.get("dettaglio", ""), row["importo"], "", user_email),
                        )
                    conn.commit()
                    totale += len(df)
                    logger.info("Importato: %s (%d righe)", file_name, len(df))
                except Exception as exc:
                    conn.rollback()
                    logger.error("Errore nel file %s: %s", file_name, exc)
    _cache_movimenti.invalidate(user_email)
    _cache_pac.invalidate(user_email)
    return totale