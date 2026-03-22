"""
backup_db.py
------------
Genera un file SQL per ogni utente registrato e lo invia come allegato
via email all'utente stesso.

Variabili d'ambiente richieste:
  - DATABASE_URL (o DATABASE_URL_POOLER)
  - GMAIL_TOKEN_SISTEMA (già presente — nessun token aggiuntivo)

Logica:
  - Ogni utente riceve solo i propri dati (filtro per user_email)
  - Il backup è off-site (nella casella email dell'utente)
  - Accessibile anche se l'infrastruttura Supabase è irraggiungibile
"""

import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

TIMEZONE = "Europe/Rome"
EMAIL_ERRORI = "digitalsheets.lp@gmail.com"

# Tabelle filtrate per user_email
TABELLE_PER_UTENTE = [
    "movimenti",
    "asset_settings",
    "finanziamenti",
    "spese_ricorrenti",
]


def _get_db_url():
    for key in ("DATABASE_URL", "DATABASE_URL_POOLER"):
        val = os.getenv(key)
        if val:
            return val
    raise RuntimeError("Nessuna variabile DATABASE_URL trovata nelle variabili d'ambiente.")


def _esporta_tabella_utente(cursor, tabella, user_email):
    """Esporta i dati di un utente da una tabella come INSERT INTO."""
    lines = [f"\n-- Tabella: {tabella}"]
    try:
        cursor.execute(
            f"SELECT * FROM {tabella} WHERE user_email = %s",
            (user_email,)
        )
        righe = cursor.fetchall()
        colonne = [desc[0] for desc in cursor.description]

        if not righe:
            lines.append(f"-- (nessun dato per {user_email})")
            return "\n".join(lines)

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
                    escaped = str(v).replace("'", "''")
                    valori.append(f"'{escaped}'")
            cols = ", ".join(colonne)
            vals = ", ".join(valori)
            lines.append(f"INSERT INTO {tabella} ({cols}) VALUES ({vals});")

    except Exception as exc:
        logger.warning("Errore esportazione %s per %s: %s", tabella, user_email, exc)
        lines.append(f"-- ERRORE esportazione {tabella}: {exc}")

    return "\n".join(lines)


def genera_sql_per_utente(cursor, user_email):
    """Genera il dump SQL completo per un singolo utente."""
    ora = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")
    blocchi = [
        f"-- Personal Budget — Backup dati",
        f"-- Utente  : {user_email}",
        f"-- Data    : {ora} (Europe/Rome)",
        f"-- ----------------------------------------",
        f"-- Per ripristinare: importa questo file in un database PostgreSQL",
        f"--   psql $DATABASE_URL < questo_file.sql",
        "SET client_encoding = 'UTF8';",
    ]
    for tabella in TABELLE_PER_UTENTE:
        blocchi.append(_esporta_tabella_utente(cursor, tabella, user_email))
    return "\n".join(blocchi)


def _lista_utenti(conn):
    """Recupera tutti gli utenti attivi dalla tabella utenti_notifiche."""
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT LOWER(TRIM(email)) FROM utenti_notifiche "
            "WHERE attivo = TRUE AND email IS NOT NULL"
        )
        utenti = [row[0] for row in cursor.fetchall() if row[0]]
        cursor.close()
        return utenti
    except Exception as exc:
        logger.error("Impossibile caricare lista utenti: %s", exc)
        return []


def _invia_email_errore(send_email_fn, titolo, dettaglio):
    """Notifica errori critici all'amministratore."""
    ora = datetime.now(ZoneInfo(TIMEZONE)).strftime("%d/%m/%Y %H:%M")
    try:
        send_email_fn(
            EMAIL_ERRORI,
            f"❌ Backup Personal Budget — {titolo}",
            f"<div style='font-family: sans-serif; color: #333;'>"
            f"<b>Data/ora:</b> {ora}<br>"
            f"<b>Errore:</b> {dettaglio}<br><br>"
            f"Controlla i log su Cloud Run per i dettagli completi.<br><br>"
            f"Il tuo assistente automatico 🤖"
            f"</div>"
        )
    except Exception as mail_exc:
        logger.error("Impossibile inviare email di errore: %s", mail_exc)


def run():
    logger.info("Avvio backup database multi-tenant...")
    from gmail_sender import send_email, send_email_with_attachment
    
    auth_mode = os.getenv("AUTH_ACCESS_MODE", "normal").strip().lower()
    if auth_mode != "normal":
        logger.info("AUTH_ACCESS_MODE=%s — invio email backup saltato.", auth_mode)
        return True

    # Connessione DB
    try:
        conn = psycopg2.connect(_get_db_url())
    except Exception as exc:
        logger.error("Connessione DB fallita: %s", exc)
        _invia_email_errore(send_email, "Connessione DB fallita", exc)
        return False

    utenti = _lista_utenti(conn)
    if not utenti:
        logger.warning("Nessun utente trovato — backup non eseguito.")
        conn.close()
        return True

    ora = datetime.now(ZoneInfo(TIMEZONE))
    data_str = ora.strftime("%Y-%m-%d")
    cursor = conn.cursor()
    successi = 0
    errori = 0

    for user_email in utenti:
        try:
            logger.info("Generazione backup per: %s", user_email)
            sql = genera_sql_per_utente(cursor, user_email)
            filename = f"personal_budget_backup_{data_str}.sql"

            body = (
                "<div style='font-family: sans-serif; color: #333;'>"
                f"Ciao,<br><br>"
                f"In allegato trovi il backup dei tuoi dati Personal Budget "
                f"del <b>{ora.strftime('%d/%m/%Y')}</b>.<br><br>"
                f"Il file contiene tutti i tuoi movimenti, impostazioni, "
                f"finanziamenti e spese ricorrenti in formato SQL.<br><br>"
                f"<b>Come ripristinare i dati:</b><br>"
                f"<code>psql $DATABASE_URL &lt; {filename}</code><br><br>"
                f"Conserva questo file in un posto sicuro — "
                f"è la tua unica copia indipendente dall'infrastruttura.<br><br>"
                f"Il tuo assistente automatico 🤖"
                f"</div>"
            )

            ok, msg = send_email_with_attachment(
                destinatario=user_email,
                subject=f"💾 Backup Personal Budget — {ora.strftime('%d/%m/%Y')}",
                body=body,
                filename=filename,
                content=sql,
                mimetype="text/plain",
            )

            if ok:
                logger.info("Backup inviato a %s (%d bytes).", user_email, len(sql))
                successi += 1
            else:
                logger.error("Invio fallito per %s: %s", user_email, msg)
                errori += 1

        except Exception as exc:
            logger.error("Errore backup per %s: %s", user_email, exc)
            errori += 1

    cursor.close()
    conn.close()

    logger.info(
        "Backup completato: %d successi, %d errori su %d utenti.",
        successi, errori, len(utenti)
    )

    if errori > 0:
        _invia_email_errore(
            send_email,
            f"Backup parziale ({errori}/{len(utenti)} errori)",
            f"{errori} utenti non hanno ricevuto il backup. "
            f"Controlla i log Cloud Run per i dettagli."
        )
        return False

    return True


if __name__ == "__main__":
    successo = run()
    exit(0 if successo else 1)