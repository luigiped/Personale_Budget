"""
pages/registro.py
-----------------
Pagina REGISTRO — Personal Budget Dashboard.

Sezioni:
  1. Nuova Transazione (form inserimento movimento)
  2. Spese Ricorrenti (aggiungi, lista, elimina)
  3. Finanziamenti (aggiungi, lista, elimina)
  4. Storico Movimenti (filtri + tabella scrollabile + elimina)
  5. Backup Dati (download SQL on-demand)
"""

import re
from datetime import datetime, date
from html import escape

import pandas as pd
from nicegui import ui

import Database as db
import logiche as log
from utils.constants import Colors, STRUTTURA_CATEGORIE, FREQ_OPTIONS, FREQ_MAP, PLOTLY_CONFIG
from utils.formatters import format_eur, eur2, chip_html
from utils.html_tables import scroll_table, render_ricorrenti_rows, _td, _tr
from config_runtime import get_secret


def render(user_email: str, anno_sel: int, mese_sel: int, settings: dict, data: dict) -> None:
    """Entry point — chiamata da main.py."""
    ui.html("<div class='section-title'>REGISTRO</div>")

    _render_nuova_transazione(user_email, data)
    ui.html("<div style='height:12px'></div>")
    _render_spese_ricorrenti(user_email)
    ui.html("<div style='height:12px'></div>")
    _render_finanziamenti(user_email, data)
    ui.html("<div style='height:12px'></div>")
    _render_storico_movimenti(user_email, data)
    ui.html("<div style='height:12px'></div>")
    _render_backup(user_email)


# ---------------------------------------------------------------------------
# 1. Nuova Transazione
# ---------------------------------------------------------------------------

def _render_nuova_transazione(user_email: str, data: dict) -> None:
    with ui.card().classes("w-full").style(
        "background: var(--bg-card); border: 1px solid var(--bdr); border-radius: 12px; padding: 20px;"
    ):
        ui.html("""<div style="display:flex;align-items:center;gap:10px;margin-bottom:18px;">
  <div style="width:28px;height:28px;border-radius:7px;background:rgba(79,142,240,0.12);
              display:flex;align-items:center;justify-content:center;font-size:15px;">💳</div>
  <span style="font-size:13px;font-weight:700;color:#dde6f5;">Nuova Transazione</span>
</div>""")

        # Riga 1: Tipo / Categoria / Dettaglio / Data
        with ui.grid(columns=4).classes("w-full gap-3"):
            tipo_radio = ui.radio(
                options={"USCITA": "↑ Uscita", "ENTRATA": "↓ Entrata"},
                value="USCITA",
            ).props("inline").style("color: var(--txt);")

            cat_select = ui.select(
                options=list(STRUTTURA_CATEGORIE.keys()),
                value=list(STRUTTURA_CATEGORIE.keys())[0],
                label="Categoria",
            ).classes("w-full").props("outlined dense")
            cat_select.style("background: var(--bg-inp); color: var(--txt);")

            det_select = ui.select(
                options=STRUTTURA_CATEGORIE[list(STRUTTURA_CATEGORIE.keys())[0]],
                value=STRUTTURA_CATEGORIE[list(STRUTTURA_CATEGORIE.keys())[0]][0],
                label="Dettaglio",
            ).classes("w-full").props("outlined dense")
            det_select.style("background: var(--bg-inp); color: var(--txt);")

            data_inp = ui.date(value=date.today().isoformat()).props("outlined dense").classes("w-full")
            data_inp.style("background: var(--bg-inp); color: var(--txt);")

        # Aggiorna dettagli quando cambia categoria
        def on_cat_change():
            cat = cat_select.value
            opts = STRUTTURA_CATEGORIE.get(cat, [])
            det_select.options = opts
            det_select.value = opts[0] if opts else ""
            det_select.update()

        cat_select.on("update:model-value", lambda: on_cat_change())

        # Riga 2: Importo / Note
        with ui.grid(columns=4).classes("w-full gap-3 mt-2"):
            importo_inp = ui.number(
                label="Importo (€)", value=0.0, min=0.0, step=0.01, format="%.2f",
            ).classes("w-full").props("outlined dense")
            importo_inp.style("background: var(--bg-inp); color: var(--txt);")

            note_inp = ui.input(
                label="Note", placeholder="Descrizione opzionale…",
            ).classes("col-span-3 w-full").props("outlined dense")
            note_inp.style("background: var(--bg-inp); color: var(--txt);")

        # Pulsanti
        with ui.row().classes("gap-3 mt-3"):
            def registra():
                imp = float(importo_inp.value or 0)
                if imp <= 0:
                    ui.notify("Inserisci un importo maggiore di zero.", type="warning")
                    return
                try:
                    d = data_inp.value
                    if isinstance(d, str):
                        d = datetime.fromisoformat(d).date()
                    db.aggiungi_movimento(
                        d, tipo_radio.value,
                        cat_select.value, det_select.value,
                        imp, note_inp.value or "", user_email=user_email,
                    )
                    importo_inp.value = 0.0
                    note_inp.value = ""
                    ui.notify("✅ Movimento registrato con successo!", type="positive")
                    ui.navigate.reload()
                except Exception as exc:
                    ui.notify(f"Errore salvataggio: {exc}", type="negative")

            def annulla():
                importo_inp.value = 0.0
                note_inp.value = ""

            ui.button("＋ Registra Movimento", on_click=registra).props("unelevated").style(
                "background: var(--acc); color: #fff; font-weight: 600;"
            )
            ui.button("Annulla", on_click=annulla).props("flat").style("color: var(--txt-mid);")


