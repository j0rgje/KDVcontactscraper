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
from duckduckgo_search import ddg
from playwright.sync_api import sync_playwright

# Zet page config vóór alle andere Streamlit-commando's
st.set_page_config(page_title="Locatiemanager Finder", layout="wide")
st.title("Kinderopvang Locatiemanager Scraper (Gratis zoekmethode)")

# Caching-wrapper voor performance
@st.cache_data
def zoek_website_bij_naam(locatienaam: str, plaats: str) -> str | None:
    """Zoek website via DuckDuckGo HTML en fallback naar headless browser indien nodig."""
    query = f"{locatienaam} {plaats} kinderopvang"
    # 1. DuckDuckGo HTML search
    try:
        url = "https://duckduckgo.com/html/"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.post(url, data={"q": query}, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        link_tag = soup.find("a", class_="result__a")
        if link_tag and link_tag.has_attr("href"):
            return link_tag["href"]
    except Exception:
        pass
    # 2. Playwright fallback
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"https://duckduckgo.com/?q={urllib.parse.quote(query)}", timeout=15000)
            link = page.query_selector("a.result__a")
            href = link.get_attribute("href") if link else None
            browser.close()
            return href
    except Exception:
        pass
    return None
    return None

@st.cache_data
def scrape_contactgegevens(url: str) -> dict:
    """Scrape e-mail, telefoon, adres en functietitel, met Playwright-fallback."""
    result = {"emails": [], "telefoons": [], "adressen": [], "functietitels": [], "error": ""}
    try:
        # Probeer met requests
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        content = resp.text

        # Fallback voor JS-sites
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
            r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", tekst
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

# Upload en verwerking
uploaded_file = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])
if uploaded_file:
    df = pd.read_excel(uploaded_file)
    if not {'locatienaam','plaats'}.issubset(df.columns):
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
            naam, plaats = row['locatienaam'], row['plaats']
            status.text(f"Verwerk {i+1}/{len(df)}: {naam} ({plaats})")
            site = zoek_website_bij_naam(naam, plaats)
            time.sleep(1)
            data = scrape_contactgegevens(site) if site else {"error":"Geen website gevonden"}

            resultaten.append({
                'locatienaam':   naam,
                'plaats':        plaats,
                'website':       site or '',
                'emails':        ", ".join(data.get('emails', [])),
                'telefoons':     ", ".join(data.get('telefoons', [])),
                'adressen':      ' | '.join(data.get('adressen', [])),
                'functietitels': ' | '.join(data.get('functietitels', [])),
                'error':         data.get('error', '')
            })
            if data.get('error'):
                errors_df.loc[len(errors_df)] = [naam, data['error']]

            result_table.dataframe(pd.DataFrame(resultaten))
            progress.progress((i+1)/len(df))

        # Download en tonen
        res_df = pd.DataFrame(resultaten)
        now = datetime.now().strftime('%Y-%m-%d-%H-%M')
        fname = f"locatiemanager-gegevens-{now}.xlsx"
        buf = BytesIO(); res_df.to_excel(buf, index=False); buf.seek(0)
        st.download_button("Download resultaten", buf, file_name=fname,
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        st.subheader("Resultaten")
        st.dataframe(res_df)
        if not errors_df.empty:
            st.warning("Er waren fouten tijdens scraping:")
            st.table(errors_df)