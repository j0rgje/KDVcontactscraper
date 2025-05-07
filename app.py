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

# 1) Definieer pure functies (zonder @st.cache_data)
def _zoek_website_bij_naam(locatienaam: str, plaats: str) -> str | None:
    query = f"{locatienaam} {plaats} kinderopvang"
    params = {"q": query, "api_key": st.session_state.get("SERPAPI_KEY", ""), "engine": "google"}
    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=10)
        resp.raise_for_status()
        for r in resp.json().get("organic_results", []):
            link = r.get("link")
            if link:
                return link
    except:
        return None
    return None

def _scrape_contactgegevens(url: str) -> dict:
    result = {"emails": [], "telefoons": [], "adressen": [], "functietitels": [], "error": ""}
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        content = resp.text

        if not re.search(r"[@0-9]", content):
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=15000)
                content = page.content()
                browser.close()

        soup = BeautifulSoup(content, "html.parser")
        tekst = soup.get_text(separator="\n")

        result["emails"] = list(set(re.findall(
            r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", tekst
        )))
        result["telefoons"] = list({
            phonenumbers.format_number(m.number, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
            for m in phonenumbers.PhoneNumberMatcher(tekst, "NL")
        })
        result["adressen"] = list({
            tag.get_text().strip()
            for tag in soup.find_all(["address","p","span","div"])
            if re.search(r"\b[A-Z][a-z]+(?:straat|laan|weg|plein|dreef)\s*\d+", tag.get_text())
        })
        result["functietitels"] = list({
            line.strip()
            for line in tekst.split("\n")
            if re.search(r"\b(manager|co[oö]rdinator|leiding|beheerder)\b", line, flags=re.IGNORECASE)
        })

    except Exception as e:
        result["error"] = str(e)
    return result

# 2) Zet page config direct na imports
st.set_page_config(page_title="Locatiemanager Finder", layout="wide")
st.title("Kinderopvang Locatiemanager Scraper")

# 3) SerpAPI Key beheer
if "SERPAPI_KEY" in st.secrets:
    st.session_state["SERPAPI_KEY"] = st.secrets["SERPAPI_KEY"]
elif os.getenv("SERPAPI_KEY"):
    st.session_state["SERPAPI_KEY"] = os.getenv("SERPAPI_KEY")

if not st.session_state.get("SERPAPI_KEY"):
    key = st.text_input("Voer SerpAPI Key in:", type="password")
    if key:
        st.session_state["SERPAPI_KEY"] = key

# 4) Wrap de pure functions met caching
zoek_website_bij_naam = st.cache_data(_zoek_website_bij_naam)
scrape_contactgegevens = st.cache_data(_scrape_contactgegevens)

# 5) UI: Excel upload en scraping flow
uploaded_file = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])
if uploaded_file:
    df = pd.read_excel(uploaded_file)
    if not {"locatienaam","plaats"}.issubset(df.columns):
        st.error("Excel moet kolommen 'locatienaam' en 'plaats' bevatten.")
        st.stop()

    st.write("### Ingelezen locaties", df)

    if st.button("Start scraping"):
        resultaten = []
        errors_df = pd.DataFrame(columns=["locatie","error"])
        progress = st.progress(0)
        status = st.empty()
        result_table = st.empty()

        for i, row in df.iterrows():
            naam, plaats = row["locatienaam"], row["plaats"]
            status.text(f"Verwerk {i+1}/{len(df)}: {naam} ({plaats})")
            site = zoek_website_bij_naam(naam, plaats)
            time.sleep(1)
            data = scrape_contactgegevens(site) if site else {"error":"Geen website gevonden"}

            resultaten.append({
                "locatienaam":   naam,
                "plaats":        plaats,
                "website":       site or "",
                "emails":        ", ".join(data.get("emails", [])),
                "telefoons":     ", ".join(data.get("telefoons", [])),
                "adressen":      " | ".join(data.get("adressen", [])),
                "functietitels": " | ".join(data.get("functietitels", [])),
                "error":         data.get("error","")
            })
            if data.get("error"):
                errors_df.loc[len(errors_df)] = [naam, data["error"]]

            result_table.dataframe(pd.DataFrame(resultaten))
            progress.progress((i+1)/len(df))

        # Download en tonen
        res_df = pd.DataFrame(resultaten)
        now = datetime.now().strftime("%Y-%m-%d-%H-%M")
        fname = f"locatiemanager-gegevens-{now}.xlsx"
        buf = BytesIO(); res_df.to_excel(buf, index=False); buf.seek(0)

        st.download_button("Download resultaten", buf, file_name=fname,
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.subheader("Resultaten")
        st.dataframe(res_df)
        if not errors_df.empty:
            st.warning("Er waren fouten tijdens scraping:")
            st.table(errors_df)