# ---------------------------------------------------------------------------
# 2. Spese Ricorrenti
# ---------------------------------------------------------------------------

def _render_spese_ricorrenti(user_email: str) -> None:
    df_ric = db.carica_spese_ricorrenti(user_email)
    n_ric  = len(df_ric) if not df_ric.empty else 0

    with ui.card().classes("w-full").style(
        "background: var(--bg-card); border: 1px solid var(--bdr); border-radius: 12px; padding: 20px;"
    ):
        with ui.row().classes("items-center justify-between w-full mb-4"):
            ui.html("<span style='font-size:13px;font-weight:700;color:#dde6f5;'>🔁 Spese Ricorrenti</span>")
            ui.html(
                f"<span style='font-size:10px;padding:3px 10px;border-radius:20px;"
                f"background:rgba(79,142,240,0.12);color:#82b4f7;"
                f"border:1px solid rgba(79,142,240,0.28);'>{n_ric} attive</span>"
            )

        # Form aggiungi
        with ui.grid(columns=3).classes("w-full gap-3"):
            desc_inp  = ui.input("Descrizione spesa").classes("w-full").props("outlined dense")
            desc_inp.style("background: var(--bg-inp); color: var(--txt);")
            imp_inp   = ui.number("Importo (€)", value=0.0, min=0.0, step=0.01, format="%.2f").classes("w-full").props("outlined dense")
            imp_inp.style("background: var(--bg-inp); color: var(--txt);")
            freq_sel  = ui.select(options=list(FREQ_OPTIONS.keys()), value="Mensile", label="Frequenza").classes("w-full").props("outlined dense")
            freq_sel.style("background: var(--bg-inp); color: var(--txt);")

        with ui.grid(columns=4).classes("w-full gap-3 mt-2"):
            giorno_inp    = ui.number("Giorno scadenza", value=1, min=1, max=31, step=1).classes("w-full").props("outlined dense")
            giorno_inp.style("background: var(--bg-inp); color: var(--txt);")
            inizio_inp    = ui.date(value=date.today().isoformat()).props("outlined dense").classes("w-full")
            inizio_inp.style("background: var(--bg-inp); color: var(--txt);")
            senza_fine    = ui.checkbox("Senza data fine", value=False)
            senza_fine.style("color: var(--txt);")
            fine_inp      = ui.date(value=date.today().isoformat()).props("outlined dense").classes("w-full")
            fine_inp.style("background: var(--bg-inp); color: var(--txt);")

        def toggle_fine():
            fine_inp.set_visibility(not senza_fine.value)

        senza_fine.on("update:model-value", lambda: toggle_fine())

        def aggiungi_ricorrente():
            desc = desc_inp.value.strip()
            imp  = float(imp_inp.value or 0)
            if not desc or imp <= 0:
                ui.notify("Inserisci descrizione e importo.", type="warning")
                return
            try:
                d_inizio = date.fromisoformat(inizio_inp.value) if isinstance(inizio_inp.value, str) else inizio_inp.value
                d_fine   = None if senza_fine.value else (date.fromisoformat(fine_inp.value) if isinstance(fine_inp.value, str) else fine_inp.value)
                db.aggiungi_spesa_ricorrente(
                    desc, imp, int(giorno_inp.value), FREQ_OPTIONS[freq_sel.value],
                    d_inizio, d_fine, user_email=user_email,
                )
                ui.notify("✅ Spesa ricorrente salvata!", type="positive")
                ui.navigate.reload()
            except Exception as exc:
                ui.notify(f"Errore: {exc}", type="negative")

        ui.button("＋ Aggiungi Ricorrente", on_click=aggiungi_ricorrente).props("unelevated").style(
            "background: var(--acc); color: #fff; font-weight: 600; margin-top: 8px;"
        )

        # Tabella ricorrenti
        if not df_ric.empty:
            tot_mensile = df_ric["importo"].sum()
            ric_rows    = render_ricorrenti_rows(df_ric, FREQ_MAP)
            ui.html(scroll_table(
                title="Elenco ricorrenti",
                right_html=f"{format_eur(tot_mensile, 2)} / mese",
                columns=[("#","left"),("Descrizione","left"),("Importo","left"),("Frequenza","left"),("Scad.","center"),("Inizio","center"),("Fine","center")],
                widths=[0.45, 2.6, 1.1, 1.25, 0.7, 1.1, 0.9],
                rows_html=ric_rows, height_px=280,
            )).classes("w-full mt-3")

            # Elimina ricorrente
            ric_options = {
                str(row["id"]): f"{row['descrizione']} | {format_eur(row['importo'], 2)}"
                for _, row in df_ric.iterrows()
            }
            with ui.row().classes("items-end gap-3 mt-3"):
                sel_ric = ui.select(
                    options=ric_options, label="Seleziona ricorrente da eliminare",
                ).classes("flex-1").props("outlined dense")
                sel_ric.style("background: var(--bg-inp); color: var(--txt);")

                confirm_ric = {"pending": False}

                def richiedi_elimina_ric():
                    confirm_ric["pending"] = True
                    confirm_banner_ric.set_visibility(True)

                def conferma_elimina_ric():
                    try:
                        db.elimina_spesa_ricorrente(int(sel_ric.value), user_email=user_email)
                        ui.notify("✅ Spesa ricorrente eliminata.", type="positive")
                        ui.navigate.reload()
                    except Exception as exc:
                        ui.notify(f"Errore: {exc}", type="negative")

                def annulla_elimina_ric():
                    confirm_ric["pending"] = False
                    confirm_banner_ric.set_visibility(False)

                ui.button("🗑️ Elimina", on_click=richiedi_elimina_ric).props("unelevated").style(
                    "background: var(--red-dim, rgba(242,106,106,0.15)); color: var(--red, #f26a6a); border: 1px solid rgba(242,106,106,0.3);"
                )

            confirm_banner_ric = ui.element("div").classes("w-full")
            with confirm_banner_ric:
                ui.html("<div style='color: var(--amber); font-size:0.85rem; margin:8px 0;'>⚠️ Operazione irreversibile. Confermi l'eliminazione?</div>")
                with ui.row().classes("gap-3"):
                    ui.button("🗑️ Sì, elimina", on_click=conferma_elimina_ric).props("unelevated").style("background: var(--red, #f26a6a); color: #fff;")
                    ui.button("Annulla", on_click=annulla_elimina_ric).props("flat").style("color: var(--txt-mid);")
            confirm_banner_ric.set_visibility(False)


