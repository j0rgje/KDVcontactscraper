import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime
from io import BytesIO
from supabase import create_client
import streamlit.components.v1 as components  # for JS reload

# Page config must be first Streamlit command
st.set_page_config(page_title="Locatiemanager Finder", layout="wide")

# Init Supabase client using env vars
SUPABASE_URL = st.secrets["NEXT_PUBLIC_SUPABASE_URL"]
SUPABASE_KEY = st.secrets["NEXT_PUBLIC_SUPABASE_ANON_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize session state
if "session" not in st.session_state:
    st.session_state.session = None
if "user" not in st.session_state:
    st.session_state.user = None

# Authentication flow
if st.session_state.session is None:
    action = st.sidebar.radio("Wat wil je doen?", ["Inloggen", "Registreren"])

    if action == "Registreren":
        st.title("Nieuw account aanmaken")
        with st.form("signup_form"):
            email = st.text_input("E-mail (gebruikersnaam)")
            password = st.text_input("Wachtwoord", type="password")
            submit = st.form_submit_button("Account aanmaken")
        if submit:
            res = supabase.auth.sign_up({"email": email, "password": password})
            err = getattr(res, 'error', None)
            if err:
                st.error(f"Registratie mislukt: {err.message}")
            else:
                st.success("Registratie gestart! Controleer je e-mail voor verificatie.")
        # Stop execution to stay on auth screen
        st.stop()

    # Login
    st.title("Login")
    with st.form("login_form"):
        email = st.text_input("E-mail")
        password = st.text_input("Wachtwoord", type="password")
        submit = st.form_submit_button("Inloggen")
    if submit:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        err = getattr(res, 'error', None)
        session = getattr(res, 'session', None)
        user = getattr(res, 'user', None)
        if err:
            st.error(f"Inloggen mislukt: {err.message}")
        elif session:
            st.session_state.session = session
            st.session_state.user = {"email": user.email, "id": user.id} if user else None
            # Reload page via JS to re-render UI
            components.html("<script>window.location.reload();</script>")
            st.stop()
            st.session_state.session = session
            st.session_state.user = {"email": user.email, "id": user.id} if user else None
            # After setting session, rerun to show main UI only
            try:
                st.experimental_rerun()
            except Exception:
                pass
        else:
            st.error("Inloggen mislukt: geen geldige sessie ontvangen. Heb je je e-mail bevestigd?")
    # If still not logged in, stop to show auth UI
    if st.session_state.session is None:
        st.stop()

# Main UI: user is logged in
user_info = st.session_state.user or {}
st.sidebar.write(f"Ingelogd als: {user_info.get('email', 'Onbekend')}")

# Logout button
if st.sidebar.button("Log uit"):
    st.session_state.session = None
    st.session_state.user = None
    # Reload page via JS
    components.html("<script>window.location.reload();</script>")
    st.stop()

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

# Main scraping UI
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
            site = zoek_website_bij_naam(naam, plaats)
            time.sleep(1)
            data = scrape_contactgegevens(site) if site else {}
            resultaten.append({
                'locatienaam': naam,
                'plaats': plaats,
                'website': site,
                'emails': ", ".join(data.get('emails', [])),
                'managers': " | ".join(data.get('managers', [])),
                'error': data.get('error', '')
            })
            progress.progress((idx+1)/len(df))
        res_df = pd.DataFrame(resultaten)
        nu = datetime.now().strftime('%Y-%m-%d-%H-%M')
        buf = BytesIO(); res_df.to_excel(buf, index=False); buf.seek(0)
        st.download_button("Download resultaten", data=buf,
                           file_name=f"locatiemanager-gegevens-{nu}.xlsx",
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
