"""
pages/registro.py
-----------------
Tab TRANSAZIONI — Personal Budget Dashboard.

Sezioni:
  1. Nuova Transazione (form inserimento movimento)
  2. Spese Ricorrenti  (form aggiungi + lista + elimina)
  3. Finanziamenti     (form aggiungi + lista + elimina)
  4. Storico Movimenti (filtri + tabella scrollabile + elimina)
  5. Backup Dati       (download SQL on-demand)
"""

import re
from datetime import datetime
from html import escape

import pandas as pd
import streamlit as st

import Database as db
import logiche as log
from utils.constants import Colors, STRUTTURA_CATEGORIE, FREQ_OPTIONS, FREQ_MAP
from utils.formatters import format_eur, chip_html
from utils.html_tables import scroll_table, render_ricorrenti_rows, _td, _tr


# ── Helper: mesi pagati da movimenti (usato nella tabella finanziamenti) ──────

def _mesi_pagati_da_mov(df_m: pd.DataFrame, nome_fin: str, rata=None, data_inizio=None) -> int | None:
    if df_m is None or df_m.empty:
        return None
    raw    = str(nome_fin or "").strip()
    tokens = [raw]
    if "." in raw:
        tokens.append(raw.split(".")[-1])
    tokens.append(re.sub(r"^fin\.?\s*", "", raw, flags=re.I))
    for t in re.split(r"[\s\-_/.]+", raw):
        if len(t.strip()) >= 3:
            tokens.append(t.strip())
    tokens  = list(dict.fromkeys(t for t in tokens if t.strip()))
    pattern = "|".join(re.escape(t) for t in tokens) if tokens else None
    if not pattern:
        return None
    tipo = df_m["Tipo"].astype(str).str.upper().str.strip()
    mask = (tipo == "USCITA") & (
        df_m["Dettaglio"].astype(str).str.contains(pattern, case=False, na=False) |
        df_m["Note"].astype(str).str.contains(pattern, case=False, na=False)
    )
    df_f = df_m[mask].copy()
    if df_f.empty:
        return None
    df_f["Data"] = pd.to_datetime(df_f["Data"], errors="coerce")
    df_f = df_f[df_f["Data"].notna()]
    if data_inizio is not None:
        inizio = pd.to_datetime(data_inizio, errors="coerce")
        if pd.notna(inizio):
            df_f = df_f[df_f["Data"] >= inizio]
    if df_f.empty:
        return None
    rata_abs = abs(float(rata)) if rata is not None else 0.0
    if rata_abs > 0:
        tol  = max(1.0, rata_abs * 0.25)
        df_f = df_f[df_f["Importo"].abs().between(rata_abs - tol, rata_abs + tol)]
    return int(len(df_f)) if not df_f.empty else None


# ══════════════════════════════════════════════════════════════════════════════
# Render principale
# ══════════════════════════════════════════════════════════════════════════════