# ---------------------------------------------------------------------------
# 3. Finanziamenti
# ---------------------------------------------------------------------------

def _render_finanziamenti(user_email: str, data: dict) -> None:
    df_fin = data["df_fin"]
    df_mov = data["df_mov"]
    n_fin  = len(df_fin) if not df_fin.empty else 0

    with ui.card().classes("w-full").style(
        "background: var(--bg-card); border: 1px solid var(--bdr); border-radius: 12px; padding: 20px;"
    ):
        with ui.row().classes("items-center justify-between w-full mb-4"):
            ui.html("<span style='font-size:13px;font-weight:700;color:#dde6f5;'>🏦 Finanziamenti</span>")
            ui.html(
                f"<span style='font-size:10px;padding:3px 10px;border-radius:20px;"
                f"background:rgba(79,142,240,0.12);color:#82b4f7;"
                f"border:1px solid rgba(79,142,240,0.28);'>{n_fin} attivi</span>"
            )

        # Form aggiungi
        with ui.grid(columns=3).classes("w-full gap-3"):
            nome_inp  = ui.input("Nome finanziamento").classes("w-full").props("outlined dense")
            nome_inp.style("background: var(--bg-inp); color: var(--txt);")
            cap_inp   = ui.number("Capitale iniziale (€)", value=0.0, step=0.1, format="%.2f").classes("w-full").props("outlined dense")
            cap_inp.style("background: var(--bg-inp); color: var(--txt);")
            taeg_inp  = ui.number("TAEG (%)", value=0.0, step=0.01).classes("w-full").props("outlined dense")
            taeg_inp.style("background: var(--bg-inp); color: var(--txt);")

        with ui.grid(columns=4).classes("w-full gap-3 mt-2"):
            dur_inp     = ui.number("Durata (mesi)", value=12, min=1, step=1).classes("w-full").props("outlined dense")
            dur_inp.style("background: var(--bg-inp); color: var(--txt);")
            data_f_inp  = ui.date(value=date.today().isoformat()).props("outlined dense").classes("w-full")
            data_f_inp.style("background: var(--bg-inp); color: var(--txt);")
            giorno_f    = ui.number("Giorno scadenza", value=1, min=1, max=31, step=1).classes("w-full").props("outlined dense")
            giorno_f.style("background: var(--bg-inp); color: var(--txt);")
            rate_pag    = ui.number("Rate già pagate", value=0, min=0, step=1).classes("w-full").props("outlined dense")
            rate_pag.style("background: var(--bg-inp); color: var(--txt);")

        def salva_finanziamento():
            nome = nome_inp.value.strip()
            cap  = float(cap_inp.value or 0)
            dur  = int(dur_inp.value or 0)
            if not nome or cap <= 0 or dur <= 0:
                ui.notify("Compila nome, capitale e durata.", type="warning")
                return
            try:
                d_inizio = date.fromisoformat(data_f_inp.value) if isinstance(data_f_inp.value, str) else data_f_inp.value
                db.aggiungi_finanziamento(
                    nome, cap, float(taeg_inp.value or 0), dur,
                    d_inizio, int(giorno_f.value or 1),
                    rate_pagate=int(rate_pag.value or 0) or None,
                    user_email=user_email,
                )
                ui.notify("✅ Finanziamento salvato!", type="positive")
                ui.navigate.reload()
            except Exception as exc:
                ui.notify(f"Errore: {exc}", type="negative")

        ui.button("💾 Salva Finanziamento", on_click=salva_finanziamento).props("unelevated").style(
            "background: var(--acc); color: #fff; font-weight: 600; margin-top: 8px;"
        )

        # Lista finanziamenti
        if not df_fin.empty:
            fin_rows_html = _build_fin_table_rows(df_fin, df_mov)
            ui.html(scroll_table(
                title="Elenco finanziamenti", right_html="",
                columns=[("Nome","left"),("Capitale","right"),("TAEG","center"),("Durata","center"),("Rata","right"),("Residuo","right"),("% Compl.","center")],
                widths=[1.8, 1.1, 0.8, 0.8, 1.1, 1.2, 0.9],
                rows_html=fin_rows_html, height_px=260,
            )).classes("w-full mt-3")

            # Elimina finanziamento
            fin_options = {str(row["id"]): f"{row['nome']}" for _, row in df_fin.iterrows()}
            with ui.row().classes("items-end gap-3 mt-3"):
                sel_fin = ui.select(options=fin_options, label="Seleziona finanziamento da eliminare").classes("flex-1").props("outlined dense")
                sel_fin.style("background: var(--bg-inp); color: var(--txt);")

                confirm_fin_banner = ui.element("div").classes("w-full")

                def richiedi_elimina_fin():
                    confirm_fin_banner.set_visibility(True)

                def conferma_elimina_fin():
                    try:
                        db.elimina_finanziamento(int(sel_fin.value), user_email=user_email)
                        ui.notify("✅ Finanziamento eliminato.", type="positive")
                        ui.navigate.reload()
                    except Exception as exc:
                        ui.notify(f"Errore: {exc}", type="negative")

                def annulla_elimina_fin():
                    confirm_fin_banner.set_visibility(False)

                ui.button("🗑️ Elimina", on_click=richiedi_elimina_fin).props("unelevated").style(
                    "background: rgba(242,106,106,0.15); color: #f26a6a; border: 1px solid rgba(242,106,106,0.3);"
                )

            with confirm_fin_banner:
                ui.html("<div style='color: var(--amber); font-size:0.85rem; margin:8px 0;'>⚠️ Operazione irreversibile. Confermi l'eliminazione?</div>")
                with ui.row().classes("gap-3"):
                    ui.button("🗑️ Sì, elimina", on_click=conferma_elimina_fin).props("unelevated").style("background: #f26a6a; color: #fff;")
                    ui.button("Annulla", on_click=annulla_elimina_fin).props("flat").style("color: var(--txt-mid);")
            confirm_fin_banner.set_visibility(False)


