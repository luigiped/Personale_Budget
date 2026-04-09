"""
utils/user_settings.py
-----------------------
Gestione impostazioni personalizzabili (multi-tenant):
  • Voci di dettaglio custom per categoria (NECESSITÀ, SVAGO, INVESTIMENTI)
  • Percentuali budget personalizzate (override del 50/30/20)

Storage: tabella asset_settings già esistente (chiave, user_email, valore_testo).
  - chiave "impost_custom_dettagli"    → valore_testo = JSON dict[str, list[str]]
  - chiave "impost_percentuali_budget" → valore_testo = JSON dict[str, float]

Nessuna nuova tabella richiesta.
"""

from __future__ import annotations
import json
import logging
from typing import Any

from utils.constants import STRUTTURA_CATEGORIE as _DEF_STRUTTURA
from utils.constants import PERCENTUALI_BUDGET  as _DEF_PERCENTUALI

logger = logging.getLogger(__name__)

_KEY_CUSTOM_DETTAGLI = "impost_custom_dettagli"
_KEY_PERC_BUDGET     = "impost_percentuali_budget"

CATEGORIE_MODIFICABILI: list[str] = ["NECESSITÀ", "SVAGO", "INVESTIMENTI"]
_MAX_DETTAGLIO_LEN = 80


def _db():
    import Database as _m  # noqa: PLC0415
    return _m


def _leggi_json(chiave: str, user_email: str) -> Any | None:
    try:
        with _db().connetti_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT valore_testo FROM asset_settings "
                "WHERE chiave = %s AND user_email = %s LIMIT 1",
                (chiave, user_email),
            )
            row = cur.fetchone()
            cur.close()
        if row and row[0]:
            return json.loads(row[0])
    except Exception as exc:
        logger.warning("user_settings._leggi_json('%s'): %s", chiave, exc)
    return None


