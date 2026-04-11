# 💰 Personal Budget Dashboard

> Web app per la gestione completa delle finanze personali — costruita con Python e Streamlit, deployata su Google Cloud Run.

![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Google Cloud Run](https://img.shields.io/badge/Cloud%20Run-4285F4?style=flat-square&logo=googlecloud&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)

---

## Panoramica

**Personal Budget Dashboard** è un'applicazione web self-hosted per il monitoraggio e la gestione delle finanze personali. Permette di tracciare entrate e uscite, gestire budget, monitorare finanziamenti e investimenti, ricevere notifiche automatiche e molto altro — il tutto con autenticazione sicura, supporto Google OAuth e funzionalità AI opzionali tramite Gemini.

---

## ✨ Funzionalità principali

### 📊 Dashboard e analisi
- KPI sintetici: saldo, spese, risparmio e indicatori principali
- Analisi storiche con grafici interattivi (Plotly)
- Previsione del saldo futura
- Report mensile AI opzionale (tramite Gemini)

### 💳 Gestione movimenti e budget
- Registro movimenti con entrate, uscite, categorie e note personalizzabili
- Budget percentuale articolato su tre macro-categorie
- Spese ricorrenti e calendario scadenze
- Gestione finanziamenti con piano di ammortamento, residuo e avanzamento rate
- Monitoraggio PAC e fondo pensione

### 🤖 Funzionalità AI *(opzionali, richiedono `GEMINI_API_KEY`)*
- **Financial Advisor Chatbot** — assistente conversazionale sui propri dati finanziari
- **Analisi predittiva e anomalie** — rilevamento automatico di pattern insoliti
- **Report mensile AI** — sintesi intelligente dell'andamento finanziario

### 🔐 Autenticazione e sicurezza
- Registrazione e login email/password
- Login con Google OAuth 2.0
- 2FA TOTP opzionale (compatibile con Google Authenticator, Microsoft Authenticator, Authy, ecc.)
- Onboarding guidato al primo accesso
- Reset password e eliminazione account

### 📬 Automazioni e job
- Notifiche email settimanali con riepilogo scadenze
- Backup dati automatico via email
- Orchestrazione job tramite endpoint HTTP (compatibile con Google Cloud Scheduler)
- Backup on-demand scaricabile dall'interfaccia

---

## 🏗️ Architettura

```
interfaccia.py          → UI Streamlit, login, onboarding, tab applicative
auth_manager.py         → autenticazione, sessioni, OAuth, 2FA
security.py             → hashing password, TOTP, cifratura dati sensibili
Database.py             → layer dati PostgreSQL, migrazioni, CRUD, rate limiting
logiche.py              → business logic finanziaria
config_runtime.py       → risoluzione configurazione
gmail_sender.py         → invio email via Gmail API
notification_worker.py  → job notifiche email
backup.py               → job backup dati
job_service.py          → wrapper HTTP per orchestrare job su Cloud Run
utils/                  → formatter, tabelle HTML, stili, costanti, settings utente
pages/                  → moduli secondari dell'interfaccia
```

---

## 🛠️ Stack tecnologico

| Layer | Tecnologia |
|---|---|
| UI | `Streamlit` |
| Database | `PostgreSQL` via `psycopg2` |
| Grafici | `Plotly` |
| Data processing | `pandas`, `numpy`, `numpy-financial` |
| Auth | email/password, Google OAuth 2.0, TOTP (`pyotp`) |
| AI | Google Gemini (`gemini-2.0-flash`) |
| Email | Gmail API |
| Deploy | Docker + Google Cloud Run |
| Secrets | env vars, `st.secrets`, Google Secret Manager |

---

## 🚀 Avvio in locale

### Prerequisiti
- Python 3.13+
- Database PostgreSQL raggiungibile dall'app
- *(Opzionale)* Credenziali Google OAuth per il login Google
- *(Opzionale)* Token Gmail OAuth per notifiche e backup email

### Installazione

```bash
# Clona il repository
git clone https://github.com/luigiped/Personal-Budget
cd personal-budget-dashboard

# Crea e attiva il virtualenv
python3 -m venv .venv
source .venv/bin/activate

# Installa le dipendenze
pip install -r requirements.txt

# Configura i segreti (vedi sezione Configurazione)
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# → modifica secrets.toml con i tuoi valori

# Avvia l'app
streamlit run interfaccia.py
```

L'app sarà disponibile su `http://localhost:8501`. Le migrazioni del database vengono applicate automaticamente all'avvio.

---

## ⚙️ Configurazione

La configurazione viene risolta nel seguente ordine di priorità:

1. **Variabili d'ambiente**
2. **Google Secret Manager** *(se l'app gira su Cloud Run)*
3. **`st.secrets` / `.streamlit/secrets.toml`**

### Variabili principali

| Chiave | Obbligatoria | Descrizione |
|---|---|---|
| `DATABASE_URL` o `DATABASE_URL_POOLER` | ✅ Sì | Stringa di connessione PostgreSQL |
| `AUTH_ACCESS_MODE` | ✅ Sì | `normal`, `demo_only`, `closed` |
| `APP_BASE_URL` | ⚠️ Consigliata | URL pubblico dell'app (necessario per Google OAuth) |
| `GOOGLE_CLIENT_ID` | Solo OAuth | Client ID Google |
| `GOOGLE_CLIENT_SECRET` o `GOOGLE_CLIENT_SECRET_JSON` | Solo OAuth | Client secret Google |
| `APP_DATA_ENCRYPTION_KEY` | ⚠️ Consigliata | Chiave Fernet per cifratura dati sensibili a riposo |
| `GMAIL_TOKEN_SISTEMA` | Solo email/job | Token Gmail serializzato JSON |
| `GEMINI_API_KEY` | Solo AI | Abilita le funzionalità AI |
| `DEMO_USER_EMAIL` | Solo `demo_only` | Email account demo |
| `DEMO_USER_PASSWORD` | Solo `demo_only` | Password account demo |
| `LOCAL_BASE_URL` | Opzionale | Override URL locale (default: `http://localhost:8501`) |
| `APP_ENV` | Opzionale | Ambiente applicativo |

### Esempio `secrets.toml`

```toml
DATABASE_URL         = "postgresql://user:password@host:5432/dbname"
AUTH_ACCESS_MODE     = "normal"
APP_BASE_URL         = "http://localhost:8501"

GOOGLE_CLIENT_ID     = "your-google-client-id"
GOOGLE_CLIENT_SECRET = "your-google-client-secret"

APP_DATA_ENCRYPTION_KEY = "your-fernet-key"

DEMO_USER_EMAIL    = "demo@example.com"
DEMO_USER_PASSWORD = "change-me"

GMAIL_TOKEN_SISTEMA = "{\"token\":\"...\",\"refresh_token\":\"...\"}"
GEMINI_API_KEY      = "your-gemini-api-key"
```

---

## 🔒 Modalità di accesso

La variabile `AUTH_ACCESS_MODE` governa il comportamento dell'app:

| Modalità | Comportamento |
|---|---|
| `normal` | Registrazione, login e Google OAuth abilitati; job email attivi |
| `demo_only` | Accesso esclusivo all'account demo; registrazione e login utenti disabilitati |
| `closed` | Accesso completamente disabilitato (es. per manutenzione) |

---

## 🔐 Sicurezza

L'app implementa le seguenti misure di hardening:

- Hashing password con `bcrypt` (con supporto retrocompatibile a hash legacy)
- Sessioni persistenti gestite lato app con token hashati nel database
- Rate limiting sui flussi sensibili di autenticazione
- Secret TOTP persistiti con supporto a cifratura applicativa (`APP_DATA_ENCRYPTION_KEY`)
- Verifica token Google e re-auth per i flussi sensibili sugli account OAuth
- Protezioni deploy aggiornate per Google Cloud Run

> ⚠️ Per abilitare la cifratura applicativa dei dati sensibili è necessario configurare `APP_DATA_ENCRYPTION_KEY`.

---

## 📬 Job e automazioni

### Notifiche email

```bash
python notification_worker.py
python notification_worker.py --dry-run
python notification_worker.py --today 2026-04-09 --timezone Europe/Rome
```

Invia automaticamente un riepilogo settimanale delle scadenze e reminder per spese imminenti. Viene saltato se `AUTH_ACCESS_MODE != normal`.

### Backup dati

```bash
python backup.py
```

Genera un dump SQL per ogni utente e lo invia via email. Dall'interfaccia è disponibile anche il download on-demand. Viene saltato se `AUTH_ACCESS_MODE != normal`.

### Orchestrazione su Cloud Run

`job_service.py` espone un endpoint HTTP che esegue notifiche e backup in sequenza, pensato per essere schedulato tramite Google Cloud Scheduler.

| Endpoint | Metodo | Descrizione |
|---|---|---|
| `/run-job` | `POST` | Esegue notifiche + backup |
| `/healthz` | `GET` | Health check |

---

## ☁️ Deploy su Google Cloud Run

Il repository include un `Dockerfile` compatibile con Cloud Run.

```bash
# Build immagine
docker build -t personal-budget-dashboard .

# Run locale via Docker
docker run --rm -p 8080:8080 personal-budget-dashboard
```

### Flusso di deploy consigliato

1. Configura i secret richiesti (es. tramite Google Secret Manager)
2. Builda e pusha l'immagine container nel tuo registry
3. Deploya il servizio su Cloud Run
4. Imposta `APP_BASE_URL` con l'URL pubblico del servizio
5. Se usi i job email, schedula `job_service.py` tramite Cloud Scheduler

---

## 📁 Struttura del repository

```
.
├── interfaccia.py
├── auth_manager.py
├── security.py
├── Database.py
├── logiche.py
├── config_runtime.py
├── gmail_sender.py
├── notification_worker.py
├── backup.py
├── job_service.py
├── requirements.txt
├── Dockerfile
├── icon/
├── utils/
│   ├── constants.py
│   ├── formatters.py
│   ├── charts.py
│   ├── html_tables.py
│   └── styles.py
└── pages/
```

---

## 🔒 Note di sicurezza per il repository

- Non committare mai `.env`, `.streamlit/secrets.toml`, token OAuth o file di credenziali
- Verifica che `.dockerignore` e `.gcloudignore` siano sempre presenti
- Se pubblichi il repository, tieni i segreti completamente separati dalla documentazione

---

## 📄 Licenza

© 2026. Tutti i diritti riservati.

Questo software è di proprietà esclusiva dell'autore. È vietata la copia, la distribuzione, la modifica o qualsiasi utilizzo del codice sorgente, in tutto o in parte, senza previa autorizzazione scritta del titolare.
