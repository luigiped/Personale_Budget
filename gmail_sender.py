import base64
import json
import logging
import os
import re

logger = logging.getLogger(__name__)
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_SEND_ENDPOINT = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def _load_token_payload():
    """
    Carica le credenziali OAuth Gmail dal primo source disponibile:
    1) env var GMAIL_TOKEN_SISTEMA (JSON string)
    2) st.secrets['GMAIL_TOKEN_SISTEMA'] (se eseguito in Streamlit)
    3) token/token_sistema.json
    4) token_sistema.json
    """
    raw = os.getenv("GMAIL_TOKEN_SISTEMA")
    if raw:
        return json.loads(raw), None

    try:
        import streamlit as st  # opzionale, solo se disponibile
        raw = st.secrets.get("GMAIL_TOKEN_SISTEMA")
        if raw:
            return json.loads(raw), None
    except Exception:
        pass

    candidate_paths = [
        Path("token/token_sistema.json"),
        Path("token_sistema.json"),
    ]
    for path in candidate_paths:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8")), path

    raise RuntimeError(
        "Token Gmail non trovato. Configura GMAIL_TOKEN_SISTEMA o crea token/token_sistema.json."
    )


def _build_credentials():
    token_payload, file_path = _load_token_payload()
    creds = Credentials.from_authorized_user_info(token_payload, scopes=[GMAIL_SEND_SCOPE])
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleAuthRequest())
        if file_path is not None:
            try:
                file_path.write_text(creds.to_json(), encoding="utf-8")
            except OSError as exc:
                # In Cloud Run il filesystem può non essere persistente; solo un warning.
                logger.warning("Impossibile aggiornare il token su disco (%s): %s", file_path, exc)
    return creds


def clean_html_to_text(html_str):
    """
    Converte l'HTML in testo semplice leggibile per il fallback.
    Questo è il trucco per far felice Cloud Run e Gmail.
    """
    text = str(html_str).replace("<br>", "\n").replace("<br/>", "\n")
    # Rimuove tutti i restanti tag HTML
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()


def send_email(destinatario, subject, body):
    """
    Invia una email via Gmail API o simula l'invio in modalità DEMO.
    """
    # CONTROLLO MODALITÀ DEMO
    if os.getenv("DEMO_MODE", "false").lower() == "true":
        print(f"--- SIMULAZIONE INVIO EMAIL ---")
        print(f"A: {destinatario}")
        print(f"Oggetto: {subject}")
        print(f"Corpo (estratto): {clean_html_to_text(body)[:50]}...")
        return True, "Email simulata con successo (Modalità Demo)."
    try:
        creds = _build_credentials()
    except Exception as exc:
        return False, f"Credenziali Gmail non valide: {exc}"
    
    # 1. Creiamo un contenitore Multipart (dichiariamo che ci sono più versioni)
    msg = MIMEMultipart("alternative")
    msg["To"] = str(destinatario or "").strip()
    msg["Subject"] = str(subject or "").strip()
    
    # 2. Creiamo la versione TESTO SEMPLICE (Piano B)
    body_text = clean_html_to_text(body)
    part_text = MIMEText(body_text, "plain", "utf-8")
    
    # 3. Creiamo la versione HTML (Piano A)
    part_html = MIMEText(body, "html", "utf-8")

    # 4. Alleghiamo le parti: ORDINE FONDAMENTALE (prima il plain, poi l'html)
    # Gmail legge l'ultima e usa quella se la supporta!
    msg.attach(part_text)
    msg.attach(part_html)

    # 5. Codifica sicura per le API di Gmail
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    
    payload = json.dumps({"raw": raw}).encode("utf-8")
    
    req = Request(
        GMAIL_SEND_ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    
    try:
        with urlopen(req, timeout=30) as resp:
            status = getattr(resp, "status", 200)
            if int(status) >= 300:
                return False, f"Gmail API HTTP {status}"
            return True, "Email inviata con successo."
    except HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            detail = str(exc)
        logger.error("Gmail API error %s: %s", exc.code, detail)
        return False, f"Gmail API error {exc.code}: {detail}"
    except URLError as exc:
        logger.error("Errore rete Gmail API: %s", exc)
        return False, f"Errore rete Gmail API: {exc}"
    except Exception as exc:
        logger.error("Invio email fallito: %s", exc)
        return False, f"Invio email fallito: {exc}"