"""
main.py
-------
Entry point NiceGUI — Personal Budget Dashboard.

Gestisce:
  - Bootstrap DB e configurazione
  - Autenticazione (email/password + Google OAuth)
  - Cookie di sessione (via nicegui app.storage.browser)
  - Layout globale: header, sidebar, navigazione tra pagine
  - Routing alle pagine (home, analisi, patrimonio, debiti, registro)

Tutti i calcoli e i dati sono delegati ai moduli esistenti invariati:
  logiche.py, Database.py, auth_manager.py, config_runtime.py
"""

import json
import base64
from datetime import datetime, date
from typing import Optional

from nicegui import app, ui, Client

from config_runtime import (
    IS_DEMO, default_base_url, export_runtime_env,
    load_google_oauth_credentials, get_secret, auth_access_mode,
)

export_runtime_env()
client_id, client_secret = load_google_oauth_credentials()
APP_BASE_URL = default_base_url()

import Database as db
from auth_manager import (
    create_session, validate_session, delete_session,
    login_email_password, register_user, get_display_name,
    AuthError, SESSION_TOKEN_COOKIE,
)
from utils.constants import MONTH_NAMES, MONTH_SHORT, Colors
from utils.formatters import eur2
import logiche as log
import pandas as pd


# ---------------------------------------------------------------------------
# Demo config
# ---------------------------------------------------------------------------
DEMO_USER_EMAIL = get_secret("DEMO_USER_EMAIL") if IS_DEMO else None
DEMO_USER_EMAIL_NORM = str(DEMO_USER_EMAIL or "").strip().lower() if DEMO_USER_EMAIL else None

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL     = "https://oauth2.googleapis.com/token"
USERINFO_URL  = "https://openidconnect.googleapis.com/v1/userinfo"

# ---------------------------------------------------------------------------
# CSS globale (tema dark indigo)
# ---------------------------------------------------------------------------
from utils.styles import CSS_ALL

# ---------------------------------------------------------------------------
# Bootstrap DB (eseguito una sola volta all'avvio del processo)
# ---------------------------------------------------------------------------
try:
    db.inizializza_db()
except Exception as _exc:
    print(f"[WARN] inizializza_db: {_exc}")

try:
    db.pulisci_sessioni_scadute()
except Exception:
    pass


# ---------------------------------------------------------------------------
# Helpers sessione (usa app.storage.browser — equivalente ai cookie NiceGUI)
# ---------------------------------------------------------------------------

def _get_session_token() -> Optional[str]:
    return app.storage.browser.get(SESSION_TOKEN_COOKIE)


def _set_session_token(token: str, expiry: datetime) -> None:
    app.storage.browser[SESSION_TOKEN_COOKIE] = token


def _clear_session_token() -> None:
    app.storage.browser.pop(SESSION_TOKEN_COOKIE, None)


def _get_current_user() -> Optional[str]:
    """Valida la sessione e restituisce l'email utente, o None."""
    token = _get_session_token()
    if not token:
        return None
    email = validate_session(token)
    if not email:
        _clear_session_token()
    return email


def _do_login(email: str) -> bool:
    try:
        token, expiry = create_session(email)
        _set_session_token(token, expiry)
        return True
    except AuthError:
        return False


def _do_logout() -> None:
    token = _get_session_token()
    if token:
        delete_session(token)
    _clear_session_token()


# ---------------------------------------------------------------------------
# Decode Google id_token → email
# ---------------------------------------------------------------------------

def _decode_id_token_email(id_token) -> Optional[str]:
    if not id_token:
        return None
    try:
        if isinstance(id_token, (bytes, bytearray)):
            data = json.loads(id_token.decode("utf-8"))
            email = data.get("email")
            return str(email).strip().lower() if email else None
        if isinstance(id_token, str) and "." not in id_token:
            data = json.loads(id_token)
            email = data.get("email")
            return str(email).strip().lower() if email else None
        if not isinstance(id_token, str):
            return None
        parts = id_token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        raw = base64.urlsafe_b64decode((payload + padding).encode()).decode()
        email = json.loads(raw).get("email")
        return str(email).strip().lower() if email else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Schermata login
# ---------------------------------------------------------------------------

