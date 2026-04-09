
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    APP_MODE=app

# Imposta la cartella di lavoro nel container
WORKDIR /app

# Copia il file dei requisiti e installa le librerie
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia tutto il resto del codice (rispettando .dockerignore)
COPY . .
RUN chmod +x /app/entrypoint.sh

# Cloud Run espone la porta del container tramite la env var PORT
EXPOSE 8080

# Entry point unico: app Streamlit o job_service in base a APP_MODE
ENTRYPOINT ["/app/entrypoint.sh"]
