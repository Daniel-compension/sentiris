import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO

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

# Hilfsfunktionen
def runde_auf_monatsersten(datum):
    if datum.day < 15:
        return pd.Timestamp(datum.year, datum.month, 1)
    else:
        jahr = datum.year + (1 if datum.month == 12 else 0)
        monat = 1 if datum.month == 12 else datum.month + 1
        return pd.Timestamp(jahr, monat, 1)

def berechne_wartezeit(datum):
    if pd.isnull(datum):
        return pd.NaT
    gerundet = runde_auf_monatsersten(datum)
    erfuellt = gerundet + pd.DateOffset(months=6)
    return max(erfuellt, WARTEZEIT_MIN_DATUM)

def berechne_stufe(wartezeit, heute=STAND_DATUM):
    if pd.isnull(wartezeit) or wartezeit > heute:
        return "Stufe 1"
    stufe = 1
    for i in range(1, 7):
        erhöhung = wartezeit + pd.DateOffset(years=i)
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
    for i in range(0, 7 - nummer + 1):
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

# Streamlit GUI
st.set_page_config(page_title="Sentiris bAV-Tool", layout="centered")
st.title("📊 Sentiris bAV – Automatisierungstool")

st.write("Lade eine Excel- oder CSV-Datei hoch:")

uploaded_file = st.file_uploader("Datei hochladen", type=["xlsx", "csv"])

if uploaded_file:
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file, sep=None, engine='python')
        else:
            df = pd.read_excel(uploaded_file)

        df["Diensteintrittsdatum"] = pd.to_datetime(df["Diensteintrittsdatum"], errors="coerce")
        df["Fehlermeldung"] = ""
        df.loc[df["Diensteintrittsdatum"].isna(), "Fehlermeldung"] = "Kein Diensteintrittsdatum hinterlegt"

        mask_valid = df["Diensteintrittsdatum"].notna()

        df.loc[mask_valid, "Wartezeit erfüllt am"] = df.loc[mask_valid, "Diensteintrittsdatum"].apply(berechne_wartezeit)
        df.loc[mask_valid, "Stufenbeginn am"] = df.loc[mask_valid, "Wartezeit erfüllt am"] + pd.DateOffset(months=12)
        df.loc[mask_valid, "Aktuelle Stufe"] = df.loc[mask_valid, "Wartezeit erfüllt am"].apply(berechne_stufe)
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

        # Nur relevante Spalten exportieren
        export_df = df.drop(columns=["Beitrag laut Stufe (bereinigt)", "Beitrag laut Allianz Vertrag (bereinigt)"], errors="ignore")

        # Ergebnis anzeigen
        st.success("✅ Datei erfolgreich verarbeitet!")
        st.dataframe(export_df)

        # Download ermöglichen
        excel_buffer = BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl', date_format="DD.MM.YYYY") as writer:
            export_df.to_excel(writer, index=False)
        st.download_button(
            label="📥 Ergänzte Datei herunterladen",
            data=excel_buffer.getvalue(),
            file_name="sentiris_auswertung.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        st.error(f"❌ Fehler bei der Verarbeitung:\n{e}")
