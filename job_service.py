"""
service_gcloud.py
---------
service combinato per l'app — esegue in sequenza:
  1. Notifiche scadenze (notification_worker.py)
  2. Backup dati utenti via email (backup.py)

Entrambi i processi rispettano AUTH_ACCESS_MODE:
  - demo_only / closed → saltati silenziosamente
  - normal             → eseguiti normalmente

Variabili d'ambiente richieste:
  - DATABASE_URL (o DATABASE_URL_POOLER)
  - GMAIL_TOKEN_SISTEMA
  - AUTH_ACCESS_MODE

Equivalente HTTP di job_gcloud.py.
Cloud Scheduler chiama POST /run-job → esegue notifiche + backup.
"""

import logging
import os
from flask import Flask, jsonify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/run-job", methods=["POST"])
def run_job():
    errori = []

    # ── 1. Notifiche ──────────────────────────────────────────────────
    logger.info("=" * 50)
    logger.info("STEP 1 — Notifiche scadenze")
    logger.info("=" * 50)
    try:
        from notification_worker import run as run_notifiche
        risultato = run_notifiche()
        logger.info(
            "Notifiche completate: weekly=%d, day_before=%d",
            risultato.get("weekly", 0),
            risultato.get("day_before", 0),
        )
    except Exception as exc:
        logger.error("Errore nel worker notifiche: %s", exc)
        errori.append(f"Notifiche: {exc}")

    # ── 2. Backup ─────────────────────────────────────────────────────
    logger.info("=" * 50)
    logger.info("STEP 2 — Backup dati utenti")
    logger.info("=" * 50)
    try:
        from backup import run as run_backup
        successo = run_backup()
        if successo:
            logger.info("Backup completato con successo.")
        else:
            logger.warning("Backup completato con errori.")
            errori.append("Backup: completato con errori")
    except Exception as exc:
        logger.error("Errore nel worker backup: %s", exc)
        errori.append(f"Backup: {exc}")

    # ── Risultato finale ───────────────────────────────────────────────
    logger.info("=" * 50)
    if errori:
        logger.error("Job completato con %d errori: %s", len(errori), " | ".join(errori))
        return jsonify({"status": "error", "errors": errori}), 500

    logger.info("Job completato con successo.")
    return jsonify({"status": "ok"}), 200


@app.route("/healthz", methods=["GET"])
def health():
    """Health check richiesto da Cloud Run."""
    return jsonify({"status": "healthy"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)