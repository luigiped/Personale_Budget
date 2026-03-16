import pandas as pd
import numpy as np
import streamlit as st
from datetime import date, datetime
import numpy_financial as npf
from dateutil.relativedelta import relativedelta
import yfinance as yf
import calendar
import math

# Standardizzazione valori tipo movimento
TIPO_ENTRATA = "ENTRATA"
TIPO_USCITA = "USCITA"

def _norm_tipo(series):
    """Normalizza i valori della colonna Tipo per confronto robusto."""
    s = series.astype(str).str.upper().str.strip()
    # Retrocompatibilita con dataset storici: alcuni file usano il plurale.
    return s.replace({
        "ENTRATE": TIPO_ENTRATA,
        "USCITE": TIPO_USCITA,
    })

# Definizione della gerarchia Categorie -> Dettagli
STRUTTURA_CATEGORIE = {
    "NECESSITÀ": [
        "Affitto",
        "Mutuo",
        "Auto",
        "Moto",
        "Bollette (Luce/Gas/Internet)",
        "Trasporti/Benzina",
        "Salute",
        "Assicurazioni",
        "Imposta di bollo",
    ],

    "SVAGO": [
        "Ristoranti/Bar",
        "Viaggi/Hotel",
        "Gite fuori porta",
        "Abbonamenti (Netflix, ecc.)",
        "Shopping Personale",
        "Regali",
        "Palestra",
        "Altro",
        "Carta di credito",
    ],

    "INVESTIMENTI": [
        "PAC",
        "Fondo Pensione",
    ],

    "ENTRATE": [
        "Stipendio",
        "Extra",
    ]   
}

# Definizione delle colonne del tuo Dataset (come nel tuo Google Sheet)
COLONNE_DATASET = [
    "Data", 
    "Tipo (Entrata/Uscita)", 
    "Categoria", 
    "Dettaglio Spesa", 
    "Importo", 
    "Note"
]

# Percentuali di budget secondo la regola 50/30/20
PERCENTUALI_BUDGET = {
    "NECESSITÀ": 0.5,
    "SVAGO": 0.3,
    "INVESTIMENTI": 0.2
}

#Regola determinazione budget mensile
def budget_mensile(stipendio):
    # Applica la regola 50/30/20
    necessità = stipendio * 0.5
    svago = stipendio * 0.3
    investimenti = stipendio * 0.2

    return { #mi restituisce il budget mensile per le categorie
        "NECESSITÀ": necessità, 
        "SVAGO": svago, 
        "INVESTIMENTI": investimenti
    }

def calcola_avanzamento_budget(totale_entrate, df_uscite_mese):
    # 1. Calcoliamo quanto abbiamo speso finora per ogni categoria
    if df_uscite_mese.empty:
        spese_per_categoria = {}
    else:
        # Raggruppa per 'Categoria' e somma 'Importo'
        spese_per_categoria = df_uscite_mese.groupby('Categoria')['Importo'].sum().to_dict()

    risultati_budget = {}

    # 2. Per ogni categoria (Necessità, Svago, Inv), applichiamo la logica
    for categoria, percentuale in PERCENTUALI_BUDGET.items():
        
        # A. Calcolo il Budget Teorico (Il tetto massimo)
        budget_disponibile = totale_entrate * percentuale
        
        # B. Recupero quanto ho speso (0 se non ho ancora speso nulla)
        spesa_reale = spese_per_categoria.get(categoria, 0.0)
        
        # C. Calcolo il residuo
        residuo = budget_disponibile - spesa_reale
        
        # D. Calcolo la percentuale di riempimento della barra
        #    (Gestiamo il caso di divisione per zero se non ci sono entrate)
        if budget_disponibile > 0:
            perc_avanzamento = (spesa_reale / budget_disponibile) * 100
        else:
            perc_avanzamento = 0.0
            
        # Strutturiamo i dati per l'interfaccia
        risultati_budget[categoria] = {
            "Budget Totale": round(budget_disponibile, 2),
            "Speso": round(spesa_reale, 2),
            "Residuo": round(residuo, 2),
            "Percentuale": round(perc_avanzamento, 1), # Es. 45.5%
            "Status": "Alert" if spesa_reale > budget_disponibile else "Ok"
        }

    return risultati_budget
#logica per grafico andamento spese mensili
def dettaglio_spese(df_uscite_mese):
    if df_uscite_mese.empty:
        return pd.DataFrame(columns=['Dettaglio', 'Importo'])

    # Raggruppiamo per la colonna "Dettaglio"
    df_dettaglio = df_uscite_mese.groupby('Dettaglio')['Importo'].sum().reset_index()
    
    # Ordiniamo dal più caro al meno caro (come spesso si fa nei grafici)
    df_dettaglio = df_dettaglio.sort_values(by='Importo', ascending=False)
    
    return df_dettaglio

#calcolo per spese ricorrenti
def _safe_day_for_month(anno, mese, giorno):
    """Adatta il giorno al massimo consentito nel mese (es. 31 -> 28/29 a febbraio)."""
    try:
        g = int(giorno)
    except Exception:
        g = 1
    g = max(1, g)
    return min(g, calendar.monthrange(int(anno), int(mese))[1])


def _to_int_default(value, default=0):
    try:
        if pd.isna(value):
            return int(default)
    except Exception:
        pass
    try:
        return int(value)
    except Exception:
        return int(default)


def _to_float_default(value, default=0.0):
    try:
        if pd.isna(value):
            return float(default)
    except Exception:
        pass
    try:
        return float(value)
    except Exception:
        return float(default)


def _label_frequenza_mesi(freq_mesi):
    freq = max(1, _to_int_default(freq_mesi, 1))
    mapping = {
        1: "Mensile",
        2: "Bimestrale",
        3: "Trimestrale",
        4: "Quadrimestrale",
        6: "Semestrale",
        12: "Annuale",
    }
    return mapping.get(freq, f"Ogni {freq} mesi")


def _col_or_empty(df, nome):
    if nome in df.columns:
        return df[nome].astype(str)
    return pd.Series("", index=df.index, dtype="object")


def _prepare_movimenti_lookup(df_movimenti):
    """Normalizza una sola volta i campi usati per matching pagamenti."""
    if df_movimenti is None or df_movimenti.empty:
        return pd.DataFrame()

    df = df_movimenti.copy()
    if "Data" not in df.columns:
        return pd.DataFrame()
    if not pd.api.types.is_datetime64_any_dtype(df["Data"]):
        df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df[df["Data"].notna()].copy()
    if df.empty:
        return df

    df["_tipo_norm"] = _norm_tipo(df["Tipo"]) if "Tipo" in df.columns else pd.Series("", index=df.index)
    df["_dettaglio_txt"] = _col_or_empty(df, "Dettaglio")
    df["_note_txt"] = _col_or_empty(df, "Note")
    df["_categoria_txt"] = _col_or_empty(df, "Categoria")
    if "Importo" in df.columns:
        df["_importo_abs"] = pd.to_numeric(df["Importo"], errors="coerce").abs()
    else:
        df["_importo_abs"] = pd.Series(np.nan, index=df.index)
    return df