def render(ctx: dict) -> None:
    user_email       = ctx["user_email"]
    df_mov           = ctx["df_mov"]
    df_fin           = ctx["df_fin"]
    invalidate_cache = ctx["invalidate_cache"]

    st.markdown("<div class='section-title'>TRANSAZIONI</div>", unsafe_allow_html=True)

    # Banner successo post-rerun
    if st.session_state.pop("_banner_mov", False):
        st.success("✅ Movimento registrato con successo!")

    # ── 1. Nuova Transazione ──────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(
            """<div style="display:flex;align-items:center;gap:10px;margin-bottom:18px;">
  <div style="width:28px;height:28px;border-radius:7px;background:rgba(79,142,240,0.12);
              display:flex;align-items:center;justify-content:center;font-size:15px;">💳</div>
  <span style="font-size:13px;font-weight:700;color:#dde6f5;">Nuova Transazione</span>
</div>""",
            unsafe_allow_html=True,
        )
        col_tipo, col_cat, col_det, col_data = st.columns([1, 1, 1.5, 1])
        tipo_inserito    = col_tipo.radio("Tipo movimento", ["↑ Uscita", "↓ Entrata"], horizontal=True, key="reg_tipo_radio")
        tipo_val         = "USCITA" if "Uscita" in tipo_inserito else "ENTRATA"
        categoria_scelta = col_cat.selectbox("Categoria", list(STRUTTURA_CATEGORIE.keys()), key="reg_categoria")
        dettagli_filtrati = STRUTTURA_CATEGORIE[categoria_scelta]
        dettaglio_scelto = col_det.selectbox("Dettaglio", dettagli_filtrati, key="reg_dettaglio")
        data_inserita    = col_data.date_input("Data", datetime.now(), key="reg_data")

        col_imp, col_note = st.columns([1, 3])
        importo_inserito  = col_imp.number_input("Importo (€)", min_value=0.0, step=0.01, format="%.2f", key="reg_importo")
        note_inserite     = col_note.text_input("Note", placeholder="Descrizione opzionale…", key="reg_note")

        col_btn, col_ann, _ = st.columns([1.2, 0.8, 3])
        if col_btn.button("＋ Registra Movimento", key="btn_registra_mov", use_container_width=True, type="primary"):
            if importo_inserito <= 0:
                st.warning("Inserisci un importo maggiore di zero.")
            else:
                try:
                    db.aggiungi_movimento(
                        data_inserita, tipo_val, categoria_scelta, dettaglio_scelto,
                        importo_inserito, note_inserite, user_email=user_email,
                    )
                    invalidate_cache()
                    st.session_state["_banner_mov"] = True
                    for k in ["reg_importo", "reg_note", "reg_data"]:
                        st.session_state.pop(k, None)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Errore salvataggio: {exc}")
        if col_ann.button("Annulla", key="btn_annulla_mov", use_container_width=True):
            for k in ["reg_importo", "reg_note", "reg_data"]:
                st.session_state.pop(k, None)
            st.rerun()

    # ── 2. Spese Ricorrenti ───────────────────────────────────────────────────
    with st.container(border=True):
        df_ric = db.carica_spese_ricorrenti(user_email)
        n_ric  = len(df_ric) if not df_ric.empty else 0
        st.markdown(
            f"""<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
  <span style="font-size:13px;font-weight:700;color:#dde6f5;">🔁 Spese Ricorrenti</span>
  <span style="font-size:10px;padding:3px 10px;border-radius:20px;background:rgba(79,142,240,0.12);
               color:#82b4f7;border:1px solid rgba(79,142,240,0.28);">{n_ric} attive</span>
</div>""",
            unsafe_allow_html=True,
        )

        with st.form("form_spese_ricorrenti", clear_on_submit=False):
            c_desc, c_imp, c_freq = st.columns([2, 1, 1])
            descrizione = c_desc.text_input("Descrizione spesa", key="ric_desc")
            importo_ric = c_imp.number_input("Importo (€)", min_value=0.0, step=0.01, key="ric_importo")
            freq_label  = c_freq.selectbox("Frequenza", list(FREQ_OPTIONS.keys()), key="ric_freq")
            freq_val    = FREQ_OPTIONS[freq_label]

            c_g, c_s, c_e, c_check = st.columns([1, 1, 1, 1])
            giorno_scad = c_g.number_input("Giorno scadenza", 1, 31, 1, 1, key="ric_giorno")
            data_inizio = c_s.date_input("Data inizio", datetime.now(), key="ric_data_inizio")
            senza_fine  = c_check.checkbox("Senza data fine", value=False, key="ric_senza_fine")
            data_fine   = None if senza_fine else c_e.date_input("Data fine", datetime.now(), key="ric_data_fine")

            if st.form_submit_button("＋ Aggiungi Ricorrente"):
                if descrizione and importo_ric > 0:
                    try:
                        db.aggiungi_spesa_ricorrente(
                            descrizione, importo_ric, giorno_scad, freq_val,
                            data_inizio, data_fine, user_email=user_email,
                        )
                        invalidate_cache()
                        st.session_state["_banner_ric"] = True
                        for k in ["ric_desc", "ric_importo", "ric_giorno"]:
                            st.session_state.pop(k, None)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Errore: {exc}")
                else:
                    st.warning("Inserisci descrizione e importo.")

        if st.session_state.pop("_banner_ric", False):
            st.success("✅ Spesa ricorrente salvata!")

        if not df_ric.empty:
            tot_mensile   = df_ric["importo"].sum()
            ric_rows_html = render_ricorrenti_rows(df_ric, FREQ_MAP)
            st.markdown(scroll_table(
                title="Elenco ricorrenti",
                right_html=f"{format_eur(tot_mensile, 2)} / mese",
                columns=[("#","left"),("Descrizione","left"),("Importo","left"),("Frequenza","left"),("Scad.","center"),("Inizio","center"),("Fine","center")],
                widths=[0.45, 2.6, 1.1, 1.25, 0.7, 1.1, 0.9],
                rows_html=ric_rows_html, height_px=320,
            ), unsafe_allow_html=True)

            col_sel, col_btn = st.columns([4, 1], vertical_alignment="bottom")
            ric_id = col_sel.selectbox(
                "Seleziona ricorrente da eliminare",
                df_ric["id"].tolist(),
                format_func=lambda sid: (
                    f"{df_ric.loc[df_ric['id']==sid].iloc[0]['descrizione']} | "
                    f"{format_eur(df_ric.loc[df_ric['id']==sid].iloc[0]['importo'], 2)}"
                    if not df_ric[df_ric["id"]==sid].empty else str(sid)
                ),
                key="sel_del_ric",
            )
            if col_btn.button("🗑️ Elimina", key="btn_del_ric", use_container_width=True):
                st.session_state["pending_delete_ric"] = ric_id

            if st.session_state.get("pending_delete_ric") is not None:
                sid  = st.session_state["pending_delete_ric"]
                desc_vals = df_ric.loc[df_ric["id"] == sid, "descrizione"].values
                desc = desc_vals[0] if len(desc_vals) > 0 else str(sid)
                st.warning(f"⚠️ Elimina **{desc}**? Operazione irreversibile.")
                cc1, cc2 = st.columns(2)
                if cc1.button("🗑️ Sì, elimina", key="confirm_del_ric", use_container_width=True, type="primary"):
                    db.elimina_spesa_ricorrente(sid, user_email=user_email)
                    invalidate_cache()
                    del st.session_state["pending_delete_ric"]
                    st.session_state["_success_ric_ts"] = datetime.now().timestamp()
                    st.rerun()
                if cc2.button("Annulla", key="cancel_del_ric", use_container_width=True):
                    del st.session_state["pending_delete_ric"]
                    st.rerun()

            if "_success_ric_ts" in st.session_state:
                if datetime.now().timestamp() - st.session_state["_success_ric_ts"] < 3:
                    st.success("✅ Spesa ricorrente eliminata.")
                else:
                    del st.session_state["_success_ric_ts"]

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # ── 3. Finanziamenti ──────────────────────────────────────────────────────
    with st.container(border=True):
        n_fin = len(df_fin) if not df_fin.empty else 0
        st.markdown(
            f"""<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
  <span style="font-size:13px;font-weight:700;color:#dde6f5;">🏦 Finanziamenti</span>
  <span style="font-size:10px;padding:3px 10px;border-radius:20px;background:rgba(79,142,240,0.12);
               color:#82b4f7;border:1px solid rgba(79,142,240,0.28);">{n_fin} attivi</span>
</div>""",
            unsafe_allow_html=True,
        )

        with st.form("form_finanziamento", clear_on_submit=False):
            c1, c2, c3 = st.columns(3)
            nome_fin  = c1.text_input("Nome finanziamento", key="fin_nome")
            capitale  = c2.number_input("Capitale iniziale (€)", 0.0, step=0.1, format="%.2f", key="fin_capitale")
            taeg      = c3.number_input("TAEG (%)", 0.0, step=0.01, key="fin_taeg")
            c4, c5, c6, c7 = st.columns(4)
            durata          = c4.number_input("Durata (mesi)", 1, step=1, key="fin_durata")
            data_inizio_fin = c5.date_input("Data inizio", key="fin_data_inizio")
            giorno_fin      = c6.number_input("Giorno scadenza", 1, 31, 1, 1, key="fin_giorno")
            rate_gia_pag    = c7.number_input("Rate già pagate", 0, step=1, value=0, key="fin_rate")

            if st.form_submit_button("💾 Salva Finanziamento"):
                if nome_fin and capitale > 0 and durata > 0:
                    try:
                        db.aggiungi_finanziamento(
                            nome_fin, capitale, taeg, durata, data_inizio_fin,
                            giorno_fin, rate_pagate=int(rate_gia_pag) or None,
                            user_email=user_email,
                        )
                        invalidate_cache()
                        for k in ["fin_nome", "fin_capitale", "fin_taeg", "fin_durata", "fin_rate", "fin_giorno"]:
                            st.session_state.pop(k, None)
                        st.success("✅ Finanziamento salvato!")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Errore: {exc}")
                else:
                    st.warning("Compila nome, capitale e durata.")

        # Tabella finanziamenti esistenti
        if not df_fin.empty:
            fin_rows_html = []
            for _, f in df_fin.iterrows():
                dati_b   = log.calcolo_finanziamento(
                    f["capitale_iniziale"], f["taeg"], f["durata_mesi"],
                    f["data_inizio"], f["giorno_scadenza"],
                )
                rate_db  = int(f["rate_pagate"]) if "rate_pagate" in f.index and pd.notna(f["rate_pagate"]) else None
                rate_mov = _mesi_pagati_da_mov(df_mov, f["nome"], dati_b["rata"], f["data_inizio"])
                rate_cal = int(dati_b.get("mesi_pagati", 0))
                vals_r   = [v for v in [rate_db, rate_mov, rate_cal] if v is not None]
                rate_eff = max(vals_r) if vals_r else None

                taeg_pct = f["taeg"]
                taeg_c, taeg_bg, taeg_bd = (
                    ("#f5a623", "rgba(245,166,35,0.10)", "rgba(245,166,35,0.26)") if taeg_pct > 5
                    else ("#10d98a", "rgba(16,217,138,0.10)", "rgba(16,217,138,0.26)")
                )
                fin_rows_html.append(_tr([
                    _td(f"<strong>{escape(str(f['nome']))}</strong>", color=Colors.TEXT, weight=600),
                    _td(format_eur(f["capitale_iniziale"], 0), color=Colors.TEXT, mono=True),
                    _td(chip_html(f"{taeg_pct:.2f}%", taeg_c, taeg_bg, taeg_bd), nowrap=False),
                    _td(f"{int(f['durata_mesi'])}m",         color=Colors.TEXT_MID, mono=True, align="center"),
                    _td(str(f["data_inizio"])[:10],          color=Colors.TEXT_MID, mono=True, align="center"),
                    _td(format_eur(dati_b["rata"], 2),       color=Colors.RED,      mono=True, weight=600),
                    _td(str(rate_eff or 0),                  color=Colors.TEXT_MID, mono=True, align="center"),
                ]))

            try:
                totale_rate = sum(
                    log.calcolo_finanziamento(
                        r["capitale_iniziale"], r["taeg"], r["durata_mesi"],
                        r["data_inizio"], r["giorno_scadenza"],
                    )["rata"]
                    for _, r in df_fin.iterrows()
                )
                right_fin = f"{format_eur(totale_rate, 2)} / mese"
            except Exception:
                right_fin = ""

            st.markdown(scroll_table(
                title="Finanziamenti in corso", right_html=right_fin,
                columns=[("Nome","left"),("Capitale","left"),("TAEG","left"),("Durata","center"),("Inizio","center"),("Rata","left"),("Rate pag.","center")],
                widths=[1.8, 1.2, 0.9, 0.8, 1.1, 1.1, 0.9],
                rows_html=fin_rows_html, height_px=280,
            ), unsafe_allow_html=True)

            col_sel_fin, col_btn_fin = st.columns([4, 1], vertical_alignment="bottom")
            fin_nome = col_sel_fin.selectbox(
                "Seleziona finanziamento da eliminare",
                df_fin["nome"].tolist(),
                format_func=lambda n: (
                    f"{n} | {format_eur(df_fin.loc[df_fin['nome']==n].iloc[0]['capitale_iniziale'], 0)}"
                    if not df_fin[df_fin["nome"]==n].empty else str(n)
                ),
                key="sel_del_fin",
            )
            if col_btn_fin.button("🗑️ Elimina", key="btn_del_fin", use_container_width=True):
                st.session_state["pending_delete_fin"] = fin_nome

            if st.session_state.get("pending_delete_fin") is not None:
                fnome = st.session_state["pending_delete_fin"]
                st.warning(f"⚠️ Elimina **{fnome}**? Operazione irreversibile.")
                cc1, cc2 = st.columns(2)
                if cc1.button("🗑️ Sì, elimina", key="confirm_del_fin", use_container_width=True, type="primary"):
                    db.elimina_finanziamento(fnome, user_email=user_email)
                    invalidate_cache()
                    del st.session_state["pending_delete_fin"]
                    st.session_state["_success_fin_ts"] = datetime.now().timestamp()
                    st.rerun()
                if cc2.button("Annulla", key="cancel_del_fin", use_container_width=True):
                    del st.session_state["pending_delete_fin"]
                    st.rerun()

            if "_success_fin_ts" in st.session_state:
                if datetime.now().timestamp() - st.session_state["_success_fin_ts"] < 3:
                    st.success("✅ Finanziamento eliminato.")
                else:
                    del st.session_state["_success_fin_ts"]

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # ── 4. Storico Movimenti ──────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(
            """<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;">
  <span style="font-size:13px;font-weight:700;color:#dde6f5;">📋 Storico Movimenti</span>
</div>""",
            unsafe_allow_html=True,
        )

        col_ft, col_fc, col_fa = st.columns([1.2, 2, 1])
        filtro_tipo = col_ft.radio("Tipo", ["Tutti", "↑ Uscita", "↓ Entrata"], horizontal=True, key="reg_filtro_tipo")
        categorie_disp = sorted(df_mov["Categoria"].dropna().unique().tolist()) if not df_mov.empty else []
        filtro_cat  = col_fc.multiselect("Categoria", categorie_disp, key="reg_filtro_cat")
        filtro_anno = (
            col_fa.selectbox(
                "Anno",
                ["Tutti"] + [str(a) for a in sorted(df_mov["Data"].dt.year.dropna().unique(), reverse=True)],
                key="reg_filtro_anno",
            )
            if not df_mov.empty else "Tutti"
        )

        df_reg = df_mov.copy()
        if filtro_tipo != "Tutti":
            tipo_f = "USCITA" if "Uscita" in filtro_tipo else "ENTRATA"
            df_reg = df_reg[df_reg["Tipo"] == tipo_f]
        if filtro_cat:
            df_reg = df_reg[df_reg["Categoria"].isin(filtro_cat)]
        if filtro_anno != "Tutti":
            df_reg = df_reg[df_reg["Data"].dt.year == int(filtro_anno)]

        df_reg.columns = [c.capitalize() for c in df_reg.columns]
        if "Id" not in df_reg.columns and "id" in df_mov.columns:
            df_reg["Id"] = df_mov.loc[df_reg.index, "id"]

        TIPO_COLOR = {"ENTRATA": Colors.GREEN, "USCITA": Colors.RED}
        CAT_COLOR  = {
            "NECESSITÀ":    ("#4f8ef0",  "rgba(79,142,240,0.10)",  "rgba(79,142,240,0.28)"),
            "SVAGO":        ("#f472b6",  "rgba(244,114,182,0.10)", "rgba(244,114,182,0.28)"),
            "INVESTIMENTI": ("#10d98a",  "rgba(16,217,138,0.10)",  "rgba(16,217,138,0.28)"),
            "ENTRATE":      ("#f5a623",  "rgba(245,166,35,0.10)",  "rgba(245,166,35,0.28)"),
        }

        def _label_mov(mid):
            if "Id" not in df_reg.columns:
                return str(mid)
            rows = df_reg[df_reg["Id"] == mid]
            if rows.empty:
                return str(mid)
            r = rows.iloc[0]
            return f"{str(r.get('Data',''))[:10]} | {r.get('Tipo','')} | {r.get('Categoria','')} | {format_eur(r.get('Importo',0), 2)}"

        mov_rows_html = []
        for _, row in df_reg.iterrows():
            tipo_v = str(row.get("Tipo", "")).upper()
            cat_v  = str(row.get("Categoria", "")).upper()
            cc, cbg, cbd = CAT_COLOR.get(cat_v, ("#82b4f7", "rgba(79,142,240,0.10)", "rgba(79,142,240,0.28)"))
            mov_rows_html.append(_tr([
                _td(str(row.get("Id", "")),             color=Colors.TEXT_MID, mono=True),
                _td(str(row.get("Data", ""))[:10],      color=Colors.TEXT_MID, mono=True),
                _td(tipo_v,                              color=TIPO_COLOR.get(tipo_v, Colors.TEXT), weight=600),
                _td(chip_html(cat_v, cc, cbg, cbd),     nowrap=False),
                _td(escape(str(row.get("Dettaglio", ""))), color=Colors.TEXT),
                _td(format_eur(row.get("Importo", 0), 2),
                    color=Colors.RED if tipo_v == "USCITA" else Colors.GREEN, mono=True, weight=600),
                _td(escape(str(row.get("Note", ""))),   color=Colors.TEXT_MID),
            ]))

        st.markdown(scroll_table(
            title="Storico movimenti",
            right_html=f"{len(df_reg)} righe",
            columns=[("ID","left"),("Data","left"),("Tipo","left"),("Categoria","left"),
                     ("Dettaglio","left"),("Importo","left"),("Note","left")],
            widths=[0.45, 0.9, 0.9, 1.0, 1.7, 0.95, 1.3],
            rows_html=mov_rows_html, height_px=420,
            empty_message="Nessun movimento trovato con i filtri selezionati.",
        ), unsafe_allow_html=True)

        if "Id" in df_reg.columns and not df_reg.empty:
            col_sm, col_bm = st.columns([4, 1], vertical_alignment="bottom")
            mov_id = col_sm.selectbox(
                "Seleziona movimento da eliminare",
                df_reg["Id"].tolist(),
                format_func=_label_mov,
                key="sel_del_mov",
            )
            if col_bm.button("🗑️ Elimina", key="btn_del_mov", use_container_width=True):
                st.session_state["pending_delete_mov"] = mov_id

        if st.session_state.get("pending_delete_mov") is not None:
            mid = st.session_state["pending_delete_mov"]
            st.warning(f"⚠️ Stai per eliminare il movimento **{_label_mov(mid)}**. Operazione irreversibile.")
            cc1, cc2 = st.columns(2)
            if cc1.button("🗑️ Sì, elimina", key="confirm_del_mov", use_container_width=True, type="primary"):
                db.elimina_movimento(mid, user_email)
                invalidate_cache()
                del st.session_state["pending_delete_mov"]
                st.session_state["_success_mov_ts"] = datetime.now().timestamp()
                st.rerun()
            if cc2.button("Annulla", key="cancel_del_mov", use_container_width=True):
                del st.session_state["pending_delete_mov"]
                st.rerun()

        if "_success_mov_ts" in st.session_state:
            if datetime.now().timestamp() - st.session_state["_success_mov_ts"] < 3:
                st.success("✅ Movimento eliminato con successo.")
            else:
                del st.session_state["_success_mov_ts"]

    # ── 5. Backup Dati ────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(
            """<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
  <span style="font-size:19px;font-weight:700;color:#dde6f5;">🗄️ Backup Dati</span>
</div>""",
            unsafe_allow_html=True,
        )

        @st.cache_data(ttl=0, show_spinner=False)
        def _genera_sql_backup(email: str) -> str | None:
            from backup import genera_sql_per_utente
            from config_runtime import get_secret
            db_url = get_secret("DATABASE_URL") or get_secret("DATABASE_URL_POOLER")
            if not db_url:
                return None
            try:
                import psycopg2
                conn   = psycopg2.connect(db_url)
                cursor = conn.cursor()
                sql    = genera_sql_per_utente(cursor, email)
                cursor.close()
                conn.close()
                return sql
            except Exception:
                return None

        sql_backup = _genera_sql_backup(user_email)
        col_txt, col_btn = st.columns([3, 1], vertical_alignment="bottom")
        col_txt.markdown(
            "<div style='font-size:0.90rem;color:#5a6f8c;line-height:1.7;'>"
            "<p style='margin-bottom:4px;'>Scarica una <strong style='color:#dde6f5;'>copia completa</strong>"
            " dei tuoi dati in formato SQL.</p>"
            "<p style='margin:0;'>Conservala in un posto sicuro — accessibile anche senza l'app.</p></div>",
            unsafe_allow_html=True,
        )
        if sql_backup:
            col_btn.download_button(
                label="⬇ Scarica backup",
                data=sql_backup.encode("utf-8"),
                file_name=f"personal_budget_backup_{datetime.now().strftime('%Y-%m-%d')}.sql",
                mime="text/plain",
                use_container_width=True,
            )
        else:
            col_btn.caption("Backup non disponibile (DATABASE_URL mancante).")
