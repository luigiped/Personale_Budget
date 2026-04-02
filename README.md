# 💰 Personal Budget Dashboard

Una web app per la gestione delle finanze personali, costruita con **Python** e **Streamlit**. Permette di tracciare entrate e uscite, pianificare il budget secondo la regola **50/30/20**, monitorare finanziamenti, investimenti (PAC e fondo pensione) e ricevere notifiche email automatiche sulle scadenze.

---

## 📸 Funzionalità principali

- **Dashboard KPI** – saldo disponibile, uscite mensili, risparmio e tasso di risparmio
- **Registro movimenti** – inserimento e visualizzazione di entrate/uscite per categoria e dettaglio
- **Budget 50/30/20** – suddivisione automatica del budget in Necessità, Svago e Investimenti
- **Spese ricorrenti** – calendario scadenze con stato pagato/da pagare/in scadenza
- **Finanziamenti** – calcolo rata (ammortamento francese), debito residuo, interessi e avanzamento
- **Analisi investimenti** – monitoraggio PAC (con prezzo live via Yahoo Finance) e Fondo Pensione con proiezioni future e beneficio fiscale IRPEF
- **Previsione saldo** – regressione lineare sui dati storici per stimare il saldo dei mesi futuri
- **Composizione portafoglio** – ripartizione percentuale tra liquidità, PAC e fondo pensione
- **Notifiche email automatiche** – riepilogo settimanale e promemoria scadenze il giorno prima
- **Backup dati** – download on-demand in formato SQL dall'app; invio automatico via email notturno in produzione
- **Autenticazione** – login con email/password e Google OAuth 2.0, con modalità demo e modalità chiusa

---

## 🗂️ Struttura del progetto

```
├── interfaccia.py          # Entry point Streamlit – UI e routing pagine
├── logiche.py              # Business logic: calcoli budget, finanziamenti, investimenti
├── Database.py             # Layer dati: connessione PostgreSQL, CRUD, migrazioni
├── auth_manager.py         # Autenticazione: sessioni, login email, Google OAuth
├── config_runtime.py       # Configurazione: env var, Streamlit secrets, Secret Manager
├── gmail_sender.py         # Invio email tramite Gmail API (OAuth2) con supporto allegati
├── notification_worker.py  # Worker notifiche: riepilogo settimanale e reminder scadenze
├── backup_db.py            # Worker backup: genera SQL per utente e invia via email
└── requirements.txt        # Dipendenze Python
```

---

## 🛠️ Stack tecnologico