def render_login_page() -> None:
    """Renderizza la schermata di login completa."""
    mode = auth_access_mode()

    ui.add_css(CSS_ALL)
    ui.add_css("""
        .login-card {
            background: var(--bg-card);
            border: 1px solid var(--bdr-md);
            border-radius: 18px;
            padding: 40px 36px;
            max-width: 420px;
            width: 100%;
            box-shadow: 0 8px 48px rgba(0,0,0,0.5), 0 0 60px rgba(79,142,240,0.07);
        }
        .login-title {
            font-size: 1.7rem; font-weight: 700; color: #e6eef9;
            font-family: 'Plus Jakarta Sans', sans-serif;
            text-align: center; margin-bottom: 4px;
        }
        .login-subtitle {
            color: rgba(230,238,249,0.6); font-size: 0.88rem;
            text-align: center; margin-bottom: 24px;
        }
    """)

    with ui.column().classes("w-full min-h-screen items-center justify-center").style(
        "background: var(--bg);"
    ):
        with ui.element("div").classes("login-card"):
            ui.html("<div class='login-title'>💰 Personal Budget</div>")
            ui.html("<div class='login-subtitle'>Accedi per esplorare la dashboard</div>")

            if mode == "closed":
                ui.notify("Accesso disabilitato. Riprova più tardi.", type="warning")
                ui.label("Accesso disabilitato. Riprova quando il servizio sarà riattivato.").classes("text-amber-400")
                return

            if IS_DEMO:
                _render_login_tabs(mode)
            else:
                _render_google_only_login()


def _render_login_tabs(mode: str) -> None:
    """Tab Login / Registra / Demo (modalità IS_DEMO)."""
    disabled = (mode == "demo_only")

    with ui.tabs().classes("w-full") as tabs:
        tab_login = ui.tab("🔑 Accedi")
        tab_reg   = ui.tab("📝 Registrati")
        tab_demo  = ui.tab("🚀 Demo")

    with ui.tab_panels(tabs, value=tab_login).classes("w-full"):

        # ── TAB LOGIN ──
        with ui.tab_panel(tab_login):
            if disabled:
                ui.label("Login utenti temporaneamente disattivato. Usa la tab Demo.").classes("text-blue-400 text-sm")
            email_inp = ui.input("Email", placeholder="email@esempio.com").classes("w-full").props("outlined dense" + (" disabled" if disabled else ""))
            pwd_inp   = ui.input("Password", password=True, password_toggle_button=True).classes("w-full").props("outlined dense" + (" disabled" if disabled else ""))

            def do_email_login():
                e = email_inp.value.strip()
                p = pwd_inp.value
                if not e or not p:
                    ui.notify("Inserisci email e password.", type="warning")
                    return
                try:
                    email_norm, token, expiry = login_email_password(e, p)
                    _set_session_token(token, expiry)
                    ui.navigate.to("/")
                except AuthError as exc:
                    ui.notify(str(exc), type="negative")

            ui.button("Accedi", on_click=do_email_login).classes("w-full mt-2").props("unelevated" + (" disabled" if disabled else "")).style("background: var(--acc); color: #fff;")

        # ── TAB REGISTRAZIONE ──
        with ui.tab_panel(tab_reg):
            if disabled:
                ui.label("Registrazione temporaneamente disattivata. Usa la tab Demo.").classes("text-blue-400 text-sm")
            nome_inp   = ui.input("Nome").classes("w-full").props("outlined dense" + (" disabled" if disabled else ""))
            email_r    = ui.input("Email").classes("w-full").props("outlined dense" + (" disabled" if disabled else ""))
            pwd_r      = ui.input("Password", password=True, password_toggle_button=True).classes("w-full").props("outlined dense" + (" disabled" if disabled else ""))
            pwd_r2     = ui.input("Conferma password", password=True, password_toggle_button=True).classes("w-full").props("outlined dense" + (" disabled" if disabled else ""))

            def do_register():
                if not email_r.value or not pwd_r.value:
                    ui.notify("Compila email e password.", type="warning")
                    return
                if pwd_r.value != pwd_r2.value:
                    ui.notify("Le password non coincidono.", type="negative")
                    return
                try:
                    register_user(email_r.value.strip(), pwd_r.value, nome_inp.value.strip())
                    ui.notify("Registrazione completata! Ora accedi dalla tab 'Accedi'.", type="positive")
                except AuthError as exc:
                    ui.notify(str(exc), type="negative")

            ui.button("Registrati", on_click=do_register).classes("w-full mt-2").props("unelevated" + (" disabled" if disabled else "")).style("background: var(--acc); color: #fff;")

        # ── TAB DEMO ──
        with ui.tab_panel(tab_demo):
            ui.label("Esplora tutte le funzionalità con dati di esempio.").classes("text-sm").style("color: rgba(230,238,249,0.7);")

            def do_demo_login():
                if DEMO_USER_EMAIL and _do_login(DEMO_USER_EMAIL):
                    ui.navigate.to("/")
                else:
                    ui.notify("Credenziali demo non configurate.", type="negative")

            ui.button("▶ Entra in modalità Demo", on_click=do_demo_login).classes("w-full mt-3").props("unelevated").style("background: var(--violet); color: #fff;")


