import argparse
from pathlib import Path

import pandas as pd

from Database import connetti_db, imposta_parametro, importa_csv_storici, inizializza_db


def _normalizza_tipo(series):
    return (
        series.astype(str)
        .str.upper()
        .str.strip()
        .replace({"ENTRATE": "ENTRATA", "USCITE": "USCITA"})
    )


def _saldo_da_movimenti():
    conn = connetti_db()
    try:
        df = pd.read_sql("SELECT tipo, importo FROM movimenti", conn)
    finally:
        conn.close()

    if df.empty:
        return 0.0

    df["tipo"] = _normalizza_tipo(df["tipo"])
    entrate = df[df["tipo"] == "ENTRATA"]["importo"].sum()
    uscite = df[df["tipo"] == "USCITA"]["importo"].sum()
    return float(entrate - uscite)


def _imposta_default_minimi():
    defaults_num = {
        "obiettivo_risparmio_perc": 30.0,
        "budget_mensile_base": 0.0,
        "alert_scadenza_giorni": 1.0,
    }
    defaults_txt = {
        "pac_ticker": "VNGA80",
        "email_notifiche": "",
    }
    for key, value in defaults_num.items():
        imposta_parametro(key, valore_num=value)
    for key, value in defaults_txt.items():
        imposta_parametro(key, valore_txt=value)


def _contatori_tabelle():
    conn = connetti_db()
    cur = conn.cursor()
    out = {}
    try:
        for table in [
            "movimenti",
            "asset_settings",
            "finanziamenti",
            "spese_ricorrenti",
            "notifiche_scadenze",
        ]:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            out[table] = int(cur.fetchone()[0])
    finally:
        cur.close()
        conn.close()
    return out


def _filtra_csv_esistenti(paths):
    validi = []
    mancanti = []
    for p in paths:
        path = Path(p)
        if path.exists() and path.is_file():
            validi.append(str(path))
        else:
            mancanti.append(str(path))
    return validi, mancanti


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Bootstrap Supabase: crea schema, importa CSV opzionali e imposta "
            "allineamento saldo opzionale."
        )
    )
    parser.add_argument(
        "--csv",
        nargs="*",
        default=[],
        help="Lista file CSV movimenti da importare (es: --csv '2025 - Foglio1.csv' '2026 - Foglio1.csv')",
    )
    parser.add_argument(
        "--saldo-reale",
        type=float,
        default=None,
        help="Saldo reale banca attuale per calcolo parametro 'allineamento_saldo'.",
    )
    parser.add_argument(
        "--imposta-default-minimi",
        action="store_true",
        help="Imposta solo i default minimi non personali in asset_settings.",
    )
    parser.add_argument(
        "--solo-schema",
        action="store_true",
        help="Crea/aggiorna solo lo schema su Supabase senza import CSV.",
    )
    args = parser.parse_args()

    print("Inizializzazione schema Supabase...")
    inizializza_db()
    print("Schema pronto.")

    totale_importate = 0
    if not args.solo_schema and args.csv:
        validi, mancanti = _filtra_csv_esistenti(args.csv)
        if mancanti:
            print(f"Attenzione: file non trovati: {', '.join(mancanti)}")
        if validi:
            print("Import CSV in corso...")
            totale_importate = importa_csv_storici(validi)
            print(f"Import completato: {totale_importate} transazioni.")
        else:
            print("Nessun CSV valido da importare.")

    if args.imposta_default_minimi:
        _imposta_default_minimi()
        print("Default minimi impostati in asset_settings.")

    if args.saldo_reale is not None:
        saldo_calcolato = _saldo_da_movimenti()
        differenza = float(args.saldo_reale) - saldo_calcolato
        imposta_parametro("allineamento_saldo", valore_num=differenza)
        print(
            "Allineamento saldo impostato: "
            f"saldo_calcolato={saldo_calcolato:.2f} | saldo_reale={args.saldo_reale:.2f} | "
            f"differenza={differenza:.2f}"
        )

    counts = _contatori_tabelle()
    print("--- Stato tabelle ---")
    for table, count in counts.items():
        print(f"{table}: {count}")
    print("Bootstrap completato.")


if __name__ == "__main__":
    main()
