import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime
from io import BytesIO

# Haal gebruikers en SerpAPI-key uit Streamlit Secrets
USERS = st.secrets.get("users", {})  # dict: {"user1": "pass1", ...}
SERPAPI_KEY = st.secrets.get("SERPAPI_KEY")

# Sessie state voor authenticatie
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# Actie selectie: inloggen of account aanmaken
actie = None
if not st.session_state.authenticated:
    actie = st.sidebar.radio("Wat wil je doen?", ["Inloggen", "Account aanmaken"] )

if not st.session_state.authenticated and actie == "Account aanmaken":
    st.title("Nieuw account aanmaken")
    with st.form(key="signup_form"):
        new_user = st.text_input("Kies een gebruikersnaam")
        new_pass = st.text_input("Kies een wachtwoord", type="password")
        signup = st.form_submit_button("Account genereren")
    if signup:
        if new_user in USERS:
            st.error("Deze gebruikersnaam bestaat al.")
        else:
            st.success("Account klaargezet!")
            st.markdown(
                "Kopieer de volgende regel en plak in je `.streamlit/secrets.toml` onder `[users]`:"
            )
            st.code(f"{new_user} = \"{new_pass}\"", language="toml")
    st.stop()

# Login scherm
if not st.session_state.authenticated:
    st.title("Login")
    with st.form(key="login_form"):
        input_user = st.text_input("Gebruikersnaam")
        input_pass = st.text_input("Wachtwoord", type="password")
        submit = st.form_submit_button("Inloggen")
    if submit:
        if input_user in USERS and input_pass == USERS[input_user]:
            st.session_state.authenticated = True
            st.experimental_rerun()
        else:
            st.error("Onjuiste gebruikersnaam of wachtwoord.")
    st.stop()

# Vanaf hier is de gebruiker ingelogd
# Configuratie SerpAPI zoek- en scrape-functies
@st.cache_data
def zoek_website_bij_naam(locatienaam, plaats):
    query = f"{locatienaam} {plaats} kinderopvang"
    params = {"q": query, "api_key": SERPAPI_KEY, "engine": "google"}
    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=10)
        data = resp.json()
        for res in data.get("organic_results", []):
            if "link" in res:
                return res["link"]
    except:
        return None
    return None

@st.cache_data
def scrape_contactgegevens(url):
    try:
        resp = requests.get(url, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        tekst = soup.get_text()
        emails = set(re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", tekst))
        managers = [p.get_text().strip() for p in soup.find_all("p") if "locatiemanager" in p.get_text().lower()]
        return {"emails": list(emails), "managers": managers}
    except Exception as e:
        return {"error": str(e)}

# Streamlit UI
st.set_page_config(page_title="Locatiemanager Finder", layout="wide")
st.title("Kinderopvang Locatiemanager Scraper")

uploaded_file = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])
if uploaded_file:
    df = pd.read_excel(uploaded_file)
    st.write("### Ingelezen data", df.head())

    if st.button("Start scraping"):
        resultaten = []
        progress = st.progress(0)
        for idx, row in df.iterrows():
            naam, plaats = str(row['locatienaam']), str(row['plaats'])
            website = zoek_website_bij_naam(naam, plaats)
            time.sleep(1)
            data = scrape_contactgegevens(website) if website else {}
            resultaten.append({
                'locatienaam': naam,
                'plaats': plaats,
                'website': website,
                'emails': ", ".join(data.get('emails', [])),
                'managers': " | ".join(data.get('managers', [])),
                'error': data.get('error', '')
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