def _scrivi_json(chiave: str, valore: Any, user_email: str) -> bool:
    try:
        payload = json.dumps(valore, ensure_ascii=False)
        with _db().connetti_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO asset_settings (chiave, user_email, valore_numerico, valore_testo)
                VALUES (%s, %s, NULL, %s)
                ON CONFLICT (chiave, user_email) DO UPDATE
                    SET valore_testo    = EXCLUDED.valore_testo,
                        valore_numerico = NULL
                """,
                (chiave, user_email, payload),
            )
            cur.close()
        return True
    except Exception as exc:
        logger.error("user_settings._scrivi_json('%s'): %s", chiave, exc)
        return False


def _normalizza_dettaglio(dettaglio: str) -> str:
    """Normalizza una voce custom rimuovendo spazi e caratteri di controllo."""
    raw = str(dettaglio or "").strip()
    cleaned = "".join(ch for ch in raw if ch.isprintable())
    return " ".join(cleaned.split())


# ===========================================================================
# API PUBBLICA — Struttura categorie
# ===========================================================================

def get_custom_dettagli(user_email: str) -> dict[str, list[str]]:
    raw = _leggi_json(_KEY_CUSTOM_DETTAGLI, user_email)
    if isinstance(raw, dict):
        return {cat: list(raw.get(cat, [])) for cat in CATEGORIE_MODIFICABILI}
    return {cat: [] for cat in CATEGORIE_MODIFICABILI}


def get_struttura_categorie(user_email: str) -> dict[str, list[str]]:
    custom = get_custom_dettagli(user_email)
    result: dict[str, list[str]] = {}
    for cat, voci_default in _DEF_STRUTTURA.items():
        if cat in CATEGORIE_MODIFICABILI:
            default_lower = {v.lower() for v in voci_default}
            aggiunte = [
                v for v in custom.get(cat, [])
                if v.strip().lower() not in default_lower
            ]
            result[cat] = list(voci_default) + aggiunte
        else:
            result[cat] = list(voci_default)
    return result


def aggiungi_dettaglio(categoria: str, dettaglio: str, user_email: str) -> tuple[bool, str]:
    dettaglio = _normalizza_dettaglio(dettaglio)
    if not dettaglio:
        return False, "Il nome della voce non può essere vuoto."
    if len(dettaglio) > _MAX_DETTAGLIO_LEN:
        return False, f"Il nome della voce non può superare {_MAX_DETTAGLIO_LEN} caratteri."
    if categoria not in CATEGORIE_MODIFICABILI:
        return False, f"La categoria '{categoria}' non è modificabile."
    struttura = get_struttura_categorie(user_email)
    if dettaglio.lower() in {v.lower() for v in struttura.get(categoria, [])}:
        return False, f"'{dettaglio}' esiste già in {categoria}."
    custom = get_custom_dettagli(user_email)
    custom[categoria].append(dettaglio)
    ok = _scrivi_json(_KEY_CUSTOM_DETTAGLI, custom, user_email)
    return (True, f"✅ '{dettaglio}' aggiunto a {categoria}.") if ok \
        else (False, "Errore nel salvataggio. Controlla i log.")


def rimuovi_dettaglio(categoria: str, dettaglio: str, user_email: str) -> tuple[bool, str]:
    if categoria not in CATEGORIE_MODIFICABILI:
        return False, f"La categoria '{categoria}' non è modificabile."
    if dettaglio.lower() in {v.lower() for v in _DEF_STRUTTURA.get(categoria, [])}:
        return False, f"'{dettaglio}' è una voce predefinita e non può essere rimossa."
    custom = get_custom_dettagli(user_email)
    lista = custom.get(categoria, [])
    nuova = [v for v in lista if v.lower() != dettaglio.lower()]
    if len(nuova) == len(lista):
        return False, f"'{dettaglio}' non trovata tra le voci personalizzate."
    custom[categoria] = nuova
    ok = _scrivi_json(_KEY_CUSTOM_DETTAGLI, custom, user_email)
    return (True, f"✅ '{dettaglio}' rimossa da {categoria}.") if ok \
        else (False, "Errore nel salvataggio. Controlla i log.")


# ===========================================================================
# API PUBBLICA — Percentuali budget
# ===========================================================================

def get_percentuali_budget(user_email: str) -> dict[str, float]:
    raw = _leggi_json(_KEY_PERC_BUDGET, user_email)
    if isinstance(raw, dict):
        cats = list(_DEF_PERCENTUALI.keys())
        try:
            perc = {cat: float(raw[cat]) for cat in cats}
            if abs(sum(perc.values()) - 1.0) < 0.01:
                return perc
        except (KeyError, TypeError, ValueError):
            pass
    return dict(_DEF_PERCENTUALI)


def salva_percentuali_budget(percentuali: dict[str, float], user_email: str) -> tuple[bool, str]:
    cats = list(_DEF_PERCENTUALI.keys())
    for cat in cats:
        if cat not in percentuali:
            return False, f"Categoria '{cat}' mancante."
        if percentuali[cat] < 0:
            return False, f"Percentuale negativa per '{cat}'."
    totale = sum(percentuali[cat] for cat in cats)
    if abs(totale - 1.0) > 0.005:
        return False, f"La somma deve essere 100% (attuale: {totale * 100:.1f}%)."
    ok = _scrivi_json(_KEY_PERC_BUDGET, {cat: round(percentuali[cat], 6) for cat in cats}, user_email)
    return (True, "✅ Percentuali budget salvate.") if ok \
        else (False, "Errore nel salvataggio. Controlla i log.")


def ripristina_percentuali_default(user_email: str) -> tuple[bool, str]:
    ok = _scrivi_json(_KEY_PERC_BUDGET, dict(_DEF_PERCENTUALI), user_email)
    return (True, "✅ Percentuali ripristinate ai valori predefiniti (50 / 30 / 20).") if ok \
        else (False, "Errore nel salvataggio. Controlla i log.")
