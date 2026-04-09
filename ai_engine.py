"""
ai_engine.py — Motore AI centralizzato (Gemini Flash, free tier)
=================================================================
Espone tre funzioni pubbliche:

  1. chat_financial_advisor(message, context)  →  str
     Chatbot che risponde a domande personali sulle finanze dell'utente.

  2. detect_anomalies(df_mov, df_ric, df_fin)  →  list[dict]
     Identifica anomalie di spesa e pattern stagionali nei movimenti.

  3. generate_monthly_report(kpi_curr, kpi_prev, anomalies) →  str
     Genera un paragrafo narrativo da inserire nell'email mensile.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from functools import lru_cache
from typing import Any
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurazione Gemini
# ---------------------------------------------------------------------------

_GEMINI_MODEL = "models/gemini-2.5-flash" # free tier, più che sufficiente per uso privato
_MAX_OUTPUT_TOKENS = 1024             # teniamo basso per restare nel free tier


@lru_cache(maxsize=1)
def _get_client():
    try:
        from google import genai
    except ImportError:
        raise RuntimeError(
            "Pacchetto 'google-genai' non installato. "
            "Eseguire: pip install google-genai"
        )

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("GEMINI_API_KEY")
        except Exception:
            pass

    if not api_key:
        try:
            from config_runtime import get_secret
            api_key = get_secret("GEMINI_API_KEY")
        except Exception:
            pass

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY non configurata. "
            "Aggiungerla in .streamlit/secrets.toml o come variabile d'ambiente."
        )

    return genai.Client(api_key=api_key)


def _gemini_error_types():
    try:
        from google import genai
        return genai.errors.ClientError, genai.errors.ServerError
    except Exception:
        # Se il pacchetto manca, il modulo AI continua a importarsi correttamente
        # e le feature AI degraderanno con fallback invece di bloccare l'app.
        return RuntimeError, RuntimeError

def _call_gemini(system_prompt, user_prompt, retries=3, delay=2):
    client_error_cls, server_error_cls = _gemini_error_types()
    try:
        client = _get_client()
    except Exception as exc:
        logger.warning("Gemini non disponibile: %s", exc)
        return ""

    full_prompt = f"{system_prompt}\n\n{user_prompt}"
    
    for i in range(retries):
        try:
            response = client.models.generate_content(
                model=_GEMINI_MODEL,
                contents=full_prompt,
            )
            return response.text
        except client_error_cls as exc:
            logger.warning("Gemini ClientError: %s", exc)
            return ""
        except server_error_cls:
            if i < retries - 1: # Se non è l'ultimo tentativo
                time.sleep(delay) # Aspetta 2 secondi e riprova
                continue
            else:
                logger.warning("Gemini ServerError dopo %d tentativi.", retries)
                return ""
        except Exception as exc:
            logger.warning("Gemini errore inatteso: %s", exc)
            return ""


def diagnose_gemini() -> dict[str, Any]:
    """
    Verifica se Gemini è configurato e se una chiamata minima risponde.

    Ritorna:
      configured: bool
      reachable: bool
      model: str
      message: str
      sample_response: str
    """
    result: dict[str, Any] = {
        "configured": False,
        "reachable": False,
        "model": _GEMINI_MODEL,
        "message": "",
        "sample_response": "",
    }

    try:
        client = _get_client()
        result["configured"] = True
    except Exception as exc:
        result["message"] = f"Configurazione Gemini non disponibile: {exc}"
        return result

    try:
        response = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents="Rispondi solo con la parola OK.",
        )
        text = " ".join(str(getattr(response, "text", "") or "").split())
        result["sample_response"] = text
        result["reachable"] = bool(text)
        result["message"] = "Gemini raggiungibile e operativo." if text else "Gemini configurato ma risposta vuota."
        return result
    except Exception as exc:
        result["message"] = f"Gemini configurato ma non raggiungibile: {exc}"
        return result


# ---------------------------------------------------------------------------
# Helper: costruzione del contesto finanziario
# ---------------------------------------------------------------------------

def _normalize_movimenti(df_mov: pd.DataFrame | None) -> pd.DataFrame:
    if df_mov is None or df_mov.empty:
        return pd.DataFrame()

    df = df_mov.copy()
    df.columns = [c.lower() for c in df.columns]
    df["data"] = pd.to_datetime(df.get("data"), errors="coerce")
    df = df[df["data"].notna()].copy()
    if df.empty:
        return df

    df["tipo"] = df.get("tipo", pd.Series(dtype=str)).astype(str).str.upper().str.strip()
    df["categoria"] = df.get("categoria", pd.Series(dtype=str)).astype(str).str.upper().str.strip()
    df["dettaglio"] = df.get("dettaglio", pd.Series("", index=df.index)).astype(str)
    df["note"] = df.get("note", pd.Series("", index=df.index)).astype(str)
    df["importo"] = pd.to_numeric(df.get("importo", 0), errors="coerce").fillna(0.0)
    df["importo_assoluto"] = df["importo"].abs()
    df["anno"] = df["data"].dt.year
    df["mese"] = df["data"].dt.month
    df["anno_mese"] = df["data"].dt.to_period("M").astype(str)
    return df


def _monthly_equivalent_from_ricorrenti(df_ric: pd.DataFrame) -> pd.DataFrame:
    if df_ric is None or df_ric.empty:
        return pd.DataFrame()

    df = df_ric.copy()
    df.columns = [c.lower() for c in df.columns]
    if "importo" not in df.columns or "descrizione" not in df.columns:
        return pd.DataFrame()

    freq_col = "frequenza_mesi" if "frequenza_mesi" in df.columns else "frequenza"
    if freq_col not in df.columns:
        df[freq_col] = 1

    df["importo"] = pd.to_numeric(df["importo"], errors="coerce").fillna(0.0)
    df[freq_col] = pd.to_numeric(df[freq_col], errors="coerce").fillna(1).clip(lower=1)
    df["importo_mensile_equiv"] = df["importo"] / df[freq_col]
    return df


def _calcola_rata_mensile(capitale: float, taeg: float, durata_mesi: int) -> float:
    try:
        capitale = float(capitale or 0.0)
        taeg = float(taeg or 0.0)
        durata_mesi = int(durata_mesi or 0)
        if capitale <= 0 or durata_mesi <= 0:
            return 0.0
        r = (taeg / 100.0) / 12.0
        if r <= 0:
            return capitale / durata_mesi
        return (capitale * r) / (1 - (1 + r) ** (-durata_mesi))
    except Exception:
        return 0.0


def build_financial_context(
    kpi: dict[str, Any],
    df_mov: pd.DataFrame | None = None,
    df_ric: pd.DataFrame | None = None,
    df_fin: pd.DataFrame | None = None,
    obiettivi_utente: list[dict[str, Any]] | None = None,
) -> str:
    """
    Costruisce il contesto AI esclusivamente dai dati già filtrati
    per l'utente corrente. Nessuna query aggiuntiva a viste globali.
    """
    lines: list[str] = []
    oggi = datetime.now()

    # ── KPI sintetici ──────────────────────────────────────────────────────
    if kpi:
        lines.append(f"## KPI mese corrente ({oggi.month}/{oggi.year})")
        mapping = {
            "saldo_reale_totale": "*** SALDO REALE TOTALE CONTI (EUR) *** — usa QUESTO per 'posso permettermi X'",
            "saldo_fineco": "Saldo conto principale (EUR)",
            "saldo_revolut": "Saldo conto secondario (EUR)",
            "entrate_mese": "Entrate mese corrente (EUR)",
            "uscite_mese": "Uscite mese corrente (EUR)",
            "risparmio_mese": "Risparmio mese corrente (EUR)",
            "tasso_risparmio": "Tasso risparmio mese corrente (%)",
            "risparmio_medio_3mesi": "Risparmio medio ultimi 3 mesi (EUR) — usa per 'tra quanto posso permettermi X'",
            "saldo_proiettato_dicembre": "Saldo proiettato a fine anno (cash flow stimato)",
            "slope_risparmio_mensile": "Trend risparmio mensile stimato (EUR/mese; >0 migliora, <0 peggiora)",
            "r2_previsione": "Affidabilità statistica della previsione R² (0-1; <0.3 bassa)",
            "delta_previsto_mensile": "Delta mensile previsto del saldo (entrate attese - uscite attese)",
            "entrate_attese_previsione": "Entrate mensili attese usate nella previsione saldo",
            "uscite_attese_previsione": "Uscite mensili attese usate nella previsione saldo",
            "metodo_previsione_saldo": "Metodo usato per la previsione saldo",
            "saldo_disponibile": "Saldo calcolato da movimenti (EUR) — NON usare per affordability",
        }
        for key, label in mapping.items():
            if key in kpi and kpi.get(key) is not None:
                lines.append(f"- {label}: {kpi.get(key)}")

    # ── Movimenti, ranking e riepiloghi ───────────────────────────────────
    df = _normalize_movimenti(df_mov)
    lines.append("\n## Elenco movimenti dettagliato (ultimi 24 mesi)")
    lines.append("Colonne: data | anno | mese | tipo | categoria | dettaglio | importo_eur | rank_nel_mese | rank_nell_anno")
    if not df.empty:
        uscite_rank = df[df["tipo"] == "USCITA"].copy()
        if not uscite_rank.empty:
            uscite_rank["rank_nel_mese"] = uscite_rank.groupby(["anno", "mese"])["importo_assoluto"].rank(
                method="dense", ascending=False
            )
            uscite_rank["rank_nell_anno"] = uscite_rank.groupby(["anno"])["importo_assoluto"].rank(
                method="dense", ascending=False
            )
            df = df.merge(
                uscite_rank[["data", "dettaglio", "importo", "rank_nel_mese", "rank_nell_anno"]],
                on=["data", "dettaglio", "importo"],
                how="left",
            )
        df = df.sort_values("data", ascending=False).head(250)
        for _, row in df.iterrows():
            lines.append(
                f"{str(row['data'])[:10]} | {int(row['anno'])} | {int(row['mese'])} | "
                f"{row['tipo']} | {row['categoria']} | {row['dettaglio']} | "
                f"{float(row['importo_assoluto']):.2f} | "
                f"rank_mese:{int(row['rank_nel_mese']) if pd.notna(row.get('rank_nel_mese')) else '-'} | "
                f"rank_anno:{int(row['rank_nell_anno']) if pd.notna(row.get('rank_nell_anno')) else '-'}"
            )
    else:
        lines.append("(nessun movimento disponibile)")

    lines.append("\n## Riepilogo mensile per categoria (EUR)")
    lines.append("Colonne: anno | mese | anno_mese | tipo | categoria | num_movimenti | totale | media | massimo | minimo")
    if not df.empty:
        monthly = df.groupby(["anno", "mese", "anno_mese", "tipo", "categoria"]).agg(
            num_movimenti=("importo", "size"),
            totale=("importo_assoluto", "sum"),
            media=("importo_assoluto", "mean"),
            massimo=("importo_assoluto", "max"),
            minimo=("importo_assoluto", "min"),
        ).reset_index().sort_values(["anno", "mese", "tipo", "categoria"])
        for _, row in monthly.tail(120).iterrows():
            lines.append(
                f"{int(row['anno'])} | {int(row['mese'])} | {row['anno_mese']} | "
                f"{row['tipo']} | {row['categoria']} | "
                f"n:{int(row['num_movimenti'])} | tot:{float(row['totale']):.2f} | "
                f"media:{float(row['media']):.2f} | max:{float(row['massimo']):.2f} | "
                f"min:{float(row['minimo']):.2f}"
            )

        lines.append("\n## Riepilogo annuale per categoria (EUR)")
        lines.append("Colonne: anno | tipo | categoria | num_movimenti | totale | media | massimo")
        yearly = df.groupby(["anno", "tipo", "categoria"]).agg(
            num_movimenti=("importo", "size"),
            totale=("importo_assoluto", "sum"),
            media=("importo_assoluto", "mean"),
            massimo=("importo_assoluto", "max"),
        ).reset_index().sort_values(["anno", "tipo", "categoria"])
        for _, row in yearly.tail(80).iterrows():
            lines.append(
                f"{int(row['anno'])} | {row['tipo']} | {row['categoria']} | "
                f"n:{int(row['num_movimenti'])} | tot:{float(row['totale']):.2f} | "
                f"media:{float(row['media']):.2f} | max:{float(row['massimo']):.2f}"
            )

        lines.append("\n## Top spese (ranking per mese e anno)")
        lines.append("Colonne: data | anno | mese | categoria | dettaglio | importo_eur | rank_nel_mese | rank_nell_anno")
        top = df[df["tipo"] == "USCITA"].copy()
        if not top.empty:
            top = top[top["rank_nel_mese"].fillna(99) <= 3].sort_values(["anno", "mese", "rank_nel_mese"])
            for _, row in top.tail(120).iterrows():
                lines.append(
                    f"{str(row['data'])[:10]} | {int(row['anno'])} | {int(row['mese'])} | "
                    f"{row['categoria']} | {row['dettaglio']} | "
                    f"{float(row['importo_assoluto']):.2f} | "
                    f"rank_mese:{int(row['rank_nel_mese']) if pd.notna(row.get('rank_nel_mese')) else '-'} | "
                    f"rank_anno:{int(row['rank_nell_anno']) if pd.notna(row.get('rank_nell_anno')) else '-'}"
                )
    else:
        lines.append("(riepilogo non disponibile)")

    # ── Ricorrenti ─────────────────────────────────────────────────────────
    lines.append("\n## Spese ricorrenti attive")
    lines.append("Colonne: descrizione | importo | frequenza | importo_mensile_equiv_eur")
    ric = _monthly_equivalent_from_ricorrenti(df_ric if df_ric is not None else pd.DataFrame())
    if not ric.empty:
        total_monthly = float(ric["importo_mensile_equiv"].sum())
        lines.append(f"- Totale equivalente mensile: EUR {total_monthly:.2f}")
        for _, row in ric.sort_values("importo_mensile_equiv", ascending=False).head(50).iterrows():
            freq_val = int(row.get("frequenza_mesi", row.get("frequenza", 1)) or 1)
            freq_label = "Mensile" if freq_val == 1 else f"Ogni {freq_val} mesi"
            lines.append(
                f"  . {row['descrizione']}: EUR {float(row['importo']):.2f} "
                f"({freq_label}) = EUR {float(row['importo_mensile_equiv']):.2f}/mese"
            )
    else:
        lines.append("  (nessuna spesa ricorrente attiva)")

    # ── Finanziamenti ──────────────────────────────────────────────────────
    lines.append("\n## Finanziamenti attivi")
    lines.append("Colonne: nome | capitale | rata_mensile | rate_rimanenti | data_fine_prevista | completamento_pct")
    if df_fin is not None and not df_fin.empty:
        fin = df_fin.copy()
        fin.columns = [c.lower() for c in fin.columns]
        for _, row in fin.iterrows():
            durata = int(row.get("durata_mesi", 0) or 0)
            rate_pagate = int(row.get("rate_pagate", 0) or 0)
            rate_rimanenti = max(durata - rate_pagate, 0)
            rata = _calcola_rata_mensile(row.get("capitale_iniziale", 0.0), row.get("taeg", 0.0), durata)
            completamento = (rate_pagate / durata * 100.0) if durata > 0 else 0.0
            data_fine = ""
            try:
                data_inizio = pd.to_datetime(row.get("data_inizio"), errors="coerce")
                if pd.notna(data_inizio) and durata > 0:
                    data_fine = str((data_inizio + pd.DateOffset(months=durata)).date())
            except Exception:
                data_fine = ""
            lines.append(
                f"  . {row.get('nome','N/D')}: capitale EUR {float(row.get('capitale_iniziale', 0) or 0):.2f}, "
                f"rata EUR {float(rata):.2f}/mese, rate rimanenti: {rate_rimanenti}, "
                f"fine prevista: {data_fine or 'N/D'}, completato: {float(completamento):.1f}%"
            )
    else:
        lines.append("  (nessun finanziamento attivo)")

    # ── Obiettivi ──────────────────────────────────────────────────────────
    obiettivi = obiettivi_utente if obiettivi_utente is not None else kpi.get("obiettivi_utente", [])
    lines.append("\n## Obiettivi finanziari dell'utente")
    if obiettivi:
        lines.append(
            "Colonne: nome | costo_eur | scadenza | accantonato_reale_eur | dedicato_eur_mese "
            "| mesi_rimanenti | versamenti_previsti_eur | totale_previsto_eur "
            "| gap_attuale_eur | gap_previsto_eur | stato"
        )
        for ob in obiettivi:
            lines.append(
                f"  . {ob['nome']}: €{ob['costo']:.0f}, "
                f"scadenza {ob['scadenza']}, accantonato reale €{ob['accantonato_reale']:.0f}, "
                f"dedicato €{ob['dedicato']:.0f}/mese, mesi rimanenti: {ob['mesi_rim']}, "
                f"versamenti previsti: €{ob['versamenti_previsti']:.0f}, totale previsto: €{ob['totale_previsto']:.0f}, "
                f"gap attuale: €{ob['gap_attuale']:.0f}, gap previsto: €{ob['gap_previsto']:.0f} → {ob['stato']}"
            )
    else:
        lines.append("  (nessun obiettivo impostato)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 1. Chat Financial Advisor
# ---------------------------------------------------------------------------

_CHAT_SYSTEM = """Sei un assistente finanziario personale preciso e diretto.
Hai accesso ai dati REALI dell'utente nel contesto fornito.
Il contesto include: ogni singola transazione (con data esatta, categoria, dettaglio, importo
e ranking nel mese/anno), riepiloghi mensili/annuali, top spese, ricorrenti e finanziamenti.