def _movimento_pagato(df_movimenti, mese, anno, descrizione, importo_atteso=None, prepared=False):
    """
    Determina se una spesa risulta pagata nel mese/anno cercando descrizione in
    dettaglio o note, limitando a movimenti di uscita.
    """
    if df_movimenti is None or df_movimenti.empty:
        return False

    df = df_movimenti if prepared else _prepare_movimenti_lookup(df_movimenti)
    if df.empty:
        return False

    tipo = df["_tipo_norm"] if "_tipo_norm" in df.columns else (_norm_tipo(df["Tipo"]) if "Tipo" in df.columns else pd.Series("", index=df.index))
    dettaglio = df["_dettaglio_txt"] if "_dettaglio_txt" in df.columns else _col_or_empty(df, "Dettaglio")
    note = df["_note_txt"] if "_note_txt" in df.columns else _col_or_empty(df, "Note")
    categoria = df["_categoria_txt"] if "_categoria_txt" in df.columns else _col_or_empty(df, "Categoria")

    token = str(descrizione or "").strip()
    if not token:
        return False

    mask = (
        (tipo == TIPO_USCITA) &
        (df["Data"].dt.month == int(mese)) &
        (df["Data"].dt.year == int(anno)) &
        (
            dettaglio.str.contains(token, case=False, na=False, regex=False) |
            note.str.contains(token, case=False, na=False, regex=False) |
            categoria.str.contains(token, case=False, na=False, regex=False)
        )
    )

    if importo_atteso is not None:
        if "_importo_abs" in df.columns:
            imp = df["_importo_abs"]
        elif "Importo" in df.columns:
            imp = pd.to_numeric(df["Importo"], errors="coerce").abs()
        else:
            imp = pd.Series(np.nan, index=df.index)
        target = abs(float(importo_atteso))
        # Match importo più stretto: l'importo deve corrispondere (tolleranza minima tecnica).
        tol = max(0.50, target * 0.02)
        mask = mask & imp.between(target - tol, target + tol)

    return bool(mask.any())


def calcola_calendario_spese(df_ricorrenti, df_movimenti, mese, anno):
    """
    Genera il calendario delle sole spese ricorrenti per il mese specificato.

    Anche qui applichiamo l'etichetta "⚠️ IN SCADENZA" per spese non ancora
    pagate la cui data cade nei prossimi due giorni.
    """
    lista_spese = []
    if df_ricorrenti is None or df_ricorrenti.empty:
        return pd.DataFrame(columns=["Spesa", "Importo", "Data", "Stato"])
    df_mov_lookup = _prepare_movimenti_lookup(df_movimenti)

    oggi = date.today()
    alert_window_days = 2

    for _, ric in df_ricorrenti.iterrows():
        importo = float(ric.get("Importo", 0) or 0)
        if importo <= 0:
            continue

        descr = ric.get("Descrizione", ric.get("descrizione", ""))
        giorno = _safe_day_for_month(anno, mese, ric.get("Giorno Scadenza", ric.get("giorno_scadenza", 1)))
        stato = "✅ PAGATO" if _movimento_pagato(
            df_mov_lookup, mese, anno, descr, importo_atteso=importo, prepared=True
        ) else "❌ DA PAGARE"
        if stato.startswith("❌"):
            dt = date(int(anno), int(mese), int(giorno))
            giorni_diff = (dt - oggi).days
            if 0 <= giorni_diff <= alert_window_days:
                stato = "⚠️ IN SCADENZA"

        lista_spese.append({
            "Spesa": descr,
            "Importo": importo,
            "Data": date(int(anno), int(mese), int(giorno)),
            "Stato": stato,
        })

    if not lista_spese:
        return pd.DataFrame(columns=["Spesa", "Importo", "Data", "Stato"])
    return pd.DataFrame(lista_spese).sort_values(by="Data")
# logiche.py (Integrazione Finanziamenti)

def calcolo_spese_ricorrenti(df_ricorrenti, df_finanziamenti, df_movimenti, mese, anno):
    """
    Versione corretta: calcola rata e debito residuo dinamicamente 
    per evitare errori di colonne mancanti.

    Aggiungiamo qui un piccolo calcolo aggiuntivo: se una spesa NON risulta
    ancora pagata ma la sua data prevista cade entro i prossimi 2 giorni
    (finestra usata anche per gli alert), lo stato viene marcato come
    "⚠️ IN SCADENZA".  In questo modo la tabella di calendario mostrerà
    una riga gialla, oltre ai classici pagato/da pagare.
    """
    # Normalizza input mese/anno (arrivano talvolta come numpy scalar/float).
    mese = _to_int_default(mese, datetime.now().month)
    anno = _to_int_default(anno, datetime.now().year)
    mese = min(max(mese, 1), 12)

    oggi = date.today()
    alert_window_days = 2  # identico a quanto usato nelle alert in interfaccia

    if df_ricorrenti is None:
        df_ricorrenti = pd.DataFrame()
    if df_movimenti is None:
        df_movimenti = pd.DataFrame()

    # 1. Normalizziamo una sola volta le colonne usate nei match.
    df_mov_lookup = _prepare_movimenti_lookup(df_movimenti)

    # 2. Generiamo le scadenze dalle spese ricorrenti (se presenti)
    lista_totale = []
    
    if not df_ricorrenti.empty:
        for _, ric in df_ricorrenti.iterrows():
            importo = float(ric.get('Importo', 0) or 0)
            if importo <= 0:
                continue

            freq = max(1, _to_int_default(ric.get('Frequenza', ric.get('frequenza_mesi', 1)), 1))
            giorno = max(1, _to_int_default(ric.get('Giorno Scadenza', ric.get('giorno_scadenza', 1)), 1))
            data_inizio = ric.get('Data Inizio', ric.get('data_inizio'))
            data_fine = ric.get('Data Fine', ric.get('data_fine'))

            # Normalizziamo date
            data_inizio = pd.to_datetime(data_inizio, errors='coerce') if pd.notna(data_inizio) else None
            data_fine = pd.to_datetime(data_fine, errors='coerce') if pd.notna(data_fine) else None

            mese_diff = 0
            if data_inizio is not None and not pd.isna(data_inizio):
                mese_diff = (anno - data_inizio.year) * 12 + (mese - data_inizio.month)
                if mese_diff < 0:
                    continue
                if data_fine is not None and not pd.isna(data_fine):
                    if date(anno, mese, 1) > data_fine.date():
                        continue
                if freq > 1 and (mese_diff % freq) != 0:
                    continue

            giorno_eff = _safe_day_for_month(anno, mese, giorno)
            descrizione = str(ric.get('Descrizione', ric.get('descrizione', '')))
            # determinazione stato originaria
            stato = "✅ PAGATO" if _movimento_pagato(
                df_mov_lookup,
                mese,
                anno,
                descrizione,
                importo_atteso=importo,
                prepared=True,
            ) else "❌ DA PAGARE"
            # se ancora da pagare e la scadenza è vicina, mettiamo in scadenza
            if stato.startswith("❌"):
                data_prevista = date(anno, mese, giorno_eff)
                giorni_diff = (data_prevista - oggi).days
                if 0 <= giorni_diff <= alert_window_days:
                    stato = "⚠️ IN SCADENZA"
            lista_totale.append({
                "Spesa": descrizione,
                "Importo": importo,
                "Data": date(anno, mese, giorno_eff),
                "Stato": stato,
                "Origine": "Ricorrente",
                "Giorno Previsto": int(giorno_eff),
                "Data Fine Prevista": (data_fine.date() if data_fine is not None and not pd.isna(data_fine) else None),
                "Frequenza": _label_frequenza_mesi(freq),
            })
    
    # 3. Generiamo le scadenze dai finanziamenti calcolando i valori
    if df_finanziamenti is None:
        df_finanziamenti = pd.DataFrame()

    for _, fin in df_finanziamenti.iterrows():
        nome_fin = fin.get('Nome Finanziamento', fin.get('nome', ''))
        capitale = fin.get('Capitale', fin.get('capitale_iniziale', 0))
        taeg = fin.get('TAEG', fin.get('taeg', 0))
        durata = fin.get('Durata', fin.get('durata_mesi', 0))
        data_inizio = fin.get('Data Inizio', fin.get('data_inizio'))
        giorno_scad = fin.get('Giorno Scadenza', fin.get('giorno_scadenza', 1))
        rate_pagate = fin.get('Rate Pagate', fin.get('rate_pagate'))
        durata = _to_int_default(durata, 0)

        # Calcoliamo i dati del finanziamento usando i dati presenti nel DB
        dati_f = calcolo_finanziamento(
            capitale,
            taeg,
            durata,
            data_inizio,
            giorno_scad,
            rate_pagate_override=rate_pagate,
        )
        
        # Procediamo solo se il debito residuo è maggiore di zero
        if dati_f['debito_residuo'] > 0:
            stato = "✅ PAGATO" if _movimento_pagato(
                df_mov_lookup,
                mese,
                anno,
                nome_fin,
                importo_atteso=dati_f['rata'],
                prepared=True,
            ) else "❌ DA PAGARE"
            giorno_eff_fin = _safe_day_for_month(anno, mese, giorno_scad)

            # Data fine prevista finanziamento calcolata da data inizio + durata.
            data_fine_prevista_fin = None
            inizio_fin = pd.to_datetime(data_inizio, errors='coerce')
            if pd.notna(inizio_fin) and durata > 0:
                fine_fin = inizio_fin + relativedelta(months=durata - 1)
                giorno_fine = _safe_day_for_month(fine_fin.year, fine_fin.month, giorno_scad)
                data_fine_prevista_fin = date(int(fine_fin.year), int(fine_fin.month), int(giorno_fine))
            
            lista_totale.append({
                "Spesa": nome_fin,
                "Importo": dati_f['rata'], # Rata calcolata dinamicamente
                "Data": date(anno, mese, giorno_eff_fin),
                "Stato": stato,
                "Origine": "Finanziamento",
                "Giorno Previsto": int(giorno_eff_fin),
                "Data Fine Prevista": data_fine_prevista_fin,
                "Frequenza": "Mensile",
            })
            
    if not lista_totale:
        return pd.DataFrame(
            columns=[
                "Spesa",
                "Importo",
                "Data",
                "Stato",
                "Origine",
                "Giorno Previsto",
                "Data Fine Prevista",
                "Frequenza",
            ]
        )
        
    df_risultato = pd.DataFrame(lista_totale)
    
    # 3. Ordinamento per Data (come nel tuo Sheet)
    return df_risultato.sort_values(by="Data")


