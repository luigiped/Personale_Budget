# ─────────────────────────────────────────────────────────────────────────────
# Personal Budget Dashboard — Dockerfile
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

WORKDIR /app

# ── Dipendenze di sistema ────────────────────────────────────────────────────
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Dipendenze Python ────────────────────────────────────────────────────────
# Copiamo prima solo requirements.txt per sfruttare la cache Docker:
# se il codice sorgente cambia ma le dipendenze no, questo layer resta cached.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Codice sorgente ──────────────────────────────────────────────────────────
COPY . .

# ── Porta ────────────────────────────────────────────────────────────────────
# Cloud Run inietta PORT=8080 automaticamente.
# In locale (o Streamlit Cloud) la variabile non è impostata → default 8501.
EXPOSE 8080

# ── Avvio ────────────────────────────────────────────────────────────────────
# Usiamo sh -c per espandere $PORT a runtime (le istruzioni EXPOSE/ENV non
CMD ["sh", "-c", "streamlit run interfaccia.py --server.port=${PORT:-8080} --server.address=0.0.0.0 --server.headless=true"]