=== LINGUA E FORMATO ===
- Rispondi SEMPRE in italiano.
- Formato importi: € X.XXX,XX (es. € 1.200,00)
- Risposte concise (max 150 parole) salvo analisi approfondite richieste.
- Non inventare dati non presenti nel contesto.

=== SALDO E DISPONIBILITÀ ===
- Il campo "SALDO REALE TOTALE CONTI" è il saldo vero dei conti bancari dell'utente.
  Usalo SEMPRE per domande tipo "posso permettermi X", "quanto ho disponibile", "ho abbastanza".
- NON usare mai "Saldo calcolato da movimenti" per calcoli di affordability.
- Per calcolare cosa rimane dopo le spese fisse del mese:
  saldo_netto = saldo_reale_totale - (uscite_mese_corrente_già_pagate) - (ricorrenti_non_ancora_pagate_del_mese)
  Poi confronta saldo_netto con il costo dell'acquisto.

=== DOMANDE SU SPESE SPECIFICHE ===
- "Spesa più alta a [mese]": nella sezione "Top spese" trova rank_nel_mese=1 per quel mese.
  Indica data esatta, categoria, dettaglio e importo.
- "Tutte le spese di [categoria] a [mese/anno]": filtra l'elenco movimenti per anno+mese+categoria.
  Elenca ogni transazione con data, dettaglio e importo.
