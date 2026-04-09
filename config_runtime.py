import json
import os
from functools import lru_cache

# ── Ambiente ──────────────────────────────────────────────────────────────────
# Su Streamlit Cloud questa sarà sempre False → nessun problema
IS_CLOUD_RUN = bool(os.getenv("K_SERVICE"))

LOCAL_BASE_URL_DEFAULT = "http://localhost:8501"  # 8501 è la porta di Streamlit


def _normalize(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
    else:
        value = str(value).strip()
    return value or None


def _read_env(name):
    return _normalize(os.getenv(name))

def _streamlit_module():
    try:
        import streamlit as st
        return st
    except Exception:
        return None


def _read_streamlit_secret(name):
    # su Streamlit vogliamo sempre leggere i secrets
    st = _streamlit_module()
    if st is None:
        return None
    try:
        value = st.secrets.get(name)
    except Exception:
        return None
    return _normalize(value)


def _resolve_app_env():
    raw = _read_env("APP_ENV") or _read_streamlit_secret("APP_ENV")
    return _normalize(raw) or "production"


def _is_demo_env(app_env):
    value = str(app_env or "").strip().lower()
    return value == "demo" or value.startswith("demo_")

# rileva se siamo in modalità demo
# in locale legge anche .streamlit/secrets.toml
APP_ENV = _resolve_app_env()
# IS_DEMO deriva da AUTH_ACCESS_MODE — un solo switch per tutto
_auth_mode_raw = _read_env("AUTH_ACCESS_MODE") or _read_streamlit_secret("AUTH_ACCESS_MODE") or "normal"
IS_DEMO = str(_auth_mode_raw).strip().lower() != "normal"

AUTH_MODE_ALLOWED = {"normal", "demo_only", "closed"}


# blocco Secret Manager lo lasciamo ma non verrà mai chiamato su Streamlit
@lru_cache(maxsize=1)
def _secret_manager_client():
    if not IS_CLOUD_RUN:
        return None
    try:
        from google.cloud import secretmanager
        return secretmanager.SecretManagerServiceClient()
    except Exception:
        return None


@lru_cache(maxsize=1)
def _google_project_id():
    for key in ("GOOGLE_CLOUD_PROJECT", "GCP_PROJECT", "GCLOUD_PROJECT"):
        value = _read_env(key)
        if value:
            return value
    for key in ("GOOGLE_CLOUD_PROJECT", "GCP_PROJECT_ID"):
        value = _read_streamlit_secret(key)
        if value:
            return value
    return None


def _read_secret_manager_secret(secret_id):
    if not IS_CLOUD_RUN:
        return None
    client = _secret_manager_client()
    project_id = _google_project_id()
    if client is None or not project_id:
        return None
    try:
        secret_name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": secret_name})
        return _normalize(response.payload.data.decode("utf-8"))
    except Exception:
        return None

def get_secret(name):
    """
    Ordine di lookup:
    1. Variabile d'ambiente (funziona sia in locale che ovunque)
    2. Cloud Run: Secret Manager
    3. Streamlit: st.secrets (secrets.toml in locale, Secrets nel cloud)
    """
    value = _read_env(name)
    if value:
        return value

    if IS_CLOUD_RUN:
        return _read_secret_manager_secret(name)

    return _read_streamlit_secret(name)


def export_runtime_env():
    """
    Esporta in os.environ solo le chiavi strettamente necessarie ai moduli legacy
    che non leggono ancora da get_secret()/st.secrets.
    """
    keys = (
        "DATABASE_URL",
        "DATABASE_URL_POOLER",
        "AUTH_ACCESS_MODE",
        "GEMINI_API_KEY",
    )
    for key in keys:
        value = get_secret(key)
        if value:
            os.environ[key] = value


def load_google_oauth_credentials():

    client_id = get_secret("GOOGLE_CLIENT_ID")
    client_secret = None

    raw_candidates = [get_secret("GOOGLE_CLIENT_SECRET_JSON"), get_secret("GOOGLE_CLIENT_SECRET")]
    for raw in raw_candidates:
        if not raw:
            continue
        value = str(raw).strip()
        if not value.startswith("{"):
            continue
        try:
            parsed = json.loads(value)
            payload = parsed.get("web") or parsed.get("installed") or parsed
            client_id = payload.get("client_id") or client_id
            client_secret = payload.get("client_secret") or client_secret
        except Exception:
            continue

    if not client_secret:
        raw_secret = get_secret("GOOGLE_CLIENT_SECRET")
        if raw_secret and not str(raw_secret).strip().startswith("{"):
            client_secret = str(raw_secret).strip()

    return _normalize(client_id), _normalize(client_secret)


def default_base_url():
    explicit = get_secret("APP_BASE_URL")
    if explicit:
        return explicit.rstrip("/")
    if IS_CLOUD_RUN:
        return None
    local_url = get_secret("LOCAL_BASE_URL") or LOCAL_BASE_URL_DEFAULT
    return local_url.rstrip("/")


def auth_access_mode():
    """
    Modalità accesso applicazione:
    - normal: login/registrazione abilitati
    - demo_only: solo account demo
    - closed: accessi disabilitati
    """
    raw = get_secret("AUTH_ACCESS_MODE")
    value = str(raw).strip().lower() if raw is not None else "normal"
    return value if value in AUTH_MODE_ALLOWED else "normal"