def _build_fin_table_rows(df_fin: pd.DataFrame, df_mov: pd.DataFrame) -> list:
    from pages.debiti import _mesi_pagati_da_mov
    rows = []
    for _, f in df_fin.iterrows():
        dati_b  = log.calcolo_finanziamento(f["capitale_iniziale"], f["taeg"], f["durata_mesi"], f["data_inizio"], f["giorno_scadenza"])
        rate_db = int(f["rate_pagate"]) if "rate_pagate" in f.index and pd.notna(f["rate_pagate"]) else None
        rate_mov = _mesi_pagati_da_mov(df_mov, f["nome"], dati_b["rata"], f["data_inizio"])
        rate_cal = int(dati_b.get("mesi_pagati", 0))
        vals     = [v for v in [rate_db, rate_mov, rate_cal] if v is not None]
        rate_eff = max(vals) if vals else None
        dati     = log.calcolo_finanziamento(f["capitale_iniziale"], f["taeg"], f["durata_mesi"], f["data_inizio"], f["giorno_scadenza"], rate_pagate_override=rate_eff)

        taeg_c = "#f5a623" if f["taeg"] > 5 else "#10d98a"
        rows.append(_tr([
            _td(f"<strong>{escape(str(f['nome']))}</strong>", color=Colors.TEXT, weight=600),
            _td(eur2(f["capitale_iniziale"]),   color=Colors.TEXT,  mono=True, align="right"),
            _td(f"{f['taeg']:.2f}%",            color=taeg_c,       mono=True, align="center"),
            _td(str(f["durata_mesi"]),          color=Colors.TEXT_MID, mono=True, align="center"),
            _td(eur2(dati["rata"]),             color=Colors.RED,   mono=True, weight=600, align="right"),
            _td(eur2(dati["debito_residuo"]),   color=Colors.TEXT,  mono=True, align="right"),
            _td(f"{dati['percentuale_completato']:.1f}%",
                color=Colors.GREEN if dati['percentuale_completato'] >= 50 else Colors.AMBER,
                mono=True, align="center"),
        ]))
    return rows