def _render_google_only_login() -> None:
    """Login Google OAuth (produzione, IS_DEMO=False)."""
    if not client_id or not client_secret:
        ui.label("Credenziali Google OAuth non configurate.").classes("text-red-400")
        return

    redirect_uri = (APP_BASE_URL or "http://localhost:8080").rstrip("/") + "/oauth/callback"
    params = (
        f"client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=openid%20email%20profile"
        f"&prompt=select_account"
    )
    google_url = f"{AUTHORIZE_URL}?{params}"

    ui.button("Accedi con Google", on_click=lambda: ui.navigate.to(google_url, new_tab=False)).classes("w-full").props("unelevated").style("background: #4285F4; color: #fff;")


# ---------------------------------------------------------------------------
# Caricamento dati centralizzato per sessione
# ---------------------------------------------------------------------------

def _load_user_data(user_email: str) -> dict:
    """
    Carica tutti i dati dell'utente in un unico dict.
    Chiamato una sola volta per richiesta — il risultato viene
    passato come parametro alle pagine.
    """
    df_mov = db.carica_dati(user_email)
    df_mov.columns = [c.capitalize() for c in df_mov.columns]
    if "Data" in df_mov:
        df_mov["Data"] = pd.to_datetime(df_mov["Data"], errors="coerce")
    else:
        df_mov["Data"] = pd.Series(pd.NaT, index=df_mov.index, dtype="datetime64[ns]")
    if "Tipo" in df_mov:
        df_mov["Tipo"] = df_mov["Tipo"].astype(str).str.upper().str.strip().replace(
            {"ENTRATE": "ENTRATA", "USCITE": "USCITA"}
        )
    if "Categoria" in df_mov:
        df_mov["Categoria"] = df_mov["Categoria"].astype(str).str.upper().str.strip()

    df_fin = db.carica_finanziamenti(user_email)

    return {"df_mov": df_mov, "df_fin": df_fin}


def _load_settings(user_email: str) -> dict:
    """Carica asset_settings come dict {chiave: (valore_num, valore_txt)}."""
    try:
        with db.connetti_db() as conn:
            df = pd.read_sql(
                "SELECT chiave, valore_numerico, valore_testo "
                "FROM asset_settings WHERE user_email = %s",
                conn, params=(user_email,),
            )
        if df.empty:
            return {}
        df = df.drop_duplicates(subset=["chiave"], keep="last")
        return {
            row["chiave"]: (row["valore_numerico"], row["valore_testo"])
            for _, row in df.iterrows()
        }
    except Exception:
        return {}


def s_num(settings: dict, key: str, default: float = 0.0) -> float:
    entry = settings.get(key)
    if entry is None:
        return default
    try:
        val = entry[0]
        return float(val) if val is not None and str(val) not in ("nan", "None") else default
    except Exception:
        return default


def s_txt(settings: dict, key: str, default: str = "") -> str:
    entry = settings.get(key)
    if entry is None:
        return default
    try:
        val = entry[1]
        return str(val) if val is not None and str(val) not in ("nan", "None") else default
    except Exception:
        return default


def s_num_candidates(settings: dict, keys: list, default: float = 0.0) -> float:
    for k in keys:
        v = s_num(settings, k, None)
        if v is not None:
            return v
    return default


# ---------------------------------------------------------------------------
# Layout principale (header + drawer laterale)
# ---------------------------------------------------------------------------