def alert_scadenze_ricorrenti(df_scadenze, giorni_preavviso=1, oggi=None):
    """
    Restituisce le scadenze ricorrenti non pagate che scadono entro N giorni.
    """
    empty_cols = ["Spesa", "Importo", "Data", "Stato", "Origine", "Giorni Alla Scadenza"]

    def _empty():
        return pd.DataFrame(columns=empty_cols)

    if df_scadenze is None or df_scadenze.empty:
        return _empty()

    if oggi is None:
        oggi = date.today()

    giorni_preavviso = max(1, _to_int_default(giorni_preavviso, 1))
    df = df_scadenze.copy()
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df[df["Data"].notna()].copy()
    if df.empty:
        return _empty()

    if "Origine" in df.columns:
        df = df[df["Origine"].astype(str).str.upper() == "RICORRENTE"].copy()
    if df.empty:
        return _empty()

    stato = df["Stato"].astype(str)
    df = df[stato.str.contains("DA PAGARE", case=False, na=False)].copy()
    if df.empty:
        return _empty()

    df["Giorni Alla Scadenza"] = (df["Data"].dt.date - oggi).apply(lambda x: x.days)
    df = df[(df["Giorni Alla Scadenza"] >= 0) & (df["Giorni Alla Scadenza"] <= giorni_preavviso)].copy()
    if df.empty:
        return _empty()

    return df.sort_values(by=["Data", "Spesa"])

#logica per calcolo finanziamenti

def calcolo_finanziamento(
    capitale,
    taeg,
    durata_mesi,
    data_inizio,
    giorno_scadenza=None,
    rate_pagate_override=None,
):
    capitale = _to_float_default(capitale, 0.0)
    durata_mesi = _to_int_default(durata_mesi, 0)
    taeg = _to_float_default(taeg, 0.0)

    if capitale <= 0 or durata_mesi <= 0:
        return {
            "rata": 0.0,
            "mesi_rimanenti": 0,
            "mesi_pagati": 0,
            "interessi_pagati": 0.0,
            "interessi_totali": 0.0,
            "interessi_residui": 0.0,
            "debito_residuo": 0.0,
            "capitale_pagato": 0.0,
            "percentuale_completato": 0.0,
        }

    tasso_mensile = (taeg / 100.0) / 12.0

    # 1. Calcolo rata
    if abs(tasso_mensile) < 1e-12:
        rata = capitale / durata_mesi
    else:
        rata = float(npf.pmt(tasso_mensile, durata_mesi, -capitale))

    # 2. Determiniamo quanti mesi sono passati dalla data_inizio a oggi
    oggi = datetime.now().date()
    inizio = pd.to_datetime(data_inizio, errors="coerce")
    if pd.isna(inizio):
        inizio = pd.Timestamp(oggi)
    inizio = inizio.date()

    if giorno_scadenza is None or pd.isna(giorno_scadenza) or _to_int_default(giorno_scadenza, 0) <= 0:
        giorno_scadenza = inizio.day
    giorno_scadenza = _to_int_default(giorno_scadenza, inizio.day)

    def _safe_day(year, month, day):
        max_day = calendar.monthrange(year, month)[1]
        return min(max(1, int(day)), max_day)

    first_day = _safe_day(inizio.year, inizio.month, giorno_scadenza)
    first_rate = date(inizio.year, inizio.month, first_day)
    if inizio.day > first_day:
        next_month = inizio + relativedelta(months=1)
        first_rate = date(next_month.year, next_month.month, _safe_day(next_month.year, next_month.month, giorno_scadenza))

    mesi_passati_cal = 0
    if oggi >= first_rate:
        cur = first_rate
        while cur <= oggi and mesi_passati_cal < durata_mesi:
            mesi_passati_cal += 1
            next_month = cur + relativedelta(months=1)
            cur = date(
                next_month.year,
                next_month.month,
                _safe_day(next_month.year, next_month.month, giorno_scadenza),
            )

    if rate_pagate_override is not None and not pd.isna(rate_pagate_override):
        mesi_passati = _to_int_default(rate_pagate_override, mesi_passati_cal)
    else:
        mesi_passati = mesi_passati_cal
    mesi_passati = max(0, min(mesi_passati, durata_mesi))

    # 3. Calcolo debito residuo/interessi
    if abs(tasso_mensile) < 1e-12:
        debito_residuo = capitale - (rata * mesi_passati)
    else:
        debito_residuo = float(npf.fv(tasso_mensile, mesi_passati, rata, -capitale))
    debito_residuo = float(max(0.0, min(capitale, debito_residuo)))

    totale_pagato = float(rata * mesi_passati)
    capitale_pagato = float(max(0.0, min(capitale, capitale - debito_residuo)))
    interessi_pagati = float(max(0.0, totale_pagato - capitale_pagato))
    interessi_totali = float(max(0.0, (rata * durata_mesi) - capitale))
    interessi_residui = float(max(0.0, interessi_totali - interessi_pagati))
    mesi_rimanenti = int(max(0, durata_mesi - mesi_passati))
    perc_comp = float((capitale_pagato / capitale) * 100) if capitale > 0 else 0.0
    perc_comp = max(0.0, min(100.0, perc_comp))

    return {
        "rata": round(float(rata), 2),
        "mesi_rimanenti": mesi_rimanenti,
        "mesi_pagati": mesi_passati,
        "interessi_pagati": round(interessi_pagati, 2),
        "interessi_totali": round(interessi_totali, 2),
        "interessi_residui": round(interessi_residui, 2),
        "debito_residuo": round(debito_residuo, 2),
        "capitale_pagato": round(capitale_pagato, 2),
        "percentuale_completato": round(perc_comp, 1),
    }