- "Spese duplicate" o "stessa voce nello stesso mese": due transazioni sono distinte se hanno
  date diverse — elencale separatamente con data e importo di ciascuna.
- "Quanto ho speso in [dettaglio] (es. Moto, Ristoranti/Bar)": filtra per campo dettaglio
  nell'elenco movimenti, somma gli importi nel periodo richiesto.

=== DOMANDE SU PERIODI ===
- "Questo mese" = mese e anno indicati nei KPI mese corrente.
- "Mese scorso" = mese precedente rispetto al mese corrente indicato nei KPI.
- Se il periodo è negli ultimi 24 mesi, i dati ci sono — non dire mai "non ho dati".
- Se il periodo è oltre i 24 mesi, comunicalo esplicitamente.
- Per confronti anno su anno usa la sezione "Riepilogo annuale per categoria".

=== PROGRAMMARE UNA SPESA ("tra quanto posso permettermi X") ===
- Calcola: mesi_necessari = costo_X / risparmio_medio_3mesi
- Arrotonda per eccesso e indica il mese/anno in cui potrebbe acquistare.
- Esempio: "A questo ritmo di risparmio potresti permettertelo entro [N] mesi, indicativamente a [mese anno]."
- Se il saldo attuale è già sufficiente, dillo subito.

=== DOMANDE SU FINANZIAMENTI ===
- Usa la sezione "Finanziamenti attivi" per rate, debito residuo, mesi rimanenti.
- La rata mensile del finanziamento è già inclusa nelle uscite mensili — non sommarla due volte.

