import argparse
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import Database as db
import logiche as log
from gmail_sender import send_email

def _eur(value):
  """Formato canonico euro con separatore italiano.

  Viene usato sia nelle email sia dall'interfaccia web, quindi usiamo il
  simbolo "€" anziché la stringa ISO "EUR" come faceva il vecchio helper.
  """
  try:
      amount = float(value)
  except Exception:
      amount = 0.0
  text = f"{amount:,.2f}"
  text = text.replace(",", "X").replace(".", ",").replace("X", ".")
  return f"€ {text}"


def _prepare_movimenti_df(df_mov):
  if df_mov is None or df_mov.empty:
      return pd.DataFrame(columns=["Data", "Tipo", "Categoria", "Dettaglio", "Importo", "Note"])

  df = df_mov.copy()
  df.columns = [str(c).capitalize() for c in df.columns]
  if "Data" not in df.columns:
      df["Data"] = pd.NaT
  if "Tipo" not in df.columns:
      df["Tipo"] = ""
  if "Categoria" not in df.columns:
      df["Categoria"] = ""
  if "Dettaglio" not in df.columns:
      df["Dettaglio"] = ""
  if "Importo" not in df.columns:
      df["Importo"] = 0.0
  if "Note" not in df.columns:
      df["Note"] = ""

  df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
  df = df[df["Data"].notna()].copy()
  df["Tipo"] = df["Tipo"].astype(str).str.upper().str.strip().replace(
      {"ENTRATE": "ENTRATA", "USCITE": "USCITA"}
  )
  df["Categoria"] = df["Categoria"].astype(str).str.upper().str.strip()
  df["Importo"] = pd.to_numeric(df["Importo"], errors="coerce").fillna(0.0)
  return df


def _prepare_finanziamenti_df(df_fin):
  if df_fin is None or df_fin.empty:
      return pd.DataFrame()
  return df_fin.rename(
      columns={
          "nome": "Nome Finanziamento",
          "capitale_iniziale": "Capitale",
          "taeg": "TAEG",
          "durata_mesi": "Durata",
          "data_inizio": "Data Inizio",
          "giorno_scadenza": "Giorno Scadenza",
          "rate_pagate": "Rate Pagate",
      }
  ).copy()


def _prepare_ricorrenti_df(df_ric):
  if df_ric is None or df_ric.empty:
      return pd.DataFrame()
  return df_ric.rename(
      columns={
          "descrizione": "Descrizione",
          "importo": "Importo",
          "giorno_scadenza": "Giorno Scadenza",
          "frequenza_mesi": "Frequenza",
          "data_inizio": "Data Inizio",
          "data_fine": "Data Fine",
      }
  ).copy()

def _calendario_per_mesi(df_ric, df_fin, df_mov, year_month_pairs):
  frames = []
  for year, month in sorted(set(year_month_pairs)):
      cal = log.calcolo_spese_ricorrenti(df_ric, df_fin, df_mov, month, year)
      if cal is not None and not cal.empty:
          frames.append(cal)
  if not frames:
      return pd.DataFrame(columns=["Spesa", "Importo", "Data", "Stato", "Origine", "Frequenza"])

  df = pd.concat(frames, ignore_index=True)
  df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
  df = df[df["Data"].notna()].copy()
  if "Stato" not in df.columns:
      df["Stato"] = ""
  if "Origine" not in df.columns:
      df["Origine"] = ""
  if "Frequenza" not in df.columns:
      df["Frequenza"] = ""
  df["Importo"] = pd.to_numeric(df["Importo"], errors="coerce").fillna(0.0)
  df["DataSolo"] = df["Data"].dt.date
  return df