| Layer | Tecnologia |
|---|---|
| Frontend | [Streamlit](https://streamlit.io/) |
| Database | PostgreSQL ([Supabase](https://supabase.com/)) via `psycopg2` |
| Autenticazione | Email/password + Google OAuth 2.0 (`streamlit-oauth`) |
| Email | Gmail API (OAuth2, `google-auth`) |
| Dati mercato | Yahoo Finance (`yfinance`) |
| Calcoli finanziari | `numpy-financial`, `numpy`, `pandas` |
| Grafici | Plotly |
| Deploy | Streamlit Cloud o Google Cloud Run |

---

## ⚙️ Requisiti

- Python **3.10+**
- Un progetto **Google Cloud** con Gmail API abilitata (per le notifiche email)
- Un database **PostgreSQL** (es. Supabase free tier)

Installa le dipendenze:

```bash
pip install -r requirements.txt
```

Dipendenze principali:

```
streamlit>=1.30
pandas
numpy
numpy-financial
plotly
psycopg2-binary
python-dateutil
yfinance
google-auth
google-auth-oauthlib
google-api-python-client
streamlit-oauth
extra-streamlit-components


---

## 🔑 Configurazione

L'app legge la configurazione da tre fonti, in ordine di priorità:

1. **Variabili d'ambiente** (funziona ovunque)
2. **Google Secret Manager** (solo su Cloud Run)
3. **Streamlit Secrets** – file `.streamlit/secrets.toml` in locale, o la sezione *Secrets* su Streamlit Cloud

### Variabili richieste

| Chiave | Descrizione |
|---|---|
| `SUPABASE_URL` | URL del progetto Supabase |
| `SUPABASE_KEY` | Chiave anon/service di Supabase |
| `DATABASE_URL` | Stringa di connessione PostgreSQL |
| `DATABASE_URL_POOLER` | Stringa alternativa (pooler) |
| `GOOGLE_CLIENT_ID` | Client ID Google OAuth |
| `GOOGLE_CLIENT_SECRET` | Client Secret Google OAuth |
| `GMAIL_TOKEN_SISTEMA` | Token OAuth2 Gmail (JSON serializzato) |
| `APP_BASE_URL` | URL pubblico dell'app (per il redirect OAuth) |
| `AUTH_ACCESS_MODE` | `normal` / `demo_only` / `closed` — controlla accessi E attiva/disattiva email automatiche |

### Esempio `.streamlit/secrets.toml`

```toml
DATABASE_URL = "postgresql://user:password@host:5432/dbname"
GOOGLE_CLIENT_ID = "xxxx.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "GOCSPX-..."
GMAIL_TOKEN_SISTEMA = '{"token": "...", "refresh_token": "...", ...}'
AUTH_ACCESS_MODE = "normal"  # normal | demo_only | closed
```

---

## 🚀 Avvio in locale

```bash
streamlit run interfaccia.py
```

L'app sarà disponibile su `http://localhost:8501`.

---

## 📧 Notifiche email (notification worker)

Il worker `notification_worker.py` invia automaticamente:

- **Ogni lunedì** – riepilogo delle scadenze della settimana
- **Ogni giorno** – promemoria per i pagamenti in scadenza il giorno successivo

Le notifiche sono **disattivate automaticamente** quando `AUTH_ACCESS_MODE` è `demo_only` o `closed`. Si attivano impostando `AUTH_ACCESS_MODE = normal`.

Può essere eseguito manualmente o schedulato (es. cron job, Cloud Scheduler):

```bash
# Esecuzione normale
python notification_worker.py

# Dry-run (non invia email, mostra solo l'output)
python notification_worker.py --dry-run

# Con data specifica e timezone
python notification_worker.py --today 2025-06-01 --timezone Europe/Rome
```

Il worker evita duplicati tramite un registro interno delle notifiche già inviate.

---

## 💾 Backup dati (backup worker)

Il worker `backup_db.py` genera un dump SQL dei dati di ogni utente e lo invia come allegato email direttamente all'utente.

**Caratteristiche:**
- Multi-tenant — ogni utente riceve solo i propri dati
- Off-site — il backup è nella casella email dell'utente, indipendente da Supabase
- Disattivato automaticamente quando `AUTH_ACCESS_MODE` è `demo_only` o `closed`

**Download on-demand:** nel tab Registro dell'app è disponibile il pulsante "Scarica backup dati" che genera il file SQL al volo e lo scarica nel browser — funziona sempre, anche in modalità demo.

**Tabelle incluse nel backup:**
- `movimenti`, `asset_settings`, `finanziamenti`, `spese_ricorrenti`

**Schedulazione su Cloud Run:**
```bash
gcloud scheduler jobs create http backup-budget-notturno \
  --location europe-west1 \
  --schedule "0 2 * * *" \
  --uri "https://europe-west1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/YOUR_PROJECT/jobs/backup-budget:run" \
  --message-body "{}" \
  --oauth-service-account-email YOUR_PROJECT@appspot.gserviceaccount.com \
  --time-zone "Europe/Rome"
```

---

## 🗄️ Database

L'applicazione usa PostgreSQL con le seguenti tabelle principali:

| Tabella | Contenuto |
|---|---|
| `movimenti` | Registro entrate e uscite |
| `spese_ricorrenti` | Spese periodiche (affitto, abbonamenti, ecc.) |
| `finanziamenti` | Prestiti e mutui |
| `asset_settings` | Impostazioni personali (PAC, fondo pensione, saldi) |
| `utenti_registrati` | Account utenti (email + password hash) |
| `utenti_notifiche` | Utenti iscritti alle notifiche email automatiche |
| `notifiche_scadenze` | Storico notifiche inviate (anti-duplicato) |
| `active_sessions` | Sessioni attive (token + scadenza) |

Le migrazioni vengono applicate automaticamente all'avvio tramite `db.inizializza_db()`.

---

## 🔐 Autenticazione

Sono supportate tre modalità, configurabili tramite `AUTH_ACCESS_MODE`:

- `normal` – registrazione e login aperti a tutti; notifiche email e backup automatici attivi
- `demo_only` – accesso esclusivo all'account demo; notifiche email e backup automatici disattivati
- `closed` – accessi disabilitati (modalità manutenzione); notifiche email e backup automatici disattivati

Il login è possibile con email/password oppure tramite **Google OAuth 2.0**. Le sessioni sono gestite tramite cookie sicuri (`pb_session_token`).

> **Nota:** `AUTH_ACCESS_MODE` è l'unico switch da cambiare per passare dalla modalità demo alla produzione completa.

---

## ☁️ Deploy

### Streamlit Cloud

1. Fai il fork/push del repo su GitHub
2. Collega il repo su [share.streamlit.io](https://share.streamlit.io)
3. Imposta le variabili nella sezione **Secrets** dell'app
4. Imposta `Main file path` su `interfaccia.py`

### Google Cloud Run

L'app è compatibile con Cloud Run. La variabile `K_SERVICE` viene rilevata automaticamente per attivare la modalità Cloud Run (Secret Manager, URL dinamico).

Esempio `Dockerfile` minimale:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
EXPOSE 8080
CMD ["streamlit", "run", "interfaccia.py", "--server.port=8080", "--server.address=0.0.0.0"]
```

---

## 📁 Moduli – descrizione rapida

### `logiche.py`
Contiene tutta la business logic dell'app:
- `calcola_kpi_dashboard` – calcola i KPI mensili principali
- `calcolo_spese_ricorrenti` – genera il calendario scadenze con rilevamento pagamenti
- `calcolo_finanziamento` – ammortamento francese, debito residuo, interessi
- `analisi_pac` – valore attuale PAC con prezzo live e proiezione futura
- `analisi_fondo_pensione` – proiezione fondo pensione con beneficio fiscale IRPEF
- `previsione_saldo` – previsione saldo via regressione lineare
- `composizione_portafoglio` – ripartizione percentuale del patrimonio

### `Database.py`
Layer di accesso ai dati su PostgreSQL via `psycopg2`. Gestisce connessione, CRUD su tutte le tabelle, migrazioni automatiche e isolamento dei dati per utente tramite `user_email`.

### `auth_manager.py`
Gestisce il ciclo di vita delle sessioni utente, il login con email/password (hash bcrypt), il flusso Google OAuth 2.0 e la modalità demo.

### `config_runtime.py`
Risolve i segreti dell'applicazione in modo uniforme tra ambienti diversi (locale, Streamlit Cloud, Cloud Run). Espone `get_secret(name)` come interfaccia unica.

### `gmail_sender.py`
Invia email HTML tramite Gmail API con supporto emoji. Gestisce il refresh automatico del token OAuth2 e il formato `multipart/alternative` per compatibilità massima. Espone anche `send_email_with_attachment()` per l'invio di file allegati (usato dal backup worker).

### `notification_worker.py`
Worker standalone per l'invio di notifiche email personalizzate per utente. Carica i dati di ogni utente indipendentemente e verifica i duplicati prima di inviare. Disattivato automaticamente se `AUTH_ACCESS_MODE != normal`.

### `backup_db.py`
Worker standalone per il backup dati multi-tenant. Genera un dump SQL filtrato per `user_email` e lo invia come allegato email a ogni utente registrato. Disattivato automaticamente se `AUTH_ACCESS_MODE != normal`. Il download on-demand dall'interfaccia è sempre disponibile indipendentemente dalla modalità.

---

## 📄 Proprietà intellettuale e Licenza

© 2026 — Luigi Pedace. Tutti i diritti riservati.

Questo software è proprietà esclusiva dell'autore. L'uso, la copia e la distribuzione non autorizzata sono severamente proibiti. Per i dettagli completi, consultare il file [LICENSE](./LICENSE) presente in questo repository.
