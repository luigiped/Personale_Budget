#!/bin/bash
set -e

if [ "$APP_MODE" = "job" ]; then
  echo "Avvio in modalità JOB SERVICE (gunicorn)"
  exec gunicorn --bind 0.0.0.0:8080 --workers 1 --timeout 300 job_service:app
else
  echo "Avvio in modalità STREAMLIT APP"
  exec streamlit run interfaccia.py \
    --server.port=8080 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false
fi