def analizza_entrate(df_transazioni, anno):
    """
    Estrae tutte le entrate dell'anno selezionato per generare il grafico.
    """
    # Filtriamo solo le entrate dell'anno specifico
    df = df_transazioni.copy()
    df['Tipo'] = _norm_tipo(df['Tipo'])
    df_entrate = df[
        (df['Tipo'] == TIPO_ENTRATA) &
        (df['Data'].dt.year == anno)
    ].copy()
    
    if df_entrate.empty:
        return pd.DataFrame(columns=['Mese', 'Importo'])

    # Raggruppiamo per mese
    entrate_mensili = df_entrate.groupby(df_entrate['Data'].dt.month)['Importo'].sum().reset_index()
    entrate_mensili.columns = ['Mese', 'Importo']
    
    # Mappiamo i numeri dei mesi in nomi brevi (Gen, Feb...) per il grafico
    nomi_mesi = {1:'Gen', 2:'Feb', 3:'Mar', 4:'Apr', 5:'Mag', 6:'Giu', 
                 7:'Lug', 8:'Ago', 9:'Set', 10:'Ott', 11:'Nov', 12:'Dic'}
    entrate_mensili['Mese'] = entrate_mensili['Mese'].map(nomi_mesi)
    
    return entrate_mensili
def obiettivo (df_transazioni, anno):
    """
    Calcola il totale delle entrate e delle uscite per l'anno selezionato.
    """
    df_anno = df_transazioni[df_transazioni['Data'].dt.year == anno].copy()
    df_anno['Tipo'] = _norm_tipo(df_anno['Tipo'])
    
    totale_entrate = df_anno[df_anno['Tipo'] == TIPO_ENTRATA]['Importo'].sum()
    totale_uscite = df_anno[df_anno['Tipo'] == TIPO_USCITA]['Importo'].sum()
    
    return {
        "Totale Entrate": round(totale_entrate, 2),
        "Totale Uscite": round(totale_uscite, 2),
        "Saldo": round(totale_entrate - totale_uscite, 2)
    }
# logica obiettivo risparmio
def obiettivo_risparmio(df_transazioni, anno, obiettivo_annuale):
    """
    Calcola quanto è stato risparmiato nell'anno e lo confronta con il target.
    """
    # 1. Calcoliamo il risparmio totale annuo
    df = df_transazioni.copy()
    df['Tipo'] = _norm_tipo(df['Tipo'])
    entrate = df[(df['Tipo'] == TIPO_ENTRATA) & (df['Data'].dt.year == anno)]['Importo'].sum()
    uscite = df[(df['Tipo'] == TIPO_USCITA) & (df['Data'].dt.year == anno)]['Importo'].abs().sum()
    
    risparmio_reale = entrate - uscite
    
    # 2. Calcolo scostamento e percentuale
    mancante = max(0, obiettivo_annuale - risparmio_reale)
    percentuale_completamento = (risparmio_reale / obiettivo_annuale * 100) if obiettivo_annuale > 0 else 0
    
    return {
        "Risparmio Totale": round(risparmio_reale, 2),
        "Obiettivo": obiettivo_annuale,
        "Mancante": round(mancante, 2),
        "Percentuale": round(percentuale_completamento, 1)
    }

#logica risparmio mensile per grafico andamento
def performance_risparmio_mensile(df_transazioni, anno):
    """
    Genera i dati per il grafico a barre verticali della % di risparmio mensile.
    Formula: ((Entrate - Uscite) / Entrate) * 100
    """
    dati_mensili = []
    nomi_mesi = {1:'Gen', 2:'Feb', 3:'Mar', 4:'Apr', 5:'Mag', 6:'Giu', 
                 7:'Lug', 8:'Ago', 9:'Set', 10:'Ott', 11:'Nov', 12:'Dic'}

    # Iteriamo per i 12 mesi
    for mese_num in range(1, 13):
        mask_mese = (df_transazioni['Data'].dt.month == mese_num) & (df_transazioni['Data'].dt.year == anno)
        df_mese = df_transazioni[mask_mese]
        
        df_mese = df_mese.copy()
        df_mese['Tipo'] = _norm_tipo(df_mese['Tipo'])
        entrate = df_mese[df_mese['Tipo'] == TIPO_ENTRATA]['Importo'].sum()
        uscite = df_mese[df_mese['Tipo'] == TIPO_USCITA]['Importo'].abs().sum()
        
        risparmio = entrate - uscite
        
        # Calcolo la percentuale di risparmio rispetto a quanto è entrato
        if entrate > 0:
            perc_risparmio = (risparmio / entrate) * 100
        else:
            perc_risparmio = 0
            
        dati_mensili.append({
            "Mese": nomi_mesi[mese_num],
            "Risparmio €": round(risparmio, 2),
            "% Risparmio": round(perc_risparmio, 1)
        })
        
    return pd.DataFrame(dati_mensili)

#logica grafico per versamento investimenti
def versamenti_asset(df_transazioni, anno):
    """
    Prepara i dati per il grafico ad area dei versamenti cumulati.
    Filtra per i dettagli 'PAC' e 'Fondo Pensione'.
    """
    # 1. Filtriamo le transazioni dell'anno per la categoria INVESTIMENTI
    df_investimenti = df_transazioni[
        (df_transazioni['Categoria'] == 'INVESTIMENTI') & 
        (df_transazioni['Data'].dt.year == anno)
    ].copy()
    
    if df_investimenti.empty:
        return pd.DataFrame(columns=['Mese', 'PAC', 'Fondo Pensione'])

    # 2. Creiamo una struttura per i 12 mesi
    nomi_mesi = {1:'Gen', 2:'Feb', 3:'Mar', 4:'Apr', 5:'Mag', 6:'Giu', 
                 7:'Lug', 8:'Ago', 9:'Set', 10:'Ott', 11:'Nov', 12:'Dic'}
    
    # 3. Raggruppiamo per mese e dettaglio, poi facciamo il pivot per avere colonne separate
    # Usiamo .abs() perché gli investimenti sono registrati come uscite (segno negativo)
    df_pivot = df_investimenti.groupby([df_investimenti['Data'].dt.month, 'Dettaglio'])['Importo'].sum().abs().unstack(fill_value=0)
    
    # Assicuriamoci che le colonne esistano anche se non ci sono versamenti
    if 'PAC' not in df_pivot: df_pivot['PAC'] = 0
    if 'Fondo Pensione' not in df_pivot: df_pivot['Fondo Pensione'] = 0
    
    # 4. Calcoliamo la SOMMA CUMULATA (fondamentale per il grafico ad area)
    # L'indice del dataframe sono i mesi (1-12)
    df_cumulato = df_pivot.cumsum().reindex(range(1, 13), fill_value=0)
    
    # 5. Formattiamo per l'interfaccia
    df_cumulato = df_cumulato.reset_index()
    df_cumulato['Mese'] = df_cumulato['Data'].map(nomi_mesi)
    
    return df_cumulato[['Mese', 'PAC', 'Fondo Pensione']]