def render_main_layout(user_email: str, page_fn, anno_sel: int, mese_sel: int,
                       settings: dict, data: dict) -> None:
    """
    Costruisce il layout comune a tutte le pagine:
      - Header top con nome utente e logout
      - Left drawer con parametri rapidi
      - Area contenuto dove viene renderizzata page_fn()
    """
    ui.add_css(CSS_ALL)
    ui.add_css(_extra_nicegui_css())

    is_demo = IS_DEMO and (str(user_email).strip().lower() == DEMO_USER_EMAIL_NORM)
    nome_display = get_display_name(user_email, is_demo_account=is_demo)
    saldo_iniziale = s_num_candidates(
        settings,
        [f"saldo_iniziale_{anno_sel}", f"saldo iniziale_{anno_sel}"],
        0.0,
    )
    kpi = log.calcola_kpi_dashboard(data["df_mov"], mese_sel, anno_sel)
    saldo_disp = log.saldo_disponibile_da_inizio(data["df_mov"], anno_sel, mese_sel, saldo_iniziale)

    # ── Header ──
    with ui.header().classes("items-center justify-between px-6 py-2").style(
        "background: var(--bg-surf); border-bottom: 1px solid var(--bdr); min-height: 52px;"
    ):
        with ui.row().classes("items-center gap-3"):
            ui.html("<span style='font-size:1.25rem;font-weight:800;color:var(--acc);letter-spacing:-0.5px;'>💰 Personal Budget</span>")
            ui.html(
                f"<span style='font-size:0.72rem;font-weight:700;letter-spacing:1.4px;"
                f"text-transform:uppercase;color:var(--txt-mid);margin-left:12px;'>"
                f"{MONTH_NAMES.get(mese_sel, '')} {anno_sel}</span>"
            )

        with ui.row().classes("items-center gap-4"):
            # KPI mini strip
            _kpi_strip(saldo_disp, kpi)
            ui.html(
                f"<span style='font-size:0.78rem;color:var(--acc-lt);font-weight:600;'>{nome_display}</span>"
            )
            ui.button(icon="logout", on_click=lambda: _handle_logout()).props("flat dense round").style("color: var(--txt-mid);")

    # ── Left drawer ──
    drawer = ui.left_drawer(fixed=True).style(
        "background: var(--bg-surf); border-right: 1px solid var(--bdr); padding: 16px 12px; width: 280px;"
    )
    with drawer:
        _render_sidebar(user_email, anno_sel, mese_sel, settings, data)

    # ── Demo banner ──
    if is_demo:
        ui.notify("👁️ Modalità Demo — dati di esempio", type="info", timeout=3000)

    # ── Navigazione tab ──
    with ui.element("div").classes("w-full px-4 pt-2"):
        _render_nav_tabs(anno_sel, mese_sel)

    # ── Contenuto pagina ──
    with ui.element("div").classes("w-full px-4 pb-8"):
        page_fn(user_email, anno_sel, mese_sel, settings, data)


def _kpi_strip(saldo_disp: float, kpi: dict) -> None:
    """Mini KPI row nell'header."""
    items = [
        ("Saldo", eur2(saldo_disp), Colors.GREEN_BRIGHT),
        ("Uscite", eur2(kpi.get("uscite_mese", 0)), Colors.RED_BRIGHT),
        ("Risparmio", eur2(kpi.get("risparmio_mese", 0)), Colors.GREEN_BRIGHT),
        ("Tasso", f"{kpi.get('tasso_risparmio', 0)}%", Colors.VIOLET),
    ]
    with ui.row().classes("gap-4"):
        for label, value, color in items:
            with ui.column().classes("items-center gap-0"):
                ui.html(f"<span style='font-size:0.6rem;color:var(--txt-mid);text-transform:uppercase;letter-spacing:1px;'>{label}</span>")
                ui.html(f"<span style='font-size:0.85rem;font-weight:700;color:{color};font-family:JetBrains Mono,monospace;'>{value}</span>")


