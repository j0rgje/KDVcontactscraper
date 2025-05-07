import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime
from io import BytesIO
import os
import phonenumbers

# Configuratie SerpAPI via environment variable
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "JOUW_SERPAPI_API_KEY_HIER")

@st.cache_data
def zoek_website_bij_naam(locatienaam: str, plaats: str) -> str | None:
    query = f"{locatienaam} {plaats} kinderopvang"
    params = {"q": query, "api_key": SERPAPI_KEY, "engine": "google"}
    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for res in data.get("organic_results", []):
            link = res.get("link")
            if link:
                return link
    except Exception:
        return None
    return None

@st.cache_data
def scrape_contactgegevens(url: str) -> dict:
    result = {"emails": [], "telefoons": [], "adressen": [], "functietitels": [], "error": ""}
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        tekst = soup.get_text(separator="\n")

        # 1. E-mails
        result["emails"] = list(set(re.findall(
            r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
            tekst
        )))

        # 2. Telefoonnummers
        telefoons = []
        for match in phonenumbers.PhoneNumberMatcher(tekst, "NL"):
            telefoons.append(
                phonenumbers.format_number(
                    match.number,
                    phonenumbers.PhoneNumberFormat.INTERNATIONAL
                )
            )
        result["telefoons"] = list(set(telefoons))

        # 3. Adressen
        adressen = []
        for tag in soup.find_all(['address', 'p', 'span', 'div']):
            line = tag.get_text().strip()
            if re.search(
                r"\b[A-Z][a-z]+(?:straat|laan|weg|plein|dreef)\s*\d+",
                line
            ):
                adressen.append(line)
        result["adressen"] = list(set(adressen))

        # 4. Functietitels
        functietitels = []
        for line in tekst.split("\n"):
            if re.search(
                r"\b(manager|co[oö]rdinator|leiding|beheerder)\b",
                line, flags=re.IGNORECASE
            ):
                functietitels.append(line.strip())
        result["functietitels"] = list(set(functietitels))

    except Exception as e:
        result["error"] = str(e)
    return result

# Streamlit UI
st.set_page_config(page_title="Locatiemanager Finder", layout="wide")
st.title("Kinderopvang Locatiemanager Scraper")

# Optioneel: laat gebruiker SerpAPI-key invoeren
api_key_input = st.text_input("SerpAPI Key", type="password")
if api_key_input:
    SERPAPI_KEY = api_key_input

uploaded_file = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])
if uploaded_file:
    df = pd.read_excel(uploaded_file)
    expected = {'locatienaam', 'plaats'}
    if not expected.issubset(df.columns):
        st.error(f"Excel moet kolommen bevatten: {expected}")
    else:
        st.write("### Ingelezen data", df.head())

        if st.button("Start scraping"):
            resultaten = []
            progress = st.progress(0)
            status_text = st.empty()

            for idx, row in df.iterrows():
                naam, plaats = str(row['locatienaam']), str(row['plaats'])
                status_text.text(f"Verwerk {idx+1}/{len(df)}: {naam}, {plaats}")
                website = zoek_website_bij_naam(naam, plaats)
                time.sleep(1)
                data = scrape_contactgegevens(website) if website else {"error": "Geen website gevonden"}

                resultaten.append({
                    "locatienaam":   naam,
                    "plaats":        plaats,
                    "website":       website or "",
                    "emails":        ", ".join(data.get("emails", [])),
                    "telefoons":     ", ".join(data.get("telefoons", [])),
                    "adressen":      " | ".join(data.get("adressen", [])),
                    "functietitels": " | ".join(data.get("functietitels", [])),
                    "error":         data.get("error", "")
                })
                progress.progress((idx+1)/len(df))

            res_df = pd.DataFrame(resultaten)
            nu = datetime.now().strftime('%Y-%m-%d-%H-%M')
            fname = f"locatiemanager-gegevens-{nu}.xlsx"
            buf = BytesIO()
            res_df.to_excel(buf, index=False)
            buf.seek(0)
            st.download_button("Download resultaten", data=buf,
                               file_name=fname,
                               mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