#lgoica per previsione saldo futuro con regressione lineare

def previsione_saldo(df_transazioni, anno, saldo_iniziale=0.0, mese_riferimento=None):
    """
    Calcola il saldo reale mensile e usa la regressione lineare 
    per prevedere il saldo dei mesi futuri dell'anno.
    """
    nomi_mesi = {1:'Gen', 2:'Feb', 3:'Mar', 4:'Apr', 5:'Mag', 6:'Giu', 
                 7:'Lug', 8:'Ago', 9:'Set', 10:'Ott', 11:'Nov', 12:'Dic'}
    
    # 1. Calcolo il saldo netto mensile reale (Entrate - Uscite)
    #    fino al mese di riferimento (mese selezionato in UI oppure mese corrente).
    df_anno = df_transazioni[df_transazioni['Data'].dt.year == anno].copy()
    if df_anno.empty:
        return pd.DataFrame()
    df_anno['Tipo'] = _norm_tipo(df_anno['Tipo'])

    anno_corrente = datetime.now().year
    mese_corrente = datetime.now().month
    if mese_riferimento is None:
        mese_cutoff = mese_corrente if int(anno) == int(anno_corrente) else 12
    else:
        mese_cutoff = min(max(_to_int_default(mese_riferimento, mese_corrente), 1), 12)

    df_anno = df_anno[df_anno['Data'].dt.month <= mese_cutoff].copy()
    if df_anno.empty:
        return pd.DataFrame()

    mensile_raw = df_anno.groupby(df_anno['Data'].dt.month).apply(
        lambda x: x[x['Tipo'] == TIPO_ENTRATA]['Importo'].sum() - x[x['Tipo'] == TIPO_USCITA]['Importo'].abs().sum()
    )
    # Mesi 1..mese_cutoff: i mesi senza movimenti mantengono saldo invariato (netto mese = 0).
    mensile = mensile_raw.reindex(range(1, mese_cutoff + 1), fill_value=0.0)
    saldi_reali_serie = mensile.cumsum() + saldo_iniziale
    saldi_reali = saldi_reali_serie.tolist()
    
    # 3. LOGICA DI REGRESSIONE LINEARE
    # X = numeri dei mesi reali (1..mese_cutoff), Y = saldo cumulativo.
    # Richiediamo almeno 2 mesi effettivamente osservati nel registro.
    if len(mensile_raw.index.tolist()) > 1:
        x = np.arange(1, mese_cutoff + 1, dtype=float)
        y = np.array(saldi_reali)
        
        # Calcoliamo i parametri della retta: y = mx + q
        m, q = np.polyfit(x, y, 1)
        
        # 4. Proiettiamo per tutti i 12 mesi.
        ultimo_mese_reale = mese_cutoff
        ultimo_saldo_reale = float(saldi_reali_serie.iloc[-1])
        
        proiezione_totale = []
        for m_num in range(1, 13):
            nome_mese = nomi_mesi[m_num]
            
            if m_num <= ultimo_mese_reale:
                # Dati storici: restano identici
                tipo = "Reale"
                valore = float(saldi_reali_serie.loc[m_num])
            else:
                # PREVISIONE AGGANCIATA:
                # Partiamo dall'ultimo saldo reale e aggiungiamo il risparmio medio (m)
                # per ogni mese di distanza dal presente.
                tipo = "Previsione"
                mesi_di_distanza = m_num - ultimo_mese_reale
                valore = ultimo_saldo_reale + (m * mesi_di_distanza)
            
            proiezione_totale.append({
                "Mese": nome_mese,
                "Saldo": round(valore, 2),
                "Tipo": tipo
            })
        
        return pd.DataFrame(proiezione_totale)
    
    return pd.DataFrame() # Ritorna vuoto se non ci sono abbastanza dati

# logica proiezione andamento PAC
@st.cache_data(ttl=60)
def prezzo_attuale_ETF(ticker):
    """
    Recupera l'ultimo prezzo di chiusura disponibile per un dato ticker.
    Esempio ticker: 'V80A.DE' (Vanguard LifeStrategy 80) o 'VWCE.MI'
    """
    try:
        ticker = str(ticker).strip()
        tickers = [ticker]
        if "." not in ticker:
            tickers.extend([f"{ticker}.MI", f"{ticker}.DE", f"{ticker}.AS"])
        for t in tickers:
            azione = yf.Ticker(t)
            data = azione.history(period="1d")
            if not data.empty:
                prezzo = data["Close"].iloc[-1]
                return round(float(prezzo), 2)
    except Exception as e:
        print(f"Errore nel recupero del prezzo per {ticker}: {e}")
        return None

def versamenti_pac_da_registro(df_transazioni, anno_corrente=None):
    """
    Somma i versamenti PAC reali presenti nel registro movimenti.
    Considera solo uscite e intercetta PAC in Dettaglio/Note.
    """
    if df_transazioni is None or df_transazioni.empty:
        return 0.0

    if "Data" not in df_transazioni.columns or "Importo" not in df_transazioni.columns:
        return 0.0

    df = df_transazioni.copy()
    if not pd.api.types.is_datetime64_any_dtype(df["Data"]):
        df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df[df["Data"].notna()].copy()
    if df.empty:
        return 0.0

    tipo = _norm_tipo(df["Tipo"]) if "Tipo" in df.columns else pd.Series("", index=df.index)
    dettaglio = df["Dettaglio"].astype(str).str.upper().str.strip() if "Dettaglio" in df.columns else pd.Series("", index=df.index)
    note = df["Note"].astype(str).str.upper().str.strip() if "Note" in df.columns else pd.Series("", index=df.index)
    categoria = df["Categoria"].astype(str).str.upper().str.strip() if "Categoria" in df.columns else pd.Series("", index=df.index)

    mask_pac = (
        dettaglio.str.contains("PAC", na=False) |
        note.str.contains("PAC", na=False) |
        ((categoria == "INVESTIMENTI") & dettaglio.str.contains("ACCUMULO", na=False))
    )
    mask = (tipo == TIPO_USCITA) & mask_pac

    if anno_corrente is not None:
        mask = mask & (df["Data"].dt.year == int(anno_corrente))

    return float(df.loc[mask, "Importo"].abs().sum())