def _render_nav_tabs(anno_sel: int, mese_sel: int) -> None:
    """Barra di navigazione tra le pagine."""
    pages = [
        ("🏠 HOME",       "/"),
        ("📈 ANALISI",    "/analisi"),
        ("💰 PATRIMONIO", "/patrimonio"),
        ("🔗 DEBITI",     "/debiti"),
        ("📝 REGISTRO",   "/registro"),
    ]
    with ui.tabs().classes("w-full").style(
        "background: transparent; border-bottom: 1px solid var(--bdr); margin-bottom: 12px;"
    ):
        for label, path in pages:
            ui.tab(label, on_click=lambda p=path: ui.navigate.to(
                f"{p}?anno={anno_sel}&mese={mese_sel}"
            )).style("color: var(--txt); font-weight: 600; font-size: 0.8rem;")


def _render_sidebar(user_email: str, anno_sel: int, mese_sel: int,
                    settings: dict, data: dict) -> None:
    """Sidebar con selettore anno/mese e impostazioni rapide."""
    ui.html("<div style='font-size:0.72rem;font-weight:700;letter-spacing:1.4px;text-transform:uppercase;color:var(--acc);margin-bottom:12px;'>PARAMETRI</div>")

    # Anno e mese
    df_mov = data["df_mov"]
    if not df_mov.empty and "Data" in df_mov.columns:
        anni = sorted(df_mov["Data"].dt.year.dropna().astype(int).unique().tolist())
    else:
        anni = [datetime.now().year]
    anni_str = [str(a) for a in anni]

    anno_select = ui.select(
        options=anni_str,
        value=str(anno_sel),
        label="Anno",
    ).classes("w-full").props("outlined dense")
    anno_select.style("background: var(--bg-inp); color: var(--txt);")

    mese_select = ui.select(
        options={str(k): v for k, v in MONTH_SHORT.items()},
        value=str(mese_sel),
        label="Mese",
    ).classes("w-full mt-2").props("outlined dense")
    mese_select.style("background: var(--bg-inp); color: var(--txt);")

    def apply_params():
        a = int(anno_select.value) if anno_select.value else anno_sel
        m = int(mese_select.value) if mese_select.value else mese_sel
        import re
        current = str(ui.context.client.request.url.path)
        ui.navigate.to(f"{current}?anno={a}&mese={m}")

    ui.button("Applica", on_click=apply_params).classes("w-full mt-2").props("unelevated dense").style("background: var(--acc); color: #fff; font-size: 0.78rem;")

    ui.separator().style("border-color: var(--bdr); margin: 12px 0;")

    # Budget residuo mese
    budget_base = s_num(settings, "budget_mensile_base", 1600.0)
    df_budget = log.budget_spese_annuale(df_mov, anno_sel, budget_base)
    mese_short = MONTH_SHORT.get(mese_sel, str(mese_sel))
    ui.html(f"<div style='font-size:0.72rem;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--txt-mid);margin-bottom:6px;'>Residuo {mese_short}</div>")
    if not df_budget.empty:
        df_res = df_budget[df_budget["Mese"] == mese_short][["Categoria", "Residuo"]]
        if not df_res.empty:
            residuo_tot = df_res["Residuo"].sum()
            color = Colors.RED if residuo_tot < 0 else Colors.GREEN
            arrow = "↓" if residuo_tot < 0 else "↑"
            ui.html(
                f"<div style='font-size:1.1rem;font-weight:700;color:{color};"
                f"font-family:JetBrains Mono,monospace;'>"
                f"{arrow} {eur2(residuo_tot, signed=True)}</div>"
            )
    else:
        ui.label("Nessun dato budget.").classes("text-xs").style("color: var(--txt-mid);")

    ui.separator().style("border-color: var(--bdr); margin: 12px 0;")

    # Impostazioni rapide (collapsible)
    with ui.expansion("⚙️ Impostazioni rapide").classes("w-full").style(
        "background: var(--bg-form); border: 1px solid var(--bdr); border-radius: 8px;"
    ):
        _render_quick_settings(user_email, anno_sel, settings)