def _format_weekly_body(df_week, start_week, end_week):
    lines = []
    # Ordiniamo per data e spesa
    df_sorted = df_week.sort_values(by=["Data", "Spesa"])
    
    for _, row in df_sorted.iterrows():
        # Formattazione data (es: 27/02)
        data_dt = row["Data"] if hasattr(row["Data"], "strftime") else pd.to_datetime(row["Data"])
        dataF = data_dt.strftime("%d/%m")
        
        nome = row.get('Spesa') or row.get('spesa') or 'Spesa'
        importo = _eur(row.get('Importo') or row.get('importo') or 0)
        
        # Riga singola con emoji e grassetto
        lines.append(f"▫️ <b>[{dataF}] {nome}</b> → {importo}")

    elenco_settimanale = "<br>".join(lines)
    totale_settimana = _eur(df_week["Importo"].sum())

    # Costruzione del corpo email
    body = (
        "<div style='font-family: sans-serif; color: #333;'>"
        "Buongiorno!<br><br>"
        "Ecco una panoramica dei pagamenti pianificati per i prossimi 7 giorni, "
        "così potrai organizzare al meglio il tuo budget:<br><br>"
        f"{elenco_settimanale}<br>"
        "<hr style='border: 0; border-top: 1px solid #eee; margin: 20px 0;'>"
        f"💰 <b>Totale della settimana: {totale_settimana}</b><br><br>"
        "Buona settimana e buon lavoro!<br>"
        "Il tuo assistente automatico 🤖"
        "</div>"
    )
    return body

def _format_due_body(df_due, due_date):
    lines = []
    # Ordiniamo per sicurezza
    df_sorted = df_due.sort_values(by=["Data", "Spesa"]) if "Data" in df_due.columns else df_due
    
    for _, row in df_sorted.iterrows():
        nome = row.get('Spesa') or row.get('spesa') or 'Spesa'
        importo = _eur(row.get('Importo') or row.get('importo') or 0)
        # Usiamo il grassetto <b> e l'emoji 📌
        lines.append(f"📌 <b>{nome}</b>: {importo}")

    elenco_spese = "<br>".join(lines)
    
    body = (
        "<div style='font-family: sans-serif; color: #333;'>"
        "Ciao!<br><br>"
        f"Ti invio un breve promemoria: domani, <b>{due_date.strftime('%d/%m/%Y')}</b>, "
        "sono previsti i seguenti pagamenti:<br><br>"
        f"{elenco_spese}<br><br>"
        "Ti auguro una buona giornata,<br>"
        "il tuo assistente automatico 🤖"
        "</div>"
    )
    return body

def _is_unpaid(df):
  """Return True for rows that still need payment.

    Consideriamo "DA PAGARE" e "IN SCADENZA" come stati che richiedono attenzione.
  """
  stato = df["Stato"].astype(str)
  return stato.str.contains("DA PAGARE", case=False, na=False) | \
         stato.str.contains("IN SCADENZA", case=False, na=False)

def _send_weekly_notifications(recipients, df_calendar, today, dry_run=False):
  sent = 0
  if today.weekday() != 0:
      return sent

  start_week = today
  end_week = start_week + timedelta(days=6)
  df_week = df_calendar[
      (df_calendar["DataSolo"] >= start_week)
      & (df_calendar["DataSolo"] <= end_week)
      & _is_unpaid(df_calendar)
  ].copy()
  if df_week.empty:
      return sent

  df_week = df_week.drop_duplicates(subset=["Spesa", "Importo", "DataSolo", "Origine"])
  iso_year, iso_week, _ = start_week.isocalendar()
  # soggetto fisso come nello script di Google
  subject = "📅 Riepilogo Spese della Settimana"
  body = _format_weekly_body(df_week, start_week, end_week)

  for recipient in recipients:
      key_week = f"WEEKLY|{iso_year}-W{iso_week:02d}|{recipient.lower()}"
      if db.notifica_scadenza_gia_inviata(key_week):
          continue

      if dry_run:
          print(f"[DRY-RUN] WEEKLY -> {recipient} ({len(df_week)} righe)")
          sent += 1
          continue

      ok, msg = send_email(recipient, subject, body)
      print(f"[WEEKLY] {recipient}: {msg}")
      if ok:
          db.registra_notifica_scadenza(key_week, recipient, end_week.isoformat())
          sent += 1
  return sent