def analisi_pac(
    ticker,
    quote_base=0.0,
    capitale_base=0.0,
    versato_reale_anno=0.0,
    versamento_mensile_proiezione=0.0,
    rendimento_annuo_stimato=0.0,
    df_transazioni=None,
    anno_corrente=None,
    aliquota_plusvalenza=0.26,
    anni=10,
    # Parametri legacy per retrocompatibilita
    quote_da_db=None,
    capitale_investito_da_db=None,
    versamento_mensile_futuro=None,
):
    # Retrocompatibilita con vecchie chiamate
    if quote_da_db is not None:
        quote_base = quote_da_db
    if capitale_investito_da_db is not None:
        capitale_base = capitale_investito_da_db
    if versamento_mensile_futuro is not None:
        versamento_mensile_proiezione = versamento_mensile_futuro

    quote_base = float(quote_base or 0.0)
    capitale_base = float(capitale_base or 0.0)
    versamento_mensile_proiezione = float(versamento_mensile_proiezione or 0.0)
    rendimento_annuo_stimato = float(rendimento_annuo_stimato or 0.0)
    aliquota_plusvalenza = float(aliquota_plusvalenza or 0.0)
    # Le quote sono trattate come intere.
    quote_base = max(0.0, float(int(round(quote_base))))

    # Se disponibile, il versato reale viene letto dal registro movimenti
    if df_transazioni is not None:
        versato_reale_anno = versamenti_pac_da_registro(df_transazioni, anno_corrente)
    versato_reale_anno = float(versato_reale_anno or 0.0)

    # 1. RECUPERO PREZZO ATTUALE
    prezzo_mercato = prezzo_attuale_ETF(ticker)
    if prezzo_mercato is None or prezzo_mercato == 0:
        prezzo_mercato = (capitale_base / quote_base) if quote_base > 0 else 100.0
        error_mode = True
    else:
        error_mode = False

    # 2. STATO ATTUALE DINAMICO
    # Integra il capitale base con i versamenti PAC reali trovati nel registro.
    capitale_investito_totale = capitale_base + versato_reale_anno
    prezzo_medio_carico = (capitale_base / quote_base) if quote_base > 0 and capitale_base > 0 else prezzo_mercato
    nuove_quote_reali = int(math.floor(versato_reale_anno / prezzo_medio_carico)) if prezzo_medio_carico > 0 else 0
    cash_non_investita = max(0.0, versato_reale_anno - (nuove_quote_reali * prezzo_medio_carico)) if prezzo_medio_carico > 0 else versato_reale_anno
    quote_totali = quote_base + nuove_quote_reali

    valore_attuale = (quote_totali * prezzo_mercato) + cash_non_investita
    profit_loss_assoluto = valore_attuale - capitale_investito_totale
    profit_loss_perc = (profit_loss_assoluto / capitale_investito_totale * 100) if capitale_investito_totale > 0 else 0.0
    imposte_attuali = max(0.0, profit_loss_assoluto * aliquota_plusvalenza)
    netto_attuale = valore_attuale - imposte_attuali

    # 3. PROIEZIONE FUTURA
    r_mensile = (rendimento_annuo_stimato / 100) / 12
    proiezioni = []

    q_sim = quote_totali
    c_sim = capitale_investito_totale
    prezzo_sim = prezzo_mercato
    cash_sim = cash_non_investita

    for m in range(1, (anni * 12) + 1):
        prezzo_sim = prezzo_sim * (1 + r_mensile)

        if versamento_mensile_proiezione > 0 and prezzo_sim > 0:
            cash_sim += versamento_mensile_proiezione
            nuove_quote = int(math.floor(cash_sim / prezzo_sim))
            if nuove_quote > 0:
                q_sim += nuove_quote
                cash_sim -= (nuove_quote * prezzo_sim)
            c_sim += versamento_mensile_proiezione

        valore_m = (q_sim * prezzo_sim) + cash_sim
        imposte_m = max(0.0, (valore_m - c_sim) * aliquota_plusvalenza)

        proiezioni.append({
            "Mese": m,
            "Anno": round(m / 12, 2),
            "Capitale Versato": round(c_sim, 2),
            "Proiezione Stimata": round(valore_m, 2),
            "Valore Netto": round(valore_m - imposte_m, 2),
        })

    sintesi = {
        "Prezzo Mercato": round(prezzo_mercato, 2),
        "Quote_Totali": int(round(quote_totali)),
        "Capitale Investito": round(capitale_investito_totale, 2),
        "Valore Attuale": round(valore_attuale, 2),
        "P&L": round(profit_loss_assoluto, 2),
        "P&L %": round(profit_loss_perc, 2),
        "Imposte": round(imposte_attuali, 2),
        "Netto": round(netto_attuale, 2),
        "Versato_Reale_Registro": round(versato_reale_anno, 2),
        "Liquidita_Non_Investita": round(cash_non_investita, 2),
        "Error": error_mode,
    }

    return {
        "Sintesi": sintesi,
        "Sintesi_Attuale": {
            "Prezzo Mercato": sintesi["Prezzo Mercato"],
            "Quote Totali": sintesi["Quote_Totali"],
            "Capitale Investito": sintesi["Capitale Investito"],
            "Valore Attuale Lordo": sintesi["Valore Attuale"],
            "Plusvalenza": sintesi["P&L"],
            "Imposte": sintesi["Imposte"],
            "Netto": sintesi["Netto"],
            "Error": sintesi["Error"],
        },
        "Grafico_Proiezione": pd.DataFrame(proiezioni),
    }
    