def _render_quick_settings(user_email: str, anno_sel: int, settings: dict) -> None:
    """Form impostazioni rapide nella sidebar."""
    prev_year = anno_sel - 1

    def _num(key, default=0.0):
        return s_num(settings, key, default)

    def _txt(key, default=""):
        return s_txt(settings, key, default)

    fields = {}

    def add_num(key, label, default, step=1.0, fmt=None):
        v = _num(key, default)
        inp = ui.number(label=label, value=v, step=step, format=fmt).classes("w-full").props("outlined dense")
        inp.style("background: var(--bg-inp); color: var(--txt); font-size: 0.78rem;")
        fields[key] = inp

    def add_txt_field(key, label, default=""):
        v = _txt(key, default)
        inp = ui.input(label=label, value=v).classes("w-full").props("outlined dense")
        inp.style("background: var(--bg-inp); color: var(--txt); font-size: 0.78rem;")
        fields[key] = inp

    add_num("obiettivo_risparmio_perc",          f"Incr. risparmio % (vs {prev_year})", 30.0)
    add_num(f"risparmio_precedente_{prev_year}",  f"Risparmio {prev_year} (€)",         0.0, 100.0)
    add_num(f"saldo_iniziale_{anno_sel}",          f"Saldo iniziale {anno_sel} (€)",     0.0, 100.0)
    add_num("budget_mensile_base",                 "Budget mensile base (€)",            1600.0, 50.0)
    add_num("saldo_fineco",                        "Saldo Fineco (€)",                   0.0, 50.0)
    add_num("saldo_revolut",                       "Saldo Revolut (€)",                  0.0, 50.0)
    add_num("pac_quote",                           "Quote PAC",                          0.0, 1.0)
    add_num("pac_capitale_investito",              "Capitale PAC (€)",                   0.0, 10.0)
    add_num("pac_versamento_mensile",              "Versamento PAC/mese (€)",            80.0, 10.0)
    add_txt_field("pac_ticker",                    "Ticker ETF PAC",                     "VNGA80")
    add_num("pac_rendimento_stimato",              "Rendimento PAC (%)",                 7.0, 0.5)
    add_num("fondo_quote",                         "Quote Fondo Pensione",               0.0, 1.0)
    add_num("fondo_capitale_investito",            "Capitale Fondo (€)",                 0.0, 10.0)
    add_num("fondo_versamento_mensile",            "Versamento Fondo/mese (€)",          50.0, 10.0)
    add_num("fondo_valore_quota",                  "Valore quota Fondo",                 7.28, 0.01, "%.4f")
    add_num("aliquota_irpef",                      "Aliquota IRPEF (0-1)",               0.26, 0.01, "%.2f")
    add_num("fondo_rendimento_stimato",            "Rendimento Fondo (%)",               5.0, 0.5)
    add_num("fondo_tfr_versato_anno",              "TFR versato anno (€)",               0.0, 100.0)
    add_txt_field("fondo_data_snapshot",           "Data snapshot Fondo (YYYY-MM-DD)",   str(date.today()))

    def save_settings():
        try:
            with db.connetti_db() as conn:
                with conn.cursor() as cur:
                    upsert_q = (
                        "INSERT INTO asset_settings "
                        "(chiave, user_email, valore_numerico, valore_testo) "
                        "VALUES (%s, %s, %s, %s) "
                        "ON CONFLICT (chiave, user_email) DO UPDATE SET "
                        "valore_numerico = EXCLUDED.valore_numerico, "
                        "valore_testo = EXCLUDED.valore_testo"
                    )
                    for key, widget in fields.items():
                        val = widget.value
                        if isinstance(val, (int, float)):
                            cur.execute(upsert_q, (key, user_email, float(val), None))
                        else:
                            cur.execute(upsert_q, (key, user_email, None, str(val) if val else ""))
            ui.notify("✅ Impostazioni salvate.", type="positive")
            ui.navigate.reload()
        except Exception as exc:
            ui.notify(f"Errore: {exc}", type="negative")

    ui.button("💾 Salva impostazioni", on_click=save_settings).classes("w-full mt-3").props("unelevated").style("background: var(--acc); color: #fff; font-size: 0.78rem;")


def _handle_logout() -> None:
    _do_logout()
    ui.navigate.to("/login")


# ---------------------------------------------------------------------------
# CSS aggiuntivo specifico NiceGUI
# ---------------------------------------------------------------------------

