import pandas as pd
import streamlit as st
from datetime import datetime
import io

# Konfiguration
PAUSE_START = pd.Timestamp("2025-01-01")
PAUSE_END = pd.Timestamp("2025-06-30")
STAND_DATUM = pd.Timestamp.today().normalize()
WARTEZEIT_MIN_DATUM = pd.Timestamp("2021-01-01")
STUFEN_BEITRAEGE = {
    "Stufe 1": 40,
    "Stufe 2": 80,
    "Stufe 3": 120,
    "Stufe 4": 160,
    "Stufe 5": 200,
    "Stufe 6": 240,
    "Stufe 7": 280
}

def runde_auf_monatsersten(datum):
    if pd.isnull(datum):
        return pd.NaT
    if datum.day < 15:
        return pd.Timestamp(datum.year, datum.month, 1)
    else:
        jahr = datum.year + (1 if datum.month == 12 else 0)
        monat = 1 if datum.month == 12 else datum.month + 1
        return pd.Timestamp(jahr, monat, 1)

def berechne_wartezeit(eintrittsdatum):
    if pd.isnull(eintrittsdatum):
        return pd.NaT
    berechnet = eintrittsdatum + pd.DateOffset(months=6)
    berechnet = pd.Timestamp(berechnet.year, berechnet.month, 1)
    if berechnet < WARTEZEIT_MIN_DATUM:
        return WARTEZEIT_MIN_DATUM
    return berechnet

def berechne_stufe_mit_pause(wartezeit_erfuellt_am, heute=STAND_DATUM):
    if pd.isnull(wartezeit_erfuellt_am) or wartezeit_erfuellt_am > heute:
        return "Stufe 1"
    stufe = 1
    for i in range(1, 7):
        erhöhung = wartezeit_erfuellt_am + pd.DateOffset(years=i)
        if PAUSE_START <= erhöhung <= PAUSE_END:
            erhöhung = pd.Timestamp("2025-07-01")
        if erhöhung <= heute:
            stufe += 1
        else:
            break
    return f"Stufe {min(stufe, 7)}"

def pruefe_verschiebung(stufenbeginn, stufe):
    if pd.isnull(stufenbeginn) or pd.isnull(stufe):
        return ""
    try:
        nummer = int(stufe.split()[-1])
    except:
        return ""

    for i in range(nummer - 1):  # -1, da Stufe 1 keine Erhöhung ist
        erhöhung = stufenbeginn + pd.DateOffset(years=i)
        if PAUSE_START <= erhöhung <= PAUSE_END:
            return "Verschiebung auf 01.07."
    return ""

def bereinige_beitrag(text):
    try:
        if isinstance(text, str):
            return float(text.replace("€", "").replace(",", ".").strip())
        return float(text)
    except:
        return None

def vergleiche_beitrag(soll, ist):
    if pd.isna(soll) or pd.isna(ist):
        return ""
    if round(soll, 2) > round(ist, 2):
        return "Beitrag erhöhen"
    elif round(soll, 2) < round(ist, 2):
        return "Beitrag reduzieren"
    else:
        return "Keine Aktion erforderlich"

def verarbeite_datei(uploaded_file):
    try:
        dateiname = uploaded_file.name.lower()
        if dateiname.endswith(".xlsx"):
            df = pd.read_excel(uploaded_file)
        elif dateiname.endswith(".csv"):
            df = pd.read_csv(uploaded_file, sep=None, engine='python')
        else:
            st.error("Nur .xlsx oder .csv Dateien werden unterstützt.")
            return None

        df["Diensteintrittsdatum"] = pd.to_datetime(df["Diensteintrittsdatum"], errors="coerce")
        df["Fehlermeldung"] = ""
        df.loc[df["Diensteintrittsdatum"].isna(), "Fehlermeldung"] = "Kein Diensteintrittsdatum hinterlegt"

        mask_valid = df["Diensteintrittsdatum"].notna()

        df.loc[mask_valid, "Wartezeit erfüllt am"] = df.loc[mask_valid, "Diensteintrittsdatum"].apply(berechne_wartezeit)
        df.loc[mask_valid, "Stufenbeginn am"] = df.loc[mask_valid, "Wartezeit erfüllt am"] + pd.DateOffset(months=12)
        df.loc[mask_valid, "Aktuelle Stufe"] = df.loc[mask_valid, "Wartezeit erfüllt am"].apply(berechne_stufe_mit_pause)

        df.loc[mask_valid, "Info"] = df.loc[mask_valid].apply(
            lambda row: pruefe_verschiebung(row["Stufenbeginn am"], row["Aktuelle Stufe"]),
            axis=1
        )

        df.loc[mask_valid, "Beitrag laut Stufe"] = df.loc[mask_valid, "Aktuelle Stufe"].map(STUFEN_BEITRAEGE).fillna(0)

        df["Beitrag laut Stufe (bereinigt)"] = df["Beitrag laut Stufe"].apply(bereinige_beitrag)
        df["Beitrag laut Allianz Vertrag (bereinigt)"] = df["Beitrag laut Allianz Vertrag"].apply(bereinige_beitrag)

        df["Anstehende Aktion"] = df.apply(
            lambda row: vergleiche_beitrag(row["Beitrag laut Stufe (bereinigt)"], row["Beitrag laut Allianz Vertrag (bereinigt)"]),
            axis=1
        )

        return df

    except Exception as e:
        st.error(f"Fehler bei der Verarbeitung: {e}")
        return None

# Streamlit App
st.set_page_config(page_title="bAV-Tool – Sentiris", layout="centered")
st.title("📊 bAV-Tool – Sentiris Automatisierung")

uploaded_file = st.file_uploader("Lade eine Excel- oder CSV-Datei hoch:", type=["xlsx", "csv"])

if uploaded_file:
    df = verarbeite_datei(uploaded_file)
    if df is not None:
        st.success("✅ Datei erfolgreich verarbeitet.")
        export_df = df.drop(columns=["Beitrag laut Stufe (bereinigt)", "Beitrag laut Allianz Vertrag (bereinigt)"], errors="ignore")

        st.dataframe(export_df)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl', date_format="DD.MM.YYYY") as writer:
            export_df.to_excel(writer, index=False)
        st.download_button(
            label="💾 Ergänzte Datei herunterladen",
            data=output.getvalue(),
            file_name="verarbeitet.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