#logica proiezione andamento fondo pensione
def analisi_fondo_pensione(valore_quota, quote_base, capitale_base,
                            versamento_mensile, rendimento_annuo_stimato,
                            df_transazioni, anno_corrente, aliquota_irpef=0.33, anni=30,
                            data_snapshot=None, tfr_versato_anno=0.0):
    """
    Calcola valore attuale dai dati reali e proietta il futuro.
    """
    import datetime # Import locale per sicurezza
    
    SOGLIA_MAX = 5164.57
    valore_quota = float(valore_quota or 0.0)
    quote_base = float(quote_base or 0.0)
    capitale_base = float(capitale_base or 0.0)
    versamento_mensile = float(versamento_mensile or 0.0)
    rendimento_annuo_stimato = float(rendimento_annuo_stimato or 0.0)
    aliquota_irpef = float(aliquota_irpef or 0.0)

    if valore_quota <= 0:
        return {
            "Sintesi": {
                "Valore Quota": 0.0,
                "Valore Attuale": 0.0,
                "Capitale Investito": round(capitale_base, 2),
                "P&L": 0.0,
                "P&L %": 0.0,
                "Quote Attuali": round(quote_base, 2),
                "Quote Finali": round(quote_base, 2),
                "Beneficio IRPEF Stimato": 0.0,
            },
            "Avanzamento_Fiscale": {
                "Versato_Anno": 0.0,
                "Rimanente_Soglia": SOGLIA_MAX,
                "Percentuale": 0.0,
                "Soglia": SOGLIA_MAX,
            },
            "Grafico_Proiezione": pd.DataFrame(),
        }
    
    oggi = date.today()
    mese_attuale = oggi.month
    anno_reale_oggi = oggi.year

    # Normalizza data_snapshot: se non passata, usa il 1 gennaio dell'anno corrente
    # così il comportamento è identico a prima (retrocompatibile)
    if data_snapshot is None:
        data_snapshot = date(anno_corrente, 1, 1)
    elif not isinstance(data_snapshot, date):
        data_snapshot = pd.to_datetime(data_snapshot).date()

    tfr_versato_anno = float(tfr_versato_anno or 0.0)

    # 1. RECUPERO VERSAMENTI ADERENTE DAL REGISTRO (solo DOPO lo snapshot)
    # Così evitiamo doppio conteggio con capitale_base che include già tutto fino allo snapshot
    df_fondo_delta = df_transazioni[
        (df_transazioni['Dettaglio'].str.contains("Fondo pensione", case=False, na=False)) &
        (df_transazioni['Data'].dt.date > data_snapshot)
    ].copy().sort_values('Data')

    # 2. CALCOLO QUOTE NUOVE per transazione (prezzo del giorno se disponibile)
    nuove_quote_aderente = 0.0
    versato_aderente_delta = 0.0
    for _, riga in df_fondo_delta.iterrows():
        importo = abs(float(riga['Importo']))
        prezzo = float(riga['Valore_Quota']) if 'Valore_Quota' in riga.index and float(riga.get('Valore_Quota', 0)) > 0 else valore_quota
        nuove_quote_aderente += importo / prezzo
        versato_aderente_delta += importo

    # 3. QUOTE E CAPITALE TFR (versato dopo lo snapshot, inserito manualmente)
    nuove_quote_tfr = tfr_versato_anno / valore_quota if valore_quota > 0 else 0.0

    # 4. STATO ATTUALE TOTALE
    quote_attuali_totali   = quote_base + nuove_quote_aderente + nuove_quote_tfr
    capitale_investito_totale = capitale_base + versato_aderente_delta + tfr_versato_anno

    # Versato anno solare (per avanzamento fiscale) = tutte le transaz. fondo dell'anno corrente
    versato_reale_anno = df_transazioni[
        (df_transazioni['Dettaglio'].str.contains("Fondo pensione", case=False, na=False)) &
        (df_transazioni['Data'].dt.year == anno_corrente)
    ]['Importo'].abs().sum()
    
    valore_attuale_reale = valore_quota * quote_attuali_totali
    pl_assoluto = valore_attuale_reale - capitale_investito_totale
    pl_perc = (pl_assoluto / capitale_investito_totale * 100) if capitale_investito_totale > 0 else 0
    
    # 3. AVANZAMENTO FISCALE
    rimanente_soglia = max(0, SOGLIA_MAX - versato_reale_anno)
    perc_avanzamento_fiscale = min(100, (versato_reale_anno / SOGLIA_MAX) * 100) if SOGLIA_MAX > 0 else 0
    beneficio_irpef_annuo = min(versamento_mensile * 12, SOGLIA_MAX) * aliquota_irpef
    
    # 4. PROIEZIONE FUTURA
    r_mensile = (rendimento_annuo_stimato / 100) / 12
    proiezioni = []
    
    prezzo_quota_temp = valore_quota
    quote_totali_temp = quote_attuali_totali 
    cap_versato_cumu = capitale_investito_totale
    
    mesi_totali = anni * 12
    
    for m in range(1, mesi_totali + 1):
        prezzo_quota_temp *= (1 + r_mensile)
        
        # Versa solo se siamo nel futuro (evita raddoppio nel mese corrente)
        if not (anno_corrente == anno_reale_oggi and m <= mese_attuale):
            nuove_quote = versamento_mensile / prezzo_quota_temp
            quote_totali_temp += nuove_quote
            cap_versato_cumu += versamento_mensile

        valore_totale = quote_totali_temp * prezzo_quota_temp
        
        proiezioni.append({
            "Mese": m,
            "Anno": round(m / 12, 1),
            "Cap.Versato Cumu.": round(cap_versato_cumu, 2),
            "Proiezione Teorica": round(valore_totale, 2),
            "Quote Totali": round(quote_totali_temp, 4),
            # Baseline fissa del valore attuale, usata come linea di confronto.
            "Valore Attuale Linea": round(valore_attuale_reale, 2)
        })
        
    return {
        "Sintesi": {
            "Valore Quota": valore_quota,
            "Valore Attuale": round(valore_attuale_reale, 2),
            "Capitale Investito": round(capitale_investito_totale, 2),
            "P&L": round(pl_assoluto, 2),
            "P&L %": round(pl_perc, 2),
            "Quote Attuali": round(quote_attuali_totali, 2),
            "Quote Finali": round(quote_totali_temp, 2),
            "Beneficio IRPEF Stimato": round(beneficio_irpef_annuo, 2),
        },
        "Avanzamento_Fiscale": {
            "Versato_Anno": round(versato_reale_anno, 2),
            "Rimanente_Soglia": round(rimanente_soglia, 2),
            "Percentuale": round(perc_avanzamento_fiscale, 1),
            "Soglia": SOGLIA_MAX
        },
        "Grafico_Proiezione": pd.DataFrame(proiezioni)
    }
# Composizione portafoglio
def composizione_portafoglio(saldo_fineco, saldo_revolut, valore_attuale_pac, valore_attuale_fondo):
    """
    Calcola il valore totale del portafoglio e la suddivisione percentuale.
    """
    totale = saldo_fineco + saldo_revolut + valore_attuale_pac + valore_attuale_fondo
    
    if totale == 0:
        return {}

    composizione = [
        {"Asset": "Liquidità Fineco", "Valore": saldo_fineco, "Perc": round((saldo_fineco / totale) * 100, 1)},
        {"Asset": "Liquidità Revolut", "Valore": saldo_revolut, "Perc": round((saldo_revolut / totale) * 100, 1)},
        {"Asset": "PAC", "Valore": valore_attuale_pac, "Perc": round((valore_attuale_pac / totale) * 100, 1)},
        {"Asset": "Fondo Pensione", "Valore": valore_attuale_fondo, "Perc": round((valore_attuale_fondo / totale) * 100, 1)}
    ]
    
    return {
        "Totale_Patrimonio": round(totale, 2),
        "Dettaglio": pd.DataFrame(composizione)
    }

#logica variazione investimenti
def variazione_investimenti(df_transazioni, anno_corrente):
    """
    Confronta i versamenti PAC/Fondo registrati nel registro tra anno corrente e precedente.
    Restituisce sia i totali annui sia lo split per asset.
    """
    anno_corrente = int(anno_corrente)
    anno_precedente = anno_corrente - 1

    default_payload = {
        "Anno_Corrente": 0.0,
        "Anno_Precedente": 0.0,
        "PAC_Anno_Corrente": 0.0,
        "PAC_Anno_Precedente": 0.0,
        "Fondo_Anno_Corrente": 0.0,
        "Fondo_Anno_Precedente": 0.0,
        "Variazione_Assoluta": 0.0,
        "Variazione_Perc": 0.0,
    }

    if df_transazioni is None or df_transazioni.empty:
        return default_payload

    df = df_transazioni.copy()
    if "Data" not in df.columns or "Importo" not in df.columns:
        return default_payload

    if not pd.api.types.is_datetime64_any_dtype(df["Data"]):
        df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df[df["Data"].notna()].copy()
    if df.empty:
        return default_payload

    tipo = _norm_tipo(df["Tipo"]) if "Tipo" in df.columns else pd.Series("", index=df.index)
    dettaglio = df["Dettaglio"].astype(str).str.upper().str.strip() if "Dettaglio" in df.columns else pd.Series("", index=df.index)
    note = df["Note"].astype(str).str.upper().str.strip() if "Note" in df.columns else pd.Series("", index=df.index)

    is_pac = dettaglio.str.contains("PAC", na=False) | note.str.contains("PAC", na=False)
    is_fondo = (
        dettaglio.str.contains("FONDO", na=False) |
        dettaglio.str.contains("PENSION", na=False) |
        note.str.contains("FONDO", na=False) |
        note.str.contains("PENSION", na=False)
    )

    mask_investimenti = (tipo == TIPO_USCITA) & (is_pac | is_fondo)
    df_inv = df.loc[mask_investimenti, ["Data", "Importo"]].copy()
    if df_inv.empty:
        return default_payload

    df_inv["Asset"] = np.where(is_pac.loc[df_inv.index], "PAC", "FONDO PENSIONE")

    pac_corrente = float(
        df_inv.loc[
            (df_inv["Data"].dt.year == anno_corrente) & (df_inv["Asset"] == "PAC"),
            "Importo",
        ].abs().sum()
    )
    pac_precedente = float(
        df_inv.loc[
            (df_inv["Data"].dt.year == anno_precedente) & (df_inv["Asset"] == "PAC"),
            "Importo",
        ].abs().sum()
    )
    fondo_corrente = float(
        df_inv.loc[
            (df_inv["Data"].dt.year == anno_corrente) & (df_inv["Asset"] == "FONDO PENSIONE"),
            "Importo",
        ].abs().sum()
    )
    fondo_precedente = float(
        df_inv.loc[
            (df_inv["Data"].dt.year == anno_precedente) & (df_inv["Asset"] == "FONDO PENSIONE"),
            "Importo",
        ].abs().sum()
    )

    investito_anno_corrente = pac_corrente + fondo_corrente
    investito_anno_precedente = pac_precedente + fondo_precedente
    variazione_assoluta = investito_anno_corrente - investito_anno_precedente
    if investito_anno_precedente > 0:
        variazione_perc = (variazione_assoluta / investito_anno_precedente) * 100
    else:
        variazione_perc = 0.0

    return {
        "Anno_Corrente": round(investito_anno_corrente, 2),
        "Anno_Precedente": round(investito_anno_precedente, 2),
        "PAC_Anno_Corrente": round(pac_corrente, 2),
        "PAC_Anno_Precedente": round(pac_precedente, 2),
        "Fondo_Anno_Corrente": round(fondo_corrente, 2),
        "Fondo_Anno_Precedente": round(fondo_precedente, 2),
        "Variazione_Assoluta": round(variazione_assoluta, 2),
        "Variazione_Perc": round(variazione_perc, 2),
    }