def _extra_nicegui_css() -> str:
    return """
    body, .nicegui-content { background: var(--bg) !important; color: var(--txt); }
    .q-header { z-index: 100; }
    .q-drawer { z-index: 99; }
    .q-tabs__content { gap: 4px; }
    .q-tab { font-size: 0.78rem !important; font-weight: 600 !important; }
    .q-tab--active { color: var(--acc) !important; }
    .q-tab-panels { background: transparent !important; }
    .q-expansion-item__container { background: var(--bg-form) !important; }
    .q-field__control { background: var(--bg-inp) !important; color: var(--txt) !important; }
    .q-field__label { color: var(--txt-mid) !important; }
    .q-item { color: var(--txt) !important; }
    .nicegui-plotly { border-radius: 10px; overflow: hidden; }
    """


# ---------------------------------------------------------------------------
# Route: OAuth callback
# ---------------------------------------------------------------------------

@ui.page("/oauth/callback")
async def oauth_callback(code: str = "", error: str = "") -> None:
    """Gestisce il callback OAuth Google."""
    if error or not code:
        ui.notify(f"Errore OAuth: {error or 'codice mancante'}", type="negative")
        ui.navigate.to("/login")
        return

    redirect_uri = (APP_BASE_URL or "http://localhost:8080").rstrip("/") + "/oauth/callback"
    import urllib.parse, urllib.request
    body = urllib.parse.urlencode({
        "code": code, "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": redirect_uri, "grant_type": "authorization_code",
    }).encode()
    try:
        req = urllib.request.Request(TOKEN_URL, data=body, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            token_data = json.loads(resp.read())
        id_token = token_data.get("id_token")
        email = _decode_id_token_email(id_token)
        if not email:
            access_token = token_data.get("access_token")
            if access_token:
                req2 = urllib.request.Request(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
                with urllib.request.urlopen(req2, timeout=15) as resp2:
                    email = json.loads(resp2.read()).get("email", "")
                    email = str(email).strip().lower() or None
        if email and _do_login(email):
            ui.navigate.to("/")
        else:
            ui.notify("Impossibile leggere l'email dal profilo Google.", type="negative")
            ui.navigate.to("/login")
    except Exception as exc:
        ui.notify(f"Errore OAuth: {exc}", type="negative")
        ui.navigate.to("/login")


# ---------------------------------------------------------------------------
# Pagine
# ---------------------------------------------------------------------------

def _resolve_params(request) -> tuple[int, int]:
    """Estrae anno e mese dai query params, con fallback al mese corrente."""
    try:
        anno = int(request.query_params.get("anno", datetime.now().year))
        mese = int(request.query_params.get("mese", datetime.now().month))
    except (ValueError, AttributeError):
        anno = datetime.now().year
        mese = datetime.now().month
    return anno, mese


def _page_factory(page_fn):
    """
    Factory che crea una coroutine NiceGUI page con auth check, data loading,
    e render del layout comune.
    """
    async def page_handler(client: Client) -> None:
        await client.connected()
        user_email = _get_current_user()
        if not user_email:
            ui.navigate.to("/login")
            return
        anno_sel, mese_sel = _resolve_params(client.request)
        settings = _load_settings(user_email)
        data     = _load_user_data(user_email)
        render_main_layout(user_email, page_fn, anno_sel, mese_sel, settings, data)

    return page_handler


# ── Registrazione route ──────────────────────────────────────────────────────

@ui.page("/login")
async def login_page() -> None:
    user_email = _get_current_user()
    if user_email:
        ui.navigate.to("/")
        return
    render_login_page()


@ui.page("/")
async def page_home(client: Client) -> None:
    from pages.home import render
    await _page_factory(render)(client)


@ui.page("/analisi")
async def page_analisi(client: Client) -> None:
    from pages.analisi import render
    await _page_factory(render)(client)


@ui.page("/patrimonio")
async def page_patrimonio(client: Client) -> None:
    from pages.patrimonio import render
    await _page_factory(render)(client)


@ui.page("/debiti")
async def page_debiti(client: Client) -> None:
    from pages.debiti import render
    await _page_factory(render)(client)


@ui.page("/registro")
async def page_registro(client: Client) -> None:
    from pages.registro import render
    await _page_factory(render)(client)


# ---------------------------------------------------------------------------
# Avvio
# ---------------------------------------------------------------------------

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="Personal Budget Dashboard",
        host="0.0.0.0",
        port=8080,
        dark=True,
        storage_secret=get_secret("APP_STORAGE_SECRET") or "pb_dev_secret_change_me",
        favicon="💰",
        reload=False,
    )