import logging
import psycopg2
import pandas as pd
import streamlit as st
from datetime import date as dt_date
from datetime import datetime
from urllib.parse import urlsplit
import os
import re

logger = logging.getLogger(__name__)
class _DBConn:
    """Wrapper che aggiunge il supporto al context manager su una connessione psycopg2."""
    def __init__(self, raw_conn):
        self._conn = raw_conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            self._conn.close()
        return False

# --- GESTIONE CONNESSIONE ---
def _sanitize_db_url(db_url):
    if not db_url:
        return db_url
    return re.sub(r"@\[([A-Za-z0-9.\-]+)\]", r"@\1", str(db_url).strip())

def _extract_host(db_url):
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

def _candidate_db_urls():
    urls = []
    for key in ("DATABASE_URL", "DATABASE_URL_POOLER"):
        try:
            raw = st.secrets.get(key)
        except Exception:
            raw = None
        if raw:
            urls.append(_sanitize_db_url(raw))
    for key in ("DATABASE_URL", "DATABASE_URL_POOLER"):
        raw = os.getenv(key)
        if raw:
            urls.append(_sanitize_db_url(raw))
    out = []
    seen = set()
    for u in urls:
        if u and u not in seen:
            out.append(u)
            seen.add(u)
    return out

def connetti_db():
    candidates = _candidate_db_urls()
    if not candidates:
        raise RuntimeError("Nessuna stringa DB trovata.")
    errors = []
    for uri in candidates:
        host = _extract_host(uri)
        try:
            return _DBConn(psycopg2.connect(uri))
        except Exception as e:
            msg = str(e).strip().splitlines()[0]
            errors.append(f"{host}: {msg}")
    raise RuntimeError(f"Connessione DB fallita: {' | '.join(errors)}")