=== RISPARMIO E REGOLA 50/30/20 ===
- Usa i riepiloghi mensili per categoria (NECESSITÀ, SVAGO, INVESTIMENTI) per confrontare
  la spesa effettiva con il budget teorico.
- Tasso di risparmio ideale: ≥20%. Se è sotto, segnalalo.

=== SCENARI WHAT-IF ("cosa succede se...") ===
Quando l'utente descrive un cambiamento futuro (nuovo lavoro, trasloco, acquisto importante,
fine di un finanziamento, aumento stipendio, ecc.), esegui questa analisi:

1. NUOVO SCENARIO: identifica le variabili che cambiano (entrate, uscite fisse, ricorrenti).
2. DELTA: calcola la differenza rispetto alla situazione attuale.
   - Nuovo risparmio mensile = nuove_entrate - (uscite_fisse_invariate + nuove_uscite)
   - Confronta con risparmio_medio_3mesi attuale.
3. IMPATTO: indica se il cambiamento migliora o peggiora la situazione in 3 aree:
   - Liquidità mensile (risparmio)
   - Sostenibilità spese fisse (finanziamenti + ricorrenti vs nuove entrate)
   - Obiettivi (es. "con il nuovo stipendio potresti permetterti X in N mesi invece di M")
4. SOGLIA DI RISCHIO: segnala se le spese fisse (finanziamenti + ricorrenti) superano
   il 50% delle nuove entrate.