# ---------------------------------------------------------------------------
# 4. Storico Movimenti
# ---------------------------------------------------------------------------

def _render_storico_movimenti(user_email: str, data: dict) -> None:
    df_mov = data["df_mov"]

    with ui.card().classes("w-full").style(
        "background: var(--bg-card); border: 1px solid var(--bdr); border-radius: 12px; padding: 20px;"
    ):
        ui.html("""<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;">
  <span style="font-size:13px;font-weight:700;color:#dde6f5;">📋 Storico Movimenti</span>
</div>""")

        # Filtri
        with ui.grid(columns=3).classes("w-full gap-3 mb-3"):
            tipo_filter = ui.select(
                options={"Tutti": "Tutti", "USCITA": "↑ Uscita", "ENTRATA": "↓ Entrata"},
                value="Tutti", label="Tipo",
            ).classes("w-full").props("outlined dense")
            tipo_filter.style("background: var(--bg-inp); color: var(--txt);")

            categorie_disp = sorted(df_mov["Categoria"].dropna().unique().tolist()) if not df_mov.empty else []
            cat_filter = ui.select(
                options=["Tutti"] + categorie_disp,
                value="Tutti", label="Categoria",
                multiple=True,
            ).classes("w-full").props("outlined dense use-chips")
            cat_filter.style("background: var(--bg-inp); color: var(--txt);")

            anni_disp = ["Tutti"] + [str(a) for a in sorted(df_mov["Data"].dt.year.dropna().unique(), reverse=True)] if not df_mov.empty else ["Tutti"]
            anno_filter = ui.select(options=anni_disp, value="Tutti", label="Anno").classes("w-full").props("outlined dense")
            anno_filter.style("background: var(--bg-inp); color: var(--txt);")

        table_container = ui.element("div").classes("w-full")

        def refresh_table():
            table_container.clear()
            df_reg = df_mov.copy()
            if tipo_filter.value and tipo_filter.value != "Tutti":
                df_reg = df_reg[df_reg["Tipo"] == tipo_filter.value]
            if cat_filter.value and "Tutti" not in (cat_filter.value or []):
                df_reg = df_reg[df_reg["Categoria"].isin(cat_filter.value)]
            if anno_filter.value and anno_filter.value != "Tutti":
                df_reg = df_reg[df_reg["Data"].dt.year == int(anno_filter.value)]

            df_reg = df_reg.copy()
            df_reg.columns = [c.capitalize() for c in df_reg.columns]
            if "Id" not in df_reg.columns and "id" in df_mov.columns:
                df_reg["Id"] = df_mov.loc[df_reg.index, "id"]

            TIPO_COLOR = {"ENTRATA": Colors.GREEN, "USCITA": Colors.RED}
            CAT_COLOR_MAP = {
                "NECESSITÀ":    ("#4f8ef0", "rgba(79,142,240,0.10)", "rgba(79,142,240,0.28)"),
                "SVAGO":        ("#f472b6", "rgba(244,114,182,0.10)", "rgba(244,114,182,0.28)"),
                "INVESTIMENTI": ("#10d98a", "rgba(16,217,138,0.10)", "rgba(16,217,138,0.28)"),
                "ENTRATE":      ("#f5a623", "rgba(245,166,35,0.10)", "rgba(245,166,35,0.28)"),
            }
            mov_rows = []
            for _, row in df_reg.iterrows():
                tipo_v = str(row.get("Tipo", "")).upper()
                cat_v  = str(row.get("Categoria", "")).upper()
                cc, cbg, cbd = CAT_COLOR_MAP.get(cat_v, ("#82b4f7", "rgba(79,142,240,0.10)", "rgba(79,142,240,0.28)"))
                mov_rows.append(_tr([
                    _td(str(row.get("Id", "")),                color=Colors.TEXT_MID, mono=True),
                    _td(str(row.get("Data", ""))[:10],         color=Colors.TEXT_MID, mono=True),
                    _td(tipo_v,                                color=TIPO_COLOR.get(tipo_v, Colors.TEXT), weight=600),
                    _td(chip_html(cat_v, cc, cbg, cbd),        nowrap=False),
                    _td(escape(str(row.get("Dettaglio", ""))), color=Colors.TEXT),
                    _td(format_eur(row.get("Importo", 0), 2),
                        color=Colors.RED if tipo_v == "USCITA" else Colors.GREEN,
                        mono=True, weight=600),
                    _td(escape(str(row.get("Note", ""))),      color=Colors.TEXT_MID),
                ]))

            with table_container:
                ui.html(scroll_table(
                    title="Storico movimenti",
                    right_html=f"{len(df_reg)} righe",
                    columns=[("ID","left"),("Data","left"),("Tipo","left"),("Categoria","left"),("Dettaglio","left"),("Importo","left"),("Note","left")],
                    widths=[0.45, 0.9, 0.9, 1.0, 1.7, 0.95, 1.3],
                    rows_html=mov_rows, height_px=420,
                    empty_message="Nessun movimento trovato con i filtri selezionati.",
                )).classes("w-full")

                # Elimina movimento
                if "Id" in df_reg.columns and not df_reg.empty:
                    def label_mov(mid):
                        rows = df_reg[df_reg.get("Id", pd.Series(dtype=int)) == mid] if "Id" in df_reg.columns else pd.DataFrame()
                        if rows.empty:
                            return str(mid)
                        r = rows.iloc[0]
                        return f"{str(r.get('Data',''))[:10]} | {r.get('Tipo','')} | {r.get('Categoria','')} | {format_eur(r.get('Importo',0), 2)}"

                    mov_id_opts = {str(mid): label_mov(mid) for mid in df_reg["Id"].tolist()}

                    with ui.row().classes("items-end gap-3 mt-3"):
                        sel_mov = ui.select(options=mov_id_opts, label="Seleziona movimento da eliminare").classes("flex-1").props("outlined dense")
                        sel_mov.style("background: var(--bg-inp); color: var(--txt);")

                        confirm_mov_banner = ui.element("div").classes("w-full")

                        def richiedi_elimina_mov():
                            confirm_mov_banner.set_visibility(True)

                        def conferma_elimina_mov():
                            try:
                                db.elimina_movimento(int(sel_mov.value), user_email)
                                ui.notify("✅ Movimento eliminato con successo.", type="positive")
                                ui.navigate.reload()
                            except Exception as exc:
                                ui.notify(f"Errore: {exc}", type="negative")

                        def annulla_elimina_mov():
                            confirm_mov_banner.set_visibility(False)

                        ui.button("🗑️ Elimina", on_click=richiedi_elimina_mov).props("unelevated").style(
                            "background: rgba(242,106,106,0.15); color: #f26a6a; border: 1px solid rgba(242,106,106,0.3);"
                        )

                    with confirm_mov_banner:
                        ui.html("<div style='color: var(--amber); font-size:0.85rem; margin:8px 0;'>⚠️ Operazione irreversibile. Confermi l'eliminazione?</div>")
                        with ui.row().classes("gap-3"):
                            ui.button("🗑️ Sì, elimina", on_click=conferma_elimina_mov).props("unelevated").style("background: #f26a6a; color: #fff;")
                            ui.button("Annulla", on_click=annulla_elimina_mov).props("flat").style("color: var(--txt-mid);")
                    confirm_mov_banner.set_visibility(False)

        tipo_filter.on("update:model-value", lambda: refresh_table())
        cat_filter.on("update:model-value", lambda: refresh_table())
        anno_filter.on("update:model-value", lambda: refresh_table())
        refresh_table()