#Logica KPI dashboard

def calcola_kpi_dashboard(df_transazioni, mese, anno):
    """
    Calcola Saldo Disponibile, Uscite del Mese, Risparmio e Tasso di Risparmio.
    """
    # 1. Filtriamo le transazioni per il mese e anno selezionati
    mask_mese = (df_transazioni['Data'].dt.month == mese) & (df_transazioni['Data'].dt.year == anno)
    df_mese = df_transazioni[mask_mese].copy()
    df_mese['Tipo'] = _norm_tipo(df_mese['Tipo'])
    
    # 2. Calcolo Uscite del Mese (Valore assoluto delle uscite)
    uscite_mese = df_mese[df_mese['Tipo'] == TIPO_USCITA]['Importo'].abs().sum()
    
    # 3. Calcolo Entrate del Mese
    entrate_mese = df_mese[df_mese['Tipo'] == TIPO_ENTRATA]['Importo'].sum()
    
    # 4. Calcolo Risparmio Mensile (Entrate - Uscite)
    risparmio_mese = entrate_mese - uscite_mese
    
    # 5. Calcolo Tasso di Risparmio %
    tasso_risparmio = (risparmio_mese / entrate_mese * 100) if entrate_mese > 0 else 0
    
    # 6. Saldo Disponibile Totale (Storico cumulativo fino alla fine del mese selezionato)
    # Calcoliamo tutte le entrate e uscite fino a quel momento
    mask_storico = (df_transazioni['Data'].dt.year < anno) | \
                   ((df_transazioni['Data'].dt.year == anno) & (df_transazioni['Data'].dt.month <= mese))
    
    df_storico = df_transazioni[mask_storico].copy()
    df_storico['Tipo'] = _norm_tipo(df_storico['Tipo'])
    entrate_tot = df_storico[df_storico['Tipo'] == TIPO_ENTRATA]['Importo'].sum()
    uscite_tot = df_storico[df_storico['Tipo'] == TIPO_USCITA]['Importo'].abs().sum()
    
    saldo_disponibile = entrate_tot - uscite_tot
    
    return {
        "saldo_disponibile": round(saldo_disponibile, 2),
        "uscite_mese": round(uscite_mese, 2),
        "risparmio_mese": round(risparmio_mese, 2),
        "tasso_risparmio": round(tasso_risparmio, 2)
    }

def saldo_disponibile_da_inizio(df_transazioni, anno, mese, saldo_iniziale=0.0):
    """
    Calcola il saldo disponibile partendo dal saldo iniziale del 1 gennaio
    e sommando entrate/uscite fino al mese selezionato.
    """
    mask = (df_transazioni['Data'].dt.year == anno) & (df_transazioni['Data'].dt.month <= mese)
    df = df_transazioni[mask].copy()
    df['Tipo'] = _norm_tipo(df['Tipo'])
    entrate = df[df['Tipo'] == TIPO_ENTRATA]['Importo'].sum()
    uscite = df[df['Tipo'] == TIPO_USCITA]['Importo'].abs().sum()
    return round(saldo_iniziale + entrate - uscite, 2)

def budget_spese_annuale(df_transazioni, anno, budget_mensile_base):
    """
    Prepara i dati per il grafico budget mensile (50/30/20).
    budget_mensile_base è il valore fisso su cui calcolare le percentuali.
    """
    if budget_mensile_base <= 0:
        return pd.DataFrame()

    if df_transazioni is None or df_transazioni.empty:
        return pd.DataFrame()

    required_cols = {"Data", "Tipo", "Categoria", "Importo"}
    if not required_cols.issubset(df_transazioni.columns):
        return pd.DataFrame()

    df = df_transazioni.copy()
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df[df["Data"].notna()]
    if df.empty:
        return pd.DataFrame()

    df = df[df['Data'].dt.year == anno].copy()
    df['Tipo'] = _norm_tipo(df['Tipo'])
    df = df[df['Tipo'] == TIPO_USCITA]
    if df.empty:
        return pd.DataFrame()

    df['Categoria'] = df['Categoria'].astype(str).str.upper().str.strip()
    # Normalizzazione categorie legacy (es. senza accento) per evitare buchi nel budget.
    df['Categoria'] = df['Categoria'].replace({
        "NECESSITA": "NECESSITÀ",
        "NECESSITA'": "NECESSITÀ",
        "NECESSITA`": "NECESSITÀ",
    })
    df['MeseNum'] = df['Data'].dt.month

    spese = df.groupby(['MeseNum', 'Categoria'])['Importo'].sum().abs().reset_index()
    mesi = range(1, 13)
    righe = []
    for m in mesi:
        for cat, perc in PERCENTUALI_BUDGET.items():
            speso = spese[(spese['MeseNum'] == m) & (spese['Categoria'] == cat)]['Importo'].sum()
            budget_cat = budget_mensile_base * perc
            residuo = budget_cat - speso
            righe.append({
                "MeseNum": m,
                "Mese": {1:'Gen', 2:'Feb', 3:'Mar', 4:'Apr', 5:'Mag', 6:'Giu', 7:'Lug', 8:'Ago', 9:'Set', 10:'Ott', 11:'Nov', 12:'Dic'}[m],
                "Categoria": cat,
                "Speso": round(speso, 2),
                "BudgetCategoria": round(budget_cat, 2),
                "Residuo": round(residuo, 2),
                "BudgetTotale": round(budget_mensile_base, 2)
            })

    return pd.DataFrame(righe)