"""

def chat_financial_advisor(
    user_message: str,
    financial_context: str,
    chat_history: list[dict] | None = None,
) -> str:
    """
    Risponde a una domanda finanziaria dell'utente.

    Parametri
    ----------
    user_message       : domanda dell'utente in linguaggio naturale
    financial_context  : output di build_financial_context()
    chat_history       : lista di {"role": "user"|"assistant", "content": str}
                         per mantenere il contesto della conversazione

    Ritorna
    -------
    Risposta testuale del modello.

    Esempi di domande supportate
    ----------------------------
    - "Quanto ho speso questo mese rispetto al mese scorso?"
    - "Posso permettermi un iPhone da 1200€ questo mese?"
    - "Perché ho speso di più in Svago a marzo?"
    - "Sto rispettando la regola 50/30/20?"
    - "Quanto mi rimane dopo le spese fisse?"
    """
    # Costruiamo lo storico conversazione come testo
    history_text = ""
    if chat_history:
        history_lines = []
        for turn in chat_history[-6:]:  # ultimi 6 turni per stare nei limiti token
            role = "Utente" if turn["role"] == "user" else "Assistente"
            history_lines.append(f"{role}: {turn['content']}")
        history_text = "\n".join(history_lines) + "\n\n"

    user_prompt = (
        f"### Dati finanziari dell'utente\n{financial_context}\n\n"
        f"### Storico conversazione\n{history_text}"
        f"### Domanda dell'utente\n{user_message}"
    )

    risposta = _call_gemini(_CHAT_SYSTEM, user_prompt)
    if risposta and risposta.strip():
        return risposta
    return (
        "L'assistente AI al momento non è disponibile per limite quota o servizio temporaneamente occupato. "
        "Riprova tra poco."
    )


# ---------------------------------------------------------------------------
# 2. Analisi Predittiva e Rilevamento Anomalie — sistema adattivo multi-segnale
# ---------------------------------------------------------------------------
#
# ARCHITETTURA:
#   Python rileva  →  calcola segnali statistici sui dati reali dell'utente
#   Gemini interpreta  →  riceve i segnali già calcolati, aggiunge contesto
#
# TRE FASI ADATTIVE (in base ai mesi di storico disponibili):
#   "bootstrap"      < 6 mesi  →  solo baseline semplice con soglia personalizzata
#   "apprendimento"  6-12 mesi →  + regressione lineare per rilevare trend
#   "matura"         12+ mesi  →  + confronto anno su anno per stagionalità reale
#
# In questo modo nuovi utenti ottengono risultati utili fin dal primo mese,
# mentre utenti con storico lungo beneficiano di analisi sempre più precise.
# ---------------------------------------------------------------------------

# Soglie configurabili
_SOGLIA_BASELINE_PCT  = 15.0  # variazione % minima per considerare un'anomalia
_SOGLIA_TREND_EURO    = 8.0   # crescita minima (€/mese) per considerare un trend
_SOGLIA_STD_MULTIPLO  = 1.5   # moltiplicatore della deviazione std per soglia adattiva
_MESI_TREND           = 6     # finestra mesi per la regressione lineare
_MESI_BASELINE        = 3     # mesi di riferimento per la baseline semplice
_MIN_SPESA_CATEGORIA  = 10.0  # soglia minima (€) sotto cui una categoria è ignorata


def _profilo_dati(df: pd.DataFrame) -> dict:
    """
    Analizza il DataFrame e determina quanti mesi di dati sono disponibili,
    quale fase di apprendimento è attiva e quali segnali possono essere calcolati.

    Ritorna un dict con:
      mesi_disponibili : numero di mesi con almeno una transazione
      fase             : "bootstrap" | "apprendimento" | "matura"
      has_trend        : True se ci sono 6+ mesi (regressione lineare affidabile)
      has_yoy          : True se ci sono 13+ mesi (confronto anno su anno possibile)
      mese_corrente    : mese numerico del mese più recente nel dataset
      anno_corrente    : anno del mese più recente nel dataset
      periodo_label    : stringa leggibile del periodo analizzato
    """
    periodi = df["mese"].unique()
    n = len(periodi)
    ultimo = df["mese"].max()

    if n < 6:
        fase = "bootstrap"
    elif n < 13:
        fase = "apprendimento"
    else:
        fase = "matura"

    return {
        "mesi_disponibili": n,
        "fase": fase,
        "has_trend": n >= 6,
        "has_yoy": n >= 13,
        "mese_corrente": ultimo.month,
        "anno_corrente": ultimo.year,
        "periodo_label": f"{n} mesi di storico",
    }


def _segnale_baseline(pivot: pd.DataFrame, mese_corrente_periodo) -> list[dict]:
    """
    Baseline adattiva: confronta il mese corrente con la media degli ultimi
    N mesi precedenti. La soglia non è fissa al 15% ma si adatta alla
    volatilità storica di ogni singola categoria (deviazione standard).

    Una categoria con spesa molto variabile (es. Svago) avrà una soglia
    più alta rispetto a una categoria stabile (es. Affitto), evitando
    falsi allarmi su spese naturalmente irregolari.
    """
    risultati = []

    try:
        idx = list(pivot.index).index(mese_corrente_periodo)
    except ValueError:
        idx = len(pivot) - 1

    if idx < 1:
        return []

    start = max(0, idx - _MESI_BASELINE)
    storico = pivot.iloc[start:idx]
    corrente = pivot.iloc[idx]

    for cat in corrente.index:
        curr_val = float(corrente[cat])
        vals = storico[cat].values.astype(float)

        if len(vals) == 0 or vals.mean() < _MIN_SPESA_CATEGORIA:
            continue

        media = float(vals.mean())
        std = float(vals.std()) if len(vals) > 1 else 0.0
        variazione_pct = ((curr_val - media) / media) * 100

        # Soglia adattiva: almeno _SOGLIA_BASELINE_PCT%,
        # ma si alza se la categoria è storicamente volatile
        soglia = _SOGLIA_BASELINE_PCT
        if std > 0 and media > 0:
            volatilita_relativa = (std / media) * 100 * _SOGLIA_STD_MULTIPLO
            soglia = max(soglia, volatilita_relativa)

        if abs(variazione_pct) >= soglia:
            risultati.append({
                "segnale": "baseline",
                "categoria": cat,
                "valore_corrente_eur": round(curr_val, 2),
                "media_storica_eur": round(media, 2),
                "std_storica_eur": round(std, 2),
                "soglia_effettiva_pct": round(soglia, 1),
                "variazione_pct": round(variazione_pct, 1),
                "mesi_campione": len(vals),
            })

    return risultati


def _segnale_trend(pivot: pd.DataFrame, mese_corrente_periodo) -> list[dict]:
    """
    Regressione lineare sugli ultimi _MESI_TREND mesi per ogni categoria.
    Rileva crescite o cali graduali che la baseline non coglie perché
    ogni singolo mese sembra "normale" rispetto al precedente.

    La pendenza (slope) in €/mese indica quanto la spesa sta crescendo
    o diminuendo mediamente ogni mese.
    Richiede almeno 4 punti per essere statisticamente significativa.
    """
    risultati = []

    try:
        idx = list(pivot.index).index(mese_corrente_periodo)
    except ValueError:
        idx = len(pivot) - 1

    start = max(0, idx - _MESI_TREND + 1)
    finestra = pivot.iloc[start:idx + 1]

    if len(finestra) < 4:
        return []

    x = np.arange(len(finestra), dtype=float)

    for cat in finestra.columns:
        y = finestra[cat].values.astype(float)

        if y.mean() < _MIN_SPESA_CATEGORIA:
            continue

        try:
            slope, _ = np.polyfit(x, y, 1)
        except Exception:
            continue

        if abs(slope) >= _SOGLIA_TREND_EURO:
            var_pct = float((y[-1] - y[0]) / y[0] * 100) if y[0] > 0 else 0.0
            risultati.append({
                "segnale": "trend",
                "categoria": cat,
                "crescita_mensile_eur": round(float(slope), 2),
                "direzione": "crescita" if slope > 0 else "calo",
                "media_periodo_eur": round(float(y.mean()), 2),
                "primo_mese_eur": round(float(y[0]), 2),
                "ultimo_mese_eur": round(float(y[-1]), 2),
                "variazione_totale_pct": round(var_pct, 1),
                "mesi_analizzati": len(finestra),
            })

    return risultati


def _segnale_yoy(
    uscite_df: pd.DataFrame,
    mese_corrente: int,
    anno_corrente: int,
) -> list[dict]:
    """
    Confronto anno su anno (Year-over-Year): stesso mese dell'anno corrente
    vs stesso mese dell'anno precedente.

    Questo è il segnale più preciso per la STAGIONALITÀ REALE dell'utente:
    se ogni dicembre spendi €600 in regali, il confronto dicembre/dicembre
    non genera falsi alert, mentre la baseline (vs media annuale) li genererebbe.

    Richiede almeno 13 mesi di storico.
    """
    risultati = []
    anno_precedente = anno_corrente - 1

    df_curr = uscite_df[
        (uscite_df["data"].dt.month == mese_corrente) &
        (uscite_df["data"].dt.year == anno_corrente)
    ]
    df_prev = uscite_df[
        (uscite_df["data"].dt.month == mese_corrente) &
        (uscite_df["data"].dt.year == anno_precedente)
    ]

    if df_curr.empty or df_prev.empty:
        return []

    totali_curr = df_curr.groupby("categoria")["importo"].sum().abs()
    totali_prev = df_prev.groupby("categoria")["importo"].sum().abs()
    tutte_cat = set(totali_curr.index) | set(totali_prev.index)

    for cat in tutte_cat:
        curr = float(totali_curr.get(cat, 0.0))
        prev = float(totali_prev.get(cat, 0.0))

        if prev < _MIN_SPESA_CATEGORIA:
            continue

        variazione_pct = ((curr - prev) / prev) * 100

        if abs(variazione_pct) >= _SOGLIA_BASELINE_PCT:
            risultati.append({
                "segnale": "yoy",
                "categoria": cat,
                "anno_corrente": anno_corrente,
                "anno_precedente": anno_precedente,
                "mese": mese_corrente,
                "valore_anno_corrente_eur": round(curr, 2),
                "valore_anno_precedente_eur": round(prev, 2),
                "variazione_pct": round(variazione_pct, 1),
            })

    return risultati


def _build_prompt_anomalie(
    segnali: dict[str, list],
    profilo: dict,
    df_ric: pd.DataFrame | None = None,
) -> str:
    """
    Costruisce il prompt da inviare a Gemini con tutti i segnali calcolati.
    Il prompt include metadati sul profilo dati così Gemini può calibrare
    la propria interpretazione in base alla maturità dello storico.
    """
    lines = []

    # Contesto sulla qualità dei dati — Gemini deve sapere di cosa dispone
    lines.append(f"## Profilo dati utente")
    lines.append(f"- Mesi di storico disponibili: {profilo['mesi_disponibili']}")
    lines.append(f"- Fase: {profilo['fase']}")
    lines.append(f"- Mese analizzato: {profilo['mese_corrente']}/{profilo['anno_corrente']}")
    lines.append(f"- Segnali calcolati: {', '.join(k for k, v in segnali.items() if v)}")
    if profilo['fase'] == 'bootstrap':
        lines.append("- NOTA: dati limitati, interpretare con cautela e segnalarlo all'utente.")

    # Segnale 1: Baseline
    if segnali.get("baseline"):
        lines.append("\n## Segnale baseline (mese corrente vs media storica)")
        lines.append("Soglia adattiva per categoria — variazioni già filtrate statisticamente.")
        for s in segnali["baseline"]:
            lines.append(
                f"- {s['categoria']}: corrente €{s['valore_corrente_eur']}, "
                f"media €{s['media_storica_eur']} (std €{s['std_storica_eur']}), "
                f"variazione {s['variazione_pct']:+.1f}% "
                f"(soglia adattiva usata: {s['soglia_effettiva_pct']}%, "
                f"su {s['mesi_campione']} mesi)"
            )

    # Segnale 2: Trend
    if segnali.get("trend"):
        lines.append("\n## Segnale trend (regressione lineare ultimi 6 mesi)")
        lines.append("Crescita o calo graduale — ogni mese sembra normale ma la direzione è chiara.")
        for s in segnali["trend"]:
            lines.append(
                f"- {s['categoria']}: {s['direzione']} di "
                f"€{abs(s['crescita_mensile_eur']):.2f}/mese in media, "
                f"da €{s['primo_mese_eur']} a €{s['ultimo_mese_eur']} "
                f"({s['variazione_totale_pct']:+.1f}% in {s['mesi_analizzati']} mesi)"
            )

    # Segnale 3: YoY
    if segnali.get("yoy"):
        lines.append("\n## Segnale year-over-year (stesso mese anno scorso)")
        lines.append("Confronto stagionale reale — elimina i falsi alert da stagionalità nota.")
        for s in segnali["yoy"]:
            lines.append(
                f"- {s['categoria']}: {s['anno_corrente']} €{s['valore_anno_corrente_eur']} "
                f"vs {s['anno_precedente']} €{s['valore_anno_precedente_eur']}, "
                f"variazione {s['variazione_pct']:+.1f}%"
            )

    # Spese ricorrenti (contesto)
    if df_ric is not None and not df_ric.empty:
        imp_col = next((c for c in ["importo", "Importo"] if c in df_ric.columns), None)
        if imp_col:
            lines.append(f"\n## Contesto: spese ricorrenti mensili totali")
            lines.append(f"€{float(df_ric[imp_col].sum()):.2f}/mese (già incluse nei movimenti)")

    return "\n".join(lines)


_ANOMALY_SYSTEM = """Sei un analista finanziario personale. Ricevi segnali statistici
già calcolati da algoritmi Python sui dati REALI dell'utente.
Il tuo compito è SOLO interpretare e classificare questi segnali — NON ricalcolarli.

