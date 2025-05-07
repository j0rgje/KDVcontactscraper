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

# Configuratie SerpAPI via environment variable of Streamlit secrets
if "SERPAPI_KEY" in st.secrets:
    SERPAPI_KEY = st.secrets["SERPAPI_KEY"]
else:
    SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

# API-key invoer in UI en sessie
if not SERPAPI_KEY:
    key_input = st.text_input("Voer SerpAPI Key in:", type="password")
    if key_input:
        st.session_state["SERPAPI_KEY"] = key_input
        SERPAPI_KEY = key_input
elif "SERPAPI_KEY" in st.session_state:
    SERPAPI_KEY = st.session_state["SERPAPI_KEY"]

# Streamlit UI configuratie
st.set_page_config(page_title="Locatiemanager Finder", layout="wide")
st.title("Kinderopvang Locatiemanager Scraper")

# Caching van zoek- en scrape-functies voor performance
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
    """Scrape publieke gegevens, met fallback naar headless browser voor JS-sites."""
    result = {"emails": [], "telefoons": [], "adressen": [], "functietitels": [], "error": ""}
    try:
        # Eerste poging via requests
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        content = resp.text

        # Fallback naar headless browser als requests niets oplevert
        if not re.search(r"[@0-9]", content):
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=15000)
                content = page.content()
                browser.close()

        soup = BeautifulSoup(content, 'html.parser')
        tekst = soup.get_text(separator="\n")

        # 1. E-mails
        result["emails"] = list(set(re.findall(
            r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
            tekst
        )))
        # 2. Telefoonnummers
        result["telefoons"] = list({
            phonenumbers.format_number(m.number, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
            for m in phonenumbers.PhoneNumberMatcher(tekst, "NL")
        })
        # 3. Adressen
        result["adressen"] = list({
            tag.get_text().strip()
            for tag in soup.find_all(['address','p','span','div'])
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

# Bestand upload en verwerking
uploaded_file = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])
if uploaded_file:
    df = pd.read_excel(uploaded_file)
    if not {'locatienaam', 'plaats'}.issubset(df.columns):
        st.error("File moet kolommen 'locatienaam' en 'plaats' bevatten.")
    else:
        st.write("### Ingelezen locaties", df)
        if st.button("Start scraping"):
            resultaten = []
            progress = st.progress(0)
            status = st.empty()
            errors_df = pd.DataFrame(columns=['locatie', 'error'])
            result_table = st.empty()

            for idx, row in df.iterrows():
                naam, plaats = row['locatienaam'], row['plaats']
                status.text(f"Proces {idx+1}/{len(df)}: {naam}, {plaats}")
                site = zoek_website_bij_naam(naam, plaats)
                time.sleep(1)
                data = scrape_contactgegevens(site) if site else {"error": "Geen website"}

                resultaten.append({
                    'locatienaam':   naam,
                    'plaats':        plaats,
                    'website':       site or '',
                    'emails':        ", ".join(data.get('emails', [])),
                    'telefoons':     ", ".join(data.get('telefoons', [])),
                    'adressen':      " | ".join(data.get('adressen', [])),
                    'functietitels': " | ".join(data.get('functietitels', [])),
                    'error':         data.get('error', '')
                })
                if data.get('error'):
                    errors_df.loc[len(errors_df)] = [naam, data['error']]
                result_table.dataframe(pd.DataFrame(resultaten))
                progress.progress((idx+1)/len(df))

            # Download en tonen
            res_df = pd.DataFrame(resultaten)
            nu = datetime.now().strftime('%Y-%m-%d-%H-%M')
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

            # Resultaat op scherm
            st.subheader("Resultaten")
            st.dataframe(res_df)
            if not errors_df.empty:
                st.warning("Er waren fouten tijdens scraping:")
                st.table(errors_df)
