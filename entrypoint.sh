#!/bin/sh
set -eu

PORT="${PORT:-8080}"
APP_MODE="${APP_MODE:-app}"

if [ "$APP_MODE" = "job" ]; then
  echo "Avvio in modalità JOB SERVICE (gunicorn)"
  exec gunicorn --bind "0.0.0.0:${PORT}" --workers 1 --timeout 300 job_service:app
else
  echo "Avvio in modalità STREAMLIT APP"
  exec streamlit run interfaccia.py \
    --server.port="${PORT}" \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=true \
    --server.enableXsrfProtection=true
fi