def _send_due_notifications(recipients, df_calendar, today, dry_run=False):
  sent = 0
  due_date = today + timedelta(days=1)
  df_due = df_calendar[
      (df_calendar["DataSolo"] == due_date) & _is_unpaid(df_calendar)
  ].copy()
  if df_due.empty:
      return sent

  subject = "⏰ Promemoria: Scadenza pagamenti domani"

  for recipient in recipients:
      pending_rows = []
      for _, row in df_due.iterrows():
          key = (
              "DUE1|"
              f"{recipient.lower()}|"
              f"{str(row.get('Origine', '')).strip().upper()}|"
              f"{str(row.get('Spesa', '')).strip().upper()}|"
              f"{due_date.isoformat()}|"
              f"{float(row.get('Importo', 0)):.2f}"
          )
          if not db.notifica_scadenza_gia_inviata(key):
              pending_rows.append((key, row))

      if not pending_rows:
          continue

      df_pending = pd.DataFrame([item[1] for item in pending_rows])
      body = _format_due_body(df_pending, due_date)
      if dry_run:
          print(f"[DRY-RUN] DUE1 -> {recipient} ({len(df_pending)} righe)")
          sent += 1
          continue

      ok, msg = send_email(recipient, subject, body)
      print(f"[DUE1] {recipient}: {msg}")
      if ok:
          for key, _ in pending_rows:
              db.registra_notifica_scadenza(key, recipient, due_date.isoformat())
          sent += 1
  return sent


# --- IN gmail_sender.py (o il tuo file worker notifiche) ---

def run(today=None, tz_name="Europe/Rome", dry_run=False):
  timezone = ZoneInfo(tz_name)
  today = today or datetime.now(timezone).date()

  db.inizializza_db()
  
  # Recuperiamo la lista di tutti gli utenti registrati
  recipients = db.lista_destinatari_notifiche()
  if not recipients:
      print("Nessun destinatario notifiche disponibile.")
      return {"weekly": 0, "day_before": 0, "total": 0}

  total_sent = {"weekly": 0, "day_before": 0}

  # --- MODIFICA FONDAMENTALE: Loop per ogni utente ---
  for recipient in recipients:
      print(f"Elaborazione notifiche per: {recipient}")
      
      # Carichiamo i dati SPECIFICI per questo utente
      df_mov = _prepare_movimenti_df(db.carica_dati(recipient)) # <--- Modifica qui
      df_ric = _prepare_ricorrenti_df(db.carica_spese_ricorrenti(recipient)) # <--- Modifica qui
      df_fin = _prepare_finanziamenti_df(db.carica_finanziamenti(recipient)) # <--- Modifica qui

      month_pairs = {(today.year, today.month), ((today + timedelta(days=1)).year, (today + timedelta(days=1)).month)}
      if today.weekday() == 0:
          week_dates = [today + timedelta(days=i) for i in range(7)]
          month_pairs.update((d.year, d.month) for d in week_dates)

      df_calendar = _calendario_per_mesi(df_ric, df_fin, df_mov, month_pairs)
      
      if df_calendar.empty:
          continue

      # Passiamo recipient singolo alle funzioni di notifica
      weekly_sent = _send_weekly_notifications([recipient], df_calendar, today, dry_run=dry_run)
      due_sent = _send_due_notifications([recipient], df_calendar, today, dry_run=dry_run)
      
      total_sent["weekly"] += weekly_sent
      total_sent["day_before"] += due_sent

  print(f"Notifiche inviate: weekly={total_sent['weekly']}, day_before={total_sent['day_before']}")
  return {"weekly": total_sent["weekly"], "day_before": total_sent["day_before"], "total": sum(total_sent.values())}

def main():
  parser = argparse.ArgumentParser(description="Worker notifiche email Personal Budget")
  parser.add_argument("--today", type=str, default="", help="Data di riferimento YYYY-MM-DD (opzionale)")
  parser.add_argument("--timezone", type=str, default="Europe/Rome", help="Timezone IANA, es. Europe/Rome")
  parser.add_argument("--dry-run", action="store_true", help="Non invia email reali")
  args = parser.parse_args()

  forced_today = None
  if args.today:
      forced_today = datetime.strptime(args.today, "%Y-%m-%d").date()

  run(today=forced_today, tz_name=args.timezone, dry_run=args.dry_run)


if __name__ == "__main__":
  main()


