FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080 \
    APP_MODE=app

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && rm -f requirements.txt

# Una sola immagine runtime: l'entrypoint sceglie tra app Streamlit e job HTTP
# in base a APP_MODE, senza duplicare servizi o trascinare file locali inutili.
COPY entrypoint.sh ./
COPY interfaccia.py ./
COPY job_service.py ./
COPY Database.py ./
COPY logiche.py ./
COPY auth_manager.py ./
COPY security.py ./
COPY config_runtime.py ./
COPY gmail_sender.py ./
COPY notification_worker.py ./
COPY backup.py ./
COPY ai_engine.py ./
COPY pages ./pages
COPY utils ./utils
COPY icon ./icon
COPY .streamlit ./.streamlit

RUN chmod 755 /app/entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]