def _applica_migrazioni(cursor):
    # Aggiunta colonna user_email a tutte le tabelle
    cursor.execute("ALTER TABLE movimenti ADD COLUMN IF NOT EXISTS user_email TEXT DEFAULT 'admin'")
    cursor.execute("ALTER TABLE asset_settings ADD COLUMN IF NOT EXISTS user_email TEXT DEFAULT 'admin'")
    cursor.execute("ALTER TABLE finanziamenti ADD COLUMN IF NOT EXISTS user_email TEXT DEFAULT 'admin'")
    cursor.execute("ALTER TABLE spese_ricorrenti ADD COLUMN IF NOT EXISTS user_email TEXT DEFAULT 'admin'")
    
    # Rimuoviamo il DEFAULT dopo averlo applicato per le vecchie righe
    cursor.execute("ALTER TABLE movimenti ALTER COLUMN user_email DROP DEFAULT")
    cursor.execute("ALTER TABLE asset_settings ALTER COLUMN user_email DROP DEFAULT")
    cursor.execute("ALTER TABLE finanziamenti ALTER COLUMN user_email DROP DEFAULT")
    cursor.execute("ALTER TABLE spese_ricorrenti ALTER COLUMN user_email DROP DEFAULT")

    # Aggiornamento PK per asset_settings e finanziamenti (ora dipendono anche dall'utente)
    try:
        cursor.execute("ALTER TABLE asset_settings DROP CONSTRAINT IF EXISTS asset_settings_pkey CASCADE")
        cursor.execute("ALTER TABLE asset_settings ADD PRIMARY KEY (chiave, user_email)")
        
        cursor.execute("ALTER TABLE finanziamenti DROP CONSTRAINT IF EXISTS finanziamenti_pkey CASCADE")
        cursor.execute("ALTER TABLE finanziamenti ADD PRIMARY KEY (nome, user_email)")
    except Exception as e:
        logger.warning("Migrazione PK ignorata (già applicata o dati sporchi): %s", e)

    cursor.execute("ALTER TABLE movimenti ADD COLUMN IF NOT EXISTS data TIMESTAMP")
    cursor.execute("ALTER TABLE movimenti ADD COLUMN IF NOT EXISTS tipo TEXT")
    cursor.execute("ALTER TABLE movimenti ADD COLUMN IF NOT EXISTS categoria TEXT")
    cursor.execute("ALTER TABLE movimenti ADD COLUMN IF NOT EXISTS dettaglio TEXT")
    cursor.execute("ALTER TABLE movimenti ADD COLUMN IF NOT EXISTS importo DOUBLE PRECISION")
    cursor.execute("ALTER TABLE movimenti ADD COLUMN IF NOT EXISTS note TEXT")
    cursor.execute("ALTER TABLE asset_settings ADD COLUMN IF NOT EXISTS valore_numerico DOUBLE PRECISION")
    cursor.execute("ALTER TABLE asset_settings ADD COLUMN IF NOT EXISTS valore_testo TEXT")
    cursor.execute("ALTER TABLE finanziamenti ADD COLUMN IF NOT EXISTS capitale_iniziale DOUBLE PRECISION")
    cursor.execute("ALTER TABLE finanziamenti ADD COLUMN IF NOT EXISTS taeg DOUBLE PRECISION")
    cursor.execute("ALTER TABLE finanziamenti ADD COLUMN IF NOT EXISTS durata_mesi INTEGER")
    cursor.execute("ALTER TABLE finanziamenti ADD COLUMN IF NOT EXISTS data_inizio DATE")
    cursor.execute("ALTER TABLE finanziamenti ADD COLUMN IF NOT EXISTS giorno_scadenza INTEGER")
    cursor.execute("ALTER TABLE finanziamenti ADD COLUMN IF NOT EXISTS rate_pagate INTEGER")
    cursor.execute("ALTER TABLE spese_ricorrenti ADD COLUMN IF NOT EXISTS descrizione TEXT")
    cursor.execute("ALTER TABLE spese_ricorrenti ADD COLUMN IF NOT EXISTS importo DOUBLE PRECISION")
    cursor.execute("ALTER TABLE spese_ricorrenti ADD COLUMN IF NOT EXISTS giorno_scadenza INTEGER")
    cursor.execute("ALTER TABLE spese_ricorrenti ADD COLUMN IF NOT EXISTS frequenza_mesi INTEGER")
    cursor.execute("ALTER TABLE spese_ricorrenti ADD COLUMN IF NOT EXISTS data_inizio DATE")
    cursor.execute("ALTER TABLE spese_ricorrenti ADD COLUMN IF NOT EXISTS data_fine DATE")
    cursor.execute("ALTER TABLE notifiche_scadenze ADD COLUMN IF NOT EXISTS chiave_evento TEXT")
    cursor.execute("ALTER TABLE notifiche_scadenze ADD COLUMN IF NOT EXISTS destinatario TEXT")
    cursor.execute("ALTER TABLE notifiche_scadenze ADD COLUMN IF NOT EXISTS data_scadenza DATE")
    cursor.execute("ALTER TABLE notifiche_scadenze ADD COLUMN IF NOT EXISTS inviato_il TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    cursor.execute("ALTER TABLE utenti_notifiche ADD COLUMN IF NOT EXISTS email TEXT")
    cursor.execute("ALTER TABLE utenti_notifiche ADD COLUMN IF NOT EXISTS attivo BOOLEAN DEFAULT TRUE")
    cursor.execute("ALTER TABLE utenti_notifiche ADD COLUMN IF NOT EXISTS ultimo_login TIMESTAMP")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_utenti_notifiche_email ON utenti_notifiche (email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_movimenti_data_id ON movimenti (data DESC, id DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_movimenti_user_email_data_id ON movimenti (user_email, data DESC, id DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_movimenti_user_email_categoria_upper ON movimenti (user_email, UPPER(categoria))")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_finanziamenti_user_email ON finanziamenti (user_email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_spese_ricorrenti_user_email_descrizione ON spese_ricorrenti (user_email, descrizione)")

def inizializza_db():
    with connetti_db() as conn:
        cursor = conn.cursor()

        cursor.execute('''CREATE TABLE IF NOT EXISTS movimenti (
            id SERIAL PRIMARY KEY, data TIMESTAMP, tipo TEXT, categoria TEXT, 
            dettaglio TEXT, importo DOUBLE PRECISION, note TEXT, user_email TEXT)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS asset_settings (
            chiave TEXT, user_email TEXT, valore_numerico DOUBLE PRECISION, 
            valore_testo TEXT, PRIMARY KEY (chiave, user_email))''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS finanziamenti (
            nome TEXT, user_email TEXT, capitale_iniziale DOUBLE PRECISION, 
            taeg DOUBLE PRECISION, durata_mesi INTEGER, data_inizio DATE, 
            giorno_scadenza INTEGER, rate_pagate INTEGER, PRIMARY KEY (nome, user_email))''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS spese_ricorrenti (
            id SERIAL PRIMARY KEY, descrizione TEXT, importo DOUBLE PRECISION, 
            giorno_scadenza INTEGER, frequenza_mesi INTEGER, data_inizio DATE, 
            data_fine DATE, user_email TEXT)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS notifiche_scadenze (
            id SERIAL PRIMARY KEY, chiave_evento TEXT UNIQUE, destinatario TEXT, 
            data_scadenza DATE, inviato_il TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS utenti_notifiche (
            email TEXT PRIMARY KEY, attivo BOOLEAN DEFAULT TRUE, 
            ultimo_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        _applica_migrazioni(cursor)
        cursor.close()

def pulisci_sessioni_scadute():
    """Elimina sessioni scadute e notifiche vecchie (> 90 giorni)."""
    try:
        with connetti_db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM active_sessions WHERE expires_at < NOW()")
            sessioni = cursor.rowcount
            cursor.execute(
                "DELETE FROM notifiche_scadenze "
                "WHERE inviato_il < NOW() - INTERVAL '90 days'"
            )
            notifiche = cursor.rowcount
            cursor.close()
        if sessioni > 0 or notifiche > 0:
            logger.info(
                "Pulizia DB: %d sessioni scadute, %d notifiche vecchie rimosse.",
                sessioni, notifiche
            )
    except Exception as exc:
        logger.warning("pulisci_sessioni_scadute: %s", exc)

# --- FUNZIONI DI SCRITTURA ---

def aggiungi_movimento(data, tipo, categoria, dettaglio, importo, note, user_email):
    now = datetime.now().replace(microsecond=0)
    try:
        if isinstance(data, datetime): dt_value = data
        elif isinstance(data, dt_date): dt_value = datetime.combine(data, now.time())
        else:
            parsed = pd.to_datetime(data, errors='coerce')
            dt_value = parsed.to_pydatetime() if not pd.isna(parsed) else now
        if isinstance(data, str) and ":" not in data:
            dt_value = dt_value.replace(hour=now.hour, minute=now.minute, second=now.second)
        data_db = dt_value.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        data_db = now.strftime('%Y-%m-%d %H:%M:%S')

    with connetti_db() as conn:
        cursor = conn.cursor()
        tipo_norm = str(tipo).upper().strip().replace("ENTRATE", "ENTRATA").replace("USCITE", "USCITA")
        cat_norm = str(categoria).upper().strip()
        query = """INSERT INTO movimenti (data, tipo, categoria, dettaglio, importo, note, user_email) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s)"""
        cursor.execute(query, (data_db, tipo_norm, cat_norm, dettaglio, importo, note, user_email))
        cursor.close()
    carica_dati.clear()
    

def imposta_parametro(chiave, valore_num=None, valore_txt=None, user_email="admin"):
    user_email_norm = str(user_email).strip().lower() if user_email else "admin"
    chiave_norm = str(chiave).strip()
    if not chiave_norm:
        raise ValueError("Chiave parametro non valida.")
    with connetti_db() as conn:
        cursor = conn.cursor()
        query = """
            INSERT INTO asset_settings (chiave, valore_numerico, valore_testo, user_email) 
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (chiave, user_email) DO UPDATE SET 
                valore_numerico = EXCLUDED.valore_numerico, 
                valore_testo = EXCLUDED.valore_testo
        """
        cursor.execute(query, (chiave_norm, valore_num, valore_txt, user_email_norm))
        cursor.close()

def aggiungi_finanziamento(nome, capitale, taeg, durata, data_inizio, scadenza, rate_pagate, user_email):
     with connetti_db() as conn:
        cursor = conn.cursor()
        query = """
            INSERT INTO finanziamenti (nome, capitale_iniziale, taeg, durata_mesi, data_inizio, giorno_scadenza, rate_pagate, user_email) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (nome, user_email) DO UPDATE SET 
                capitale_iniziale = EXCLUDED.capitale_iniziale, taeg = EXCLUDED.taeg,
                durata_mesi = EXCLUDED.durata_mesi, data_inizio = EXCLUDED.data_inizio,
                giorno_scadenza = EXCLUDED.giorno_scadenza, rate_pagate = EXCLUDED.rate_pagate
        """
        cursor.execute(query, (nome, capitale, taeg, durata, data_inizio, scadenza, rate_pagate, user_email))
        cursor.close()
        carica_finanziamenti.clear()

def aggiungi_spesa_ricorrente(descrizione, importo, giorno_scadenza, frequenza_mesi, data_inizio, data_fine, user_email):
    with connetti_db() as conn:
        cursor = conn.cursor()
        query = """
            INSERT INTO spese_ricorrenti (descrizione, importo, giorno_scadenza, frequenza_mesi, data_inizio, data_fine, user_email) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (descrizione, importo, giorno_scadenza, frequenza_mesi, data_inizio, data_fine, user_email))
        cursor.close()
    carica_spese_ricorrenti.clear()

# --- FUNZIONI DI ELIMINAZIONE ---

def elimina_movimento(mov_id, user_email):
    with connetti_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM movimenti WHERE id = %s AND user_email = %s", (mov_id, user_email))
        cursor.close()
    carica_dati.clear()

def elimina_finanziamento(nome, user_email):
    with connetti_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM finanziamenti WHERE nome = %s AND user_email = %s", (nome, user_email))
        cursor.close()
    carica_finanziamenti.clear()

def elimina_spesa_ricorrente(spesa_id, user_email):
    with connetti_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM spese_ricorrenti WHERE id = %s AND user_email = %s", (spesa_id, user_email))
        cursor.close()
    carica_spese_ricorrenti.clear()

# --- FUNZIONI DI LETTURA ---

@st.cache_data(ttl=60, show_spinner=False)
def carica_dati(user_email):
    with connetti_db() as conn:
        query = "SELECT * FROM movimenti WHERE user_email = %s ORDER BY data DESC, id DESC"
        df = pd.read_sql_query(query, conn, params=(user_email,))
    return df

@st.cache_data(ttl=60, show_spinner=False)
def carica_spese_ricorrenti(user_email):
    with connetti_db() as conn:
        try:
            query = "SELECT * FROM spese_ricorrenti WHERE user_email = %s ORDER BY descrizione ASC"
            df = pd.read_sql_query(query, conn, params=(user_email,))
        except Exception:
            df = pd.DataFrame()
    return df

@st.cache_data(ttl=60, show_spinner=False)
def carica_finanziamenti(user_email):
    with connetti_db() as conn:
        query = "SELECT * FROM finanziamenti WHERE user_email = %s"
        df = pd.read_sql_query(query, conn, params=(user_email,))
    return df

@st.cache_data(ttl=60)
def recupera_investimento_pac_db(user_email):
    with connetti_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT SUM(importo) FROM movimenti 
            WHERE (categoria = 'PAC' OR dettaglio = 'PAC' OR tipo = 'PAC') AND user_email = %s
        """
        cursor.execute(query, (user_email,))
        risultato = cursor.fetchone()[0]
        cursor.close()
    return risultato if risultato else 0.0

def recupera_totale_per_categoria(categoria, user_email):
    with connetti_db() as conn:
        cursor = conn.cursor()
        query = "SELECT SUM(importo) FROM movimenti WHERE UPPER(categoria) = %s AND user_email = %s"
        cursor.execute(query, (categoria.upper(), user_email))
        risultato = cursor.fetchone()[0]
        cursor.close()
    return risultato if risultato else 0.0

# --- ALTRE UTILITIES ---

def registra_notifica_scadenza(chiave_evento, destinatario, data_scadenza=None):
    with connetti_db() as conn:
        cursor = conn.cursor()
        query = """
            INSERT INTO notifiche_scadenze (chiave_evento, destinatario, data_scadenza) 
            VALUES (%s, %s, %s) ON CONFLICT (chiave_evento) DO NOTHING
        """
        cursor.execute(query, (chiave_evento, destinatario, data_scadenza))
        conn.commit()
        cursor.close()

def registra_utente_notifiche(email, attivo=True):
    if not email: return
    email_norm = str(email).strip().lower()
    if not email_norm: return
    with connetti_db() as conn:
        cursor = conn.cursor()
        query = """
            INSERT INTO utenti_notifiche (email, attivo, ultimo_login)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (email) DO UPDATE SET attivo = EXCLUDED.attivo, ultimo_login = CURRENT_TIMESTAMP
        """
        cursor.execute(query, (email_norm, bool(attivo)))
        cursor.close()

def notifica_scadenza_gia_inviata(chiave_evento):
    with connetti_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM notifiche_scadenze WHERE chiave_evento = %s LIMIT 1", (chiave_evento,))
        row = cursor.fetchone()
        cursor.close()
    return row is not None

def lista_destinatari_notifiche():
    with connetti_db() as conn:
        cursor = conn.cursor()
        destinatari = set()
        try:
            cursor.execute("SELECT DISTINCT LOWER(TRIM(email)) AS email FROM utenti_notifiche WHERE attivo = TRUE AND email IS NOT NULL")
            for (email,) in cursor.fetchall():
                if email: destinatari.add(str(email).strip().lower())
        except Exception: pass
        cursor.close()
    return sorted(destinatari)

def verifica_password(password_inserita):
    try:
        password_reale = st.secrets.get("PASSWORD_APP")
    except Exception:
        password_reale = None
    if not password_reale:
        return False
    return password_inserita == password_reale

# --- IMPORTAZIONE CSV ---

def importa_csv_storici(lista_file_csv, user_email="admin"):
    totale = 0
    with connetti_db() as conn:
        cursor = conn.cursor()
        for file in lista_file_csv:
            file_name = getattr(file, "name", str(file))
            try:
                df = pd.read_csv(file, sep=None, engine='python', encoding='utf-8')
                df.columns = df.columns.str.strip()
                mappa = {'DATA':'data', 'TIPO':'tipo', 'CATEGORIA':'categoria', 'DETTAGLIO SPESA':'dettaglio', 'IMPORTO':'importo'}
                df = df.rename(columns=mappa)
                if 'tipo' in df.columns: df['tipo'] = df['tipo'].astype(str).str.upper().str.strip().replace({'ENTRATE': 'ENTRATA', 'USCITE': 'USCITA'})
                if 'categoria' in df.columns: df['categoria'] = df['categoria'].astype(str).str.upper().str.strip()
                if df['importo'].dtype == 'O': df['importo'] = df['importo'].str.replace('€', '').str.replace('.', '').str.replace(',', '.').str.strip().astype(float)
                df['data'] = pd.to_datetime(df['data'], dayfirst=True).dt.strftime('%Y-%m-%d %H:%M:%S')
                for _, row in df.iterrows():
                    cursor.execute(
                        "INSERT INTO movimenti (data, tipo, categoria, dettaglio, importo, note, user_email) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (row['data'], row['tipo'], row['categoria'], row.get('dettaglio', ''), row['importo'], "", user_email)
                    )
                conn.commit()
                totale += len(df)
                logger.info("Importato: %s (%d righe)", file_name, len(df))
            except Exception as e:
                conn.rollback()
                logger.error("Errore nel file %s: %s", file_name, e)
        cursor.close()
    return totale
