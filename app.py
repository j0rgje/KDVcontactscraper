import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime
from io import BytesIO
from supabase import create_client

# Page configuration
st.set_page_config(page_title="Locatiemanager Finder", layout="wide")

# Initialize session state
if "session" not in st.session_state:
    st.session_state.session = None
if "user" not in st.session_state:
    st.session_state.user = None
if "login_error" not in st.session_state:
    st.session_state.login_error = None
if "signup_error" not in st.session_state:
    st.session_state.signup_error = None
if "signup_success" not in st.session_state:
    st.session_state.signup_success = False

# Supabase initialization
SUPABASE_URL = st.secrets.get("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Authentication flow
# Authentication flow
if st.session_state.session is None:
    st.sidebar.title("Authenticatie")
    action = st.sidebar.radio("Actie:", ["Inloggen", "Registreren"])

    if action == "Inloggen":
        st.title("Login")
        with st.form("login_form"):  
            email = st.text_input("E-mail")
            password = st.text_input("Wachtwoord", type="password")
            submit = st.form_submit_button("Inloggen")
        if submit:
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            err = getattr(res, 'error', None)
            sess = getattr(res, 'session', None)
            user = getattr(res, 'user', None)
            if err:
                st.session_state.login_error = err.message
            elif sess is None:
                st.session_state.login_error = "Geen geldige sessie ontvangen. Heb je je e-mail bevestigd?"
            else:
                # Successful login: set session and reload via JS
                st.session_state.session = sess
                st.session_state.user = {"email": user.email, "id": user.id} if user else None
                st.session_state.login_error = None
                components.html("<script>window.location.href=window.location.href;</script>", height=0)
        if st.session_state.login_error:
            st.error(st.session_state.login_error)
        st.stop()

    else:  # Registreren
        st.title("Nieuw account aanmaken")
        with st.form("signup_form"):  
            email = st.text_input("E-mail (gebruikersnaam)")
            password = st.text_input("Wachtwoord", type="password")
            submit = st.form_submit_button("Account aanmaken")
        if submit:
            res = supabase.auth.sign_up({"email": email, "password": password})
            err = getattr(res, 'error', None)
            if err:
                st.session_state.signup_error = err.message
            else:
                st.session_state.signup_success = True
                st.session_state.signup_error = None
                # reload to show success
                components.html("<script>window.location.href=window.location.href;</script>", height=0)
        if st.session_state.signup_error:
            st.error(st.session_state.signup_error)
        if st.session_state.signup_success:
            st.success("Registratie gestart! Controleer je e-mail voor verificatie.")
        st.stop()

# SerpAPI-key uit secrets
SERPAPI_KEY = st.secrets.get("SERPAPI_KEY")

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

# Scraper UI
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
