import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime
from io import BytesIO
from supabase import create_client

# Init Supabase client using env vars uit secrets
SUPABASE_URL = st.secrets["NEXT_PUBLIC_SUPABASE_URL"]
SUPABASE_KEY = st.secrets["NEXT_PUBLIC_SUPABASE_ANON_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Sessie state voor authenticatie
if "session" not in st.session_state:
    st.session_state.session = None

# Keuze: inloggen of registreren
if not st.session_state.session:
    actie = st.sidebar.radio("Wat wil je doen?", ["Inloggen", "Registreren"])
    if actie == "Registreren":
        st.title("Nieuw account aanmaken")
        with st.form(key="signup_form"):
            email = st.text_input("E-mail (wordt je gebruikersnaam)")
            password = st.text_input("Wachtwoord", type="password")
            signup = st.form_submit_button("Registreren")
        if signup:
            res = supabase.auth.sign_up({"email": email, "password": password})
            if res.get('error'):
                st.error(f"Registratie mislukt: {res['error']['message']}")
            else:
                st.success("Registratie gelukt! Controleer je e-mail voor verificatie.")
        st.stop()
    else:
        st.title("Login")
        with st.form(key="login_form"):
            email = st.text_input("E-mail")
            password = st.text_input("Wachtwoord", type="password")
            login = st.form_submit_button("Inloggen")
        if login:
            res = supabase.auth.sign_in({"email": email, "password": password})
            if res.get('error') or not res.get('data'):
                st.error("Onjuiste e-mail of wachtwoord.")
            else:
                st.session_state.session = res['data']
                st.experimental_rerun()
        st.stop()

# Vanaf hier is de gebruiker ingelogd
user_email = st.session_state.session['user']['email']
st.sidebar.write(f"Ingelogd als: {user_email}")

# SerpAPI-key uit secrets
SERPAPI_KEY = st.secrets.get("SERPAPI_KEY")

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
