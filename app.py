import os
import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime
from io import BytesIO
import phonenumbers
from playwright.sync_api import sync_playwright

# Zet de page config vóór alle andere Streamlit-commando's
st.set_page_config(page_title="Locatiemanager Finder", layout="wide")

# Titel van de app
st.title("Kinderopvang Locatiemanager Scraper")

# Configuratie SerpAPI via secrets of omgevingsvariabele
if "SERPAPI_KEY" in st.secrets:
    SERPAPI_KEY = st.secrets["SERPAPI_KEY"]
else:
    SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

# UI-element om API-key in te voeren indien nog niet ingesteld
if not SERPAPI_KEY:
    key_input = st.text_input("Voer SerpAPI Key in:", type="password")
    if key_input:
        SERPAPI_KEY = key_input
        st.session_state["SERPAPI_KEY"] = key_input
elif "SERPAPI_KEY" in st.session_state:
    SERPAPI_KEY = st.session_state["SERPAPI_KEY"]

@st.cache_data
def zoek_website_bij_naam(locatienaam: str, plaats: str) -> str | None:
    """Zoek website via SerpAPI en cache het resultaat."""
    query = f"{locatienaam} {plaats} kinderopvang"
    params = {"q": query, "api_key": SERPAPI_KEY, "engine": "google"}
    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("organic_results", [])
        return next((r.get("link") for r in results if r.get("link")), None)
    except Exception:
        return None

@st.cache_data
def scrape_contactgegevens(url: str) -> dict:
    """Scrape e-mail, telefoon, adres en functietitel, met Playwright-fallback."""
    result = {"emails": [], "telefoons": [], "adressen": [], "functietitels": [], "error": ""}
    try:
        # Eerste poging: requests
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        content = resp.text

        # Fallback naar headless browser voor JS-­sites
        if not re.search(r"[@0-9]", content):
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=15000)
                content = page.content()
                browser.close()

        soup = BeautifulSoup(content, "html.parser")
        tekst = soup.get_text(separator="\n")

        # 1. E-mails
        result["emails"] = list(set(
            re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", tekst)
        ))

        # 2. Telefoonnummers
        result["telefoons"] = list({
            phonenumbers.format_number(m.number, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
            for m in phonenumbers.PhoneNumberMatcher(tekst, "NL")
        })

        # 3. Adressen (NL-straat + nummer)
        result["adressen"] = list({
            tag.get_text().strip()
            for tag in soup.find_all(["address","p","span","div"])
            if re.search(r"\b[A-Z][a-z]+(?:straat|laan|weg|plein|dreef)\s*\d+", tag.get_text())
        })

        # 4. Functietitels
        result["functietitels"] = list({
            line.strip()
            for line in tekst.split("\n")
            if re.search(r"\b(manager|co[oö]rdinator|leiding|beheerder)\b", line, flags=re.IGNORECASE)
        })

    except Exception as e:
        result["error"] = str(e)

    return result

# Bestand upload
uploaded_file = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])
if uploaded_file:
    df = pd.read_excel(uploaded_file)

    # Validatie kolommen
    if not {"locatienaam", "plaats"}.issubset(df.columns):
        st.error("Excel moet kolommen 'locatienaam' en 'plaats' bevatten.")
    else:
        st.write("### Ingelezen locaties", df)

        if st.button("Start scraping"):
            resultaten = []
            progress = st.progress(0)
            status = st.empty()
            errors_df = pd.DataFrame(columns=["locatie", "error"])
            result_table = st.empty()

            # Scrapen per locatie
            for idx, row in df.iterrows():
                naam, plaats = row["locatienaam"], row["plaats"]
                status.text(f"Proces {idx+1}/{len(df)}: {naam}, {plaats}")
                site = zoek_website_bij_naam(naam, plaats)
                time.sleep(1)
                data = scrape_contactgegevens(site) if site else {"error": "Geen website gevonden"}

                # Verzamel resultaat
                resultaten.append({
                    "locatienaam":   naam,
                    "plaats":        plaats,
                    "website":       site or "",
                    "emails":        ", ".join(data.get("emails", [])),
                    "telefoons":     ", ".join(data.get("telefoons", [])),
                    "adressen":      " | ".join(data.get("adressen", [])),
                    "functietitels": " | ".join(data.get("functietitels", [])),
                    "error":         data.get("error", "")
                })
                if data.get("error"):
                    errors_df.loc[len(errors_df)] = [naam, data["error"]]

                # Update UI
                result_table.dataframe(pd.DataFrame(resultaten))
                progress.progress((idx+1) / len(df))

            # Downloadknop
            res_df = pd.DataFrame(resultaten)
            nu = datetime.now().strftime("%Y-%m-%d-%H-%M")
            fname = f"locatiemanager-gegevens-{nu}.xlsx"
            buf = BytesIO()
            res_df.to_excel(buf, index=False)
            buf.seek(0)
            st.download_button(
                "Download resultaten",
                buf,
                file_name=fname,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # Toon resultaat en fouten
            st.subheader("Resultaten")
            st.dataframe(res_df)
            if not errors_df.empty:
                st.warning("Er waren fouten tijdens scraping:")
                st.table(errors_df)