REGOLE:
- Per ogni segnale ricevuto, produci UNO o ZERO oggetti JSON.
- Non inventare anomalie non presenti nei segnali.
- Se la fase è "bootstrap" (pochi mesi di dati), abbassa la gravità di un livello
  e aggiungi nel messaggio che il dato si consoliderà nel tempo.
- Il segnale "yoy" è il più affidabile per la stagionalità: se una variazione
  baseline è già spiegata dal yoy (stessa variazione l'anno scorso), abbassa
  la gravità o non includerla.
- Il segnale "trend" con direzione "calo" è generalmente positivo (info), non negativo.
- Usa "alert" solo per variazioni yoy > 30% o trend con crescita > €30/mese.
- Usa "warning" per variazioni significative non spiegabili dalla stagionalità.
- Usa "info" per trend lievi o cali di spesa.

Per ogni anomalia restituisci:
{
  "tipo": "anomalia" | "trend" | "pattern_stagionale",
  "categoria": "<nome categoria>",
  "gravita": "info" | "warning" | "alert",
  "titolo": "<titolo breve max 8 parole>",
  "messaggio": "<spiegazione specifica max 30 parole con i numeri reali>",
  "variazione_pct": <float, positivo=aumento spesa, negativo=calo>
}

Rispondi SOLO con il JSON array. Nessun testo fuori dal JSON. Se nessun segnale
è rilevante, rispondi con [].
"""


def detect_anomalies(
    df_mov: pd.DataFrame,
    df_ric: pd.DataFrame | None = None,
    df_fin: pd.DataFrame | None = None,
    reference_months: int = 3,
) -> list[dict]:
    """
    Identifica anomalie, trend e pattern stagionali con approccio adattivo.

    Il sistema si adatta automaticamente alla quantità di dati disponibili:

      Fase bootstrap (< 6 mesi)
        Calcola: baseline con soglia adattiva per categoria
        Utile per: rilevare picchi evidenti fin dal primo mese

      Fase apprendimento (6-12 mesi)
        Calcola: baseline + regressione lineare (trend)
        Utile per: identificare crescite graduali che mese per mese sembrano normali

      Fase matura (12+ mesi)
        Calcola: baseline + trend + confronto anno su anno
        Utile per: stagionalità reale dell'utente, eliminazione falsi alert natalizi/estivi

    In tutte le fasi Python rileva (calcoli statistici sui dati reali),
    Gemini interpreta (contestualizza e assegna gravità).

    Parametri
    ----------
    df_mov           : DataFrame movimenti — colonne attese: data, tipo, categoria, importo
    df_ric           : DataFrame spese ricorrenti (opzionale, per contesto a Gemini)
    df_fin           : DataFrame finanziamenti (opzionale, non usato nel rilevamento)
    reference_months : mesi baseline per la fase bootstrap (default 3)

    Ritorna
    -------
    list[dict] — lista anomalie. Ogni dict ha:
      tipo, categoria, gravita, titolo, messaggio, variazione_pct
    Lista vuota se nessuna anomalia o in caso di errore.
    """
    if df_mov is None or df_mov.empty:
        return []

    try:
        # ── Normalizzazione DataFrame ────────────────────────────────────────
        df = df_mov.copy()
        df.columns = [c.lower() for c in df.columns]
        df["data"] = pd.to_datetime(df.get("data"), errors="coerce")
        df = df[df["data"].notna()].copy()
        df["mese"] = df["data"].dt.to_period("M")
        df["importo"] = pd.to_numeric(df.get("importo", 0), errors="coerce").fillna(0.0)
        df["tipo"] = df.get("tipo", pd.Series(dtype=str)).astype(str).str.upper().str.strip()
        df["categoria"] = df.get("categoria", pd.Series(dtype=str)).astype(str).str.upper().str.strip()

        uscite = df[df["tipo"].str.contains("USCITA", na=False)].copy()
        if uscite.empty:
            return []

        # ── Profilo dati: determina la fase ─────────────────────────────────
        profilo = _profilo_dati(uscite)
        mese_curr_periodo = uscite["mese"].max()

        # ── Pivot mensile per categoria ──────────────────────────────────────
        pivot = (
            uscite.groupby(["mese", "categoria"])["importo"]
            .sum().abs()
            .unstack(fill_value=0.0)
        )

        if len(pivot) < 2:
            return []

        # ── Calcolo segnali in base alla fase ────────────────────────────────
        segnali: dict[str, list] = {
            "baseline": [],
            "trend": [],
            "yoy": [],
        }

        # Segnale baseline — sempre attivo
        segnali["baseline"] = _segnale_baseline(pivot, mese_curr_periodo)

        # Segnale trend — da fase "apprendimento" in poi
        if profilo["has_trend"]:
            segnali["trend"] = _segnale_trend(pivot, mese_curr_periodo)

        # Segnale YoY — solo in fase "matura"
        if profilo["has_yoy"]:
            segnali["yoy"] = _segnale_yoy(
                uscite,
                profilo["mese_corrente"],
                profilo["anno_corrente"],
            )

        # Nessun segnale rilevato → nessuna chiamata a Gemini (risparmio token)
        n_segnali = sum(len(v) for v in segnali.values())
        if n_segnali == 0:
            logger.info("detect_anomalies: nessun segnale rilevato, skip chiamata Gemini.")
            return []

        logger.info(
            "detect_anomalies [%s, %d mesi]: baseline=%d trend=%d yoy=%d segnali → Gemini",
            profilo["fase"],
            profilo["mesi_disponibili"],
            len(segnali["baseline"]),
            len(segnali["trend"]),
            len(segnali["yoy"]),
        )

        # ── Costruzione prompt e chiamata Gemini ─────────────────────────────
        stats_text = _build_prompt_anomalie(segnali, profilo, df_ric)

    except Exception as exc:
        logger.warning("detect_anomalies: errore pre-calcolo: %s", exc, exc_info=True)
        return []

    try:
        raw = _call_gemini(_ANOMALY_SYSTEM, stats_text)
        if not raw or not raw.strip():
            return []
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)

        anomalies = json.loads(raw)
        return anomalies if isinstance(anomalies, list) else []
    except json.JSONDecodeError as exc:
        logger.warning("detect_anomalies: risposta JSON non valida: %s", exc)
        return []
    except Exception as exc:
        logger.error("detect_anomalies: errore chiamata Gemini: %s", exc)
        return []


# ---------------------------------------------------------------------------
# 3. Report Mensile AI
# ---------------------------------------------------------------------------

_REPORT_SYSTEM = """Sei un assistente finanziario personale. Scrivi un breve report mensile
in italiano, tono caldo ma professionale.

Regole:
- Nessun saluto iniziale, nessuna formula da email, nessun titolo.
- Usa SOLO i dati presenti nel prompt.
- Non citare mesi o anni diversi da quelli esplicitamente presenti nei dati forniti.
- Se fai un confronto, indica sempre il riferimento corretto già presente nel prompt.
- Evidenzia 2-3 punti salienti con numeri reali.
- Chiudi con un suggerimento pratico e specifico in una frase.
- Lunghezza: 90-140 parole.
- Nessun markdown, solo testo scorrevole.
- Evita frasi generiche tipo "è importante risparmiare".
"""


def generate_monthly_report(
    kpi_current: dict[str, Any],
    kpi_previous: dict[str, Any],
    anomalies: list[dict] | None = None,
    month_label: str = "",
) -> str:
    """
    Genera un paragrafo narrativo per l'email mensile.

    Parametri
    ----------
    kpi_current  : KPI del mese appena concluso (da calcola_kpi_dashboard)
    kpi_previous : KPI del mese precedente (per il confronto)
    anomalies    : lista di anomalie da detect_anomalies() (opzionale)
    month_label  : es. "Marzo 2025" (opzionale, per personalizzare il testo)

    Ritorna
    -------
    Paragrafo testuale pronto per essere inserito nell'email HTML.
    """
    def _fmt(val, prefix="€"):
        try:
            return f"{prefix}{float(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            return str(val)

    # Costruiamo il prompt con dati concreti
    lines = [f"## Dati mese: {month_label or 'corrente'}"]

    compare_fields = {
        "entrate_mese":    "Entrate",
        "uscite_mese":     "Uscite totali",
        "risparmio_mese":  "Risparmio",
        "tasso_risparmio": "Tasso risparmio",
        "speso_necessita": "Speso necessità",
        "speso_svago":     "Speso svago",
        "speso_investimenti": "Speso investimenti",
    }

    for key, label in compare_fields.items():
        curr = kpi_current.get(key)
        prev = kpi_previous.get(key)
        if curr is not None and prev is not None:
            try:
                diff_pct = ((float(curr) - float(prev)) / float(prev)) * 100 if float(prev) != 0 else 0
                suffix = "%" if "tasso" in key else ""
                lines.append(
                    f"- {label}: {_fmt(curr)}{suffix} "
                    f"(mese precedente: {_fmt(prev)}{suffix}, variazione: {diff_pct:+.1f}%)"
                )
            except Exception:
                lines.append(f"- {label}: {curr}")

    if anomalies:
        lines.append("\n## Anomalie rilevate questo mese")
        for a in anomalies[:3]:  # max 3 anomalie nel report
            lines.append(f"- [{a.get('gravita','').upper()}] {a.get('titolo','')}: {a.get('messaggio','')}")

    data_prompt = "\n".join(lines)

    try:
        raw = _call_gemini(_REPORT_SYSTEM, data_prompt)
        if raw and raw.strip():
            return raw
    except Exception as exc:
        logger.error("Errore generazione report mensile: %s", exc)

    # Fallback: testo generico senza AI
    uscite = kpi_current.get("uscite_mese", 0)
    risparmio = kpi_current.get("risparmio_mese", 0)
    return (
        f"Questo mese hai registrato uscite per {_fmt(uscite)} "
        f"e un risparmio di {_fmt(risparmio)}. "
        "Controlla la dashboard per il dettaglio completo."
    )