# ---------------------------------------------------------------------------
# 5. Backup Dati
# ---------------------------------------------------------------------------

def _render_backup(user_email: str) -> None:
    with ui.card().classes("w-full").style(
        "background: var(--bg-card); border: 1px solid var(--bdr); border-radius: 12px; padding: 20px;"
    ):
        ui.html("""<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
  <span style="font-size:19px;font-weight:700;color:#dde6f5;">🗄️ Backup Dati</span>
</div>""")

        ui.html(
            "<div style='font-size:0.90rem;color:#5a6f8c;line-height:1.7;'>"
            "<p style='margin-bottom:4px;'>Scarica una <strong style='color:#dde6f5;'>copia completa</strong> dei tuoi dati in formato SQL.</p>"
            "<p style='margin:0;'>Conservala in un posto sicuro — accessibile anche senza l'app.</p></div>"
        )

        def genera_e_scarica():
            sql = _genera_sql_backup(user_email)
            if not sql:
                ui.notify("Backup non disponibile. Controlla la connessione al database.", type="negative")
                return
            filename = f"personal_budget_backup_{datetime.now().strftime('%Y-%m-%d')}.sql"
            ui.download(sql.encode("utf-8"), filename=filename)

        ui.button("⬇ Scarica backup", on_click=genera_e_scarica).props("unelevated").style(
            "background: var(--acc); color: #fff; font-weight: 600; margin-top: 8px;"
        )


def _genera_sql_backup(user_email: str):
    from backup import genera_sql_per_utente
    db_url = get_secret("DATABASE_URL") or get_secret("DATABASE_URL_POOLER")
    if not db_url:
        return None
    try:
        import psycopg2
        conn   = psycopg2.connect(db_url)
        cursor = conn.cursor()
        sql    = genera_sql_per_utente(cursor, user_email)
        cursor.close()
        conn.close()
        return sql
    except Exception:
        return None