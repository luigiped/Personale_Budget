
FROM python:3.13-slim

# Imposta la cartella di lavoro nel container
WORKDIR /app

# Copia il file dei requisiti e installa le librerie
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia tutto il resto del codice (rispettando il .gitignore)
COPY . .

# Cloud Run assegna automaticamente una porta, Streamlit deve usare quella
ENV PORT=8080
EXPOSE 8080

# Comando per avviare la tua app Streamlit
CMD ["streamlit", "run", "interfaccia.py", "--server.port=8080", "--server.address=0.0.0.0"]