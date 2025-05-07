import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime
from io import BytesIO
from supabase import create_client

# Init Supabase client using env vars
SUPABASE_URL = st.secrets["NEXT_PUBLIC_SUPABASE_URL"]
SUPABASE_KEY = st.secrets["NEXT_PUBLIC_SUPABASE_ANON_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Ensure session_state keys for user session
if "session" not in st.session_state:
    st.session_state.session = None
if "user" not in st.session_state:
    st.session_state.user = None

# Authentication flow
if not st.session_state.session:
    action = st.sidebar.radio("Wat wil je doen?", ["Inloggen", "Registreren"])

    if action == "Registreren":
        st.title("Nieuw account aanmaken")
        with st.form("signup_form"):
            email = st.text_input("E-mail (wordt je gebruikersnaam)")
            password = st.text_input("Wachtwoord", type="password")
            signup_click = st.form_submit_button("Registreren")
        if signup_click:
            res = supabase.auth.sign_up({"email": email, "password": password})
            err = getattr(res, "error", None)
            if err:
                st.error(f"Registratie mislukt: {err.message}")
            else:
                st.success("Registratie gestart! Controleer je e-mail voor verificatie.")
        st.stop()

    # Login form
    st.title("Login")
    with st.form("login_form"):
        email = st.text_input("E-mail")
        password = st.text_input("Wachtwoord", type="password")
        login_click = st.form_submit_button("Inloggen")
    if login_click:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        err = getattr(res, "error", None)
        session = getattr(res, "session", None)
        user = getattr(res, "user", None)
        if err:
            st.error(f"Inloggen mislukt: {err.message}")
        elif not session:
            st.error("Inloggen mislukt: geen geldige sessie ontvangen. Heb je je e-mail bevestigd?")
        else:
            st.session_state.session = session
            st.session_state.user = {"email": user.email, "id": user.id} if user else None
            st.experimental_rerun()
    st.stop()

# User is now logged in
user_info = st.session_state.user or {}
st.sidebar.write(f"Ingelogd als: {user_info.get('email', 'Onbekend')}")

# SerpAPI-key uit secrets
SERPAPI_KEY = st.secrets["SERPAPI_KEY"]

@st.cache_data
def zoek_website_bij_naam(locatienaam, plaats):
    query = f"{locatienaam} {plaats} kinderopvang"
    params = {"q": query, "api_key": SERPAPI_KEY, "engine": "google"}
    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=10)
        data = resp.json()
        for item in data.get("organic_results", []):
            link = item.get("link")
            if link:
                return link
    except Exception:
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

# Main UI
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
        buf = BytesIO()
        res_df.to_excel(buf, index=False)
        buf.seek(0)
        st.download_button("Download resultaten", data=buf,
                           file_name=f"locatiemanager-gegevens-{nu}.xlsx",
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
