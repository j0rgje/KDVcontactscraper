import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime
from io import BytesIO
from supabase import create_client
import altair as alt
import phonenumbers
import streamlit.components.v1 as components  # for JS reload
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors

# Page configuration
st.set_page_config(page_title="Locatiemanager Finder", layout="wide")

# Initialize session state
for key in ["session", "user", "login_error", "signup_error", "signup_success", "manual_rows"]:
    if key not in st.session_state:
        st.session_state[key] = None if key != "signup_success" else False
if st.session_state.manual_rows is None:
    st.session_state.manual_rows = []

# Supabase initialization
SUPABASE_URL = st.secrets.get("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Authentication flow
if not st.session_state.session:
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
                components.html("<script>window.location.href=window.location.href;</script>", height=0)
        if st.session_state.signup_error:
            st.error(st.session_state.signup_error)
        if st.session_state.signup_success:
            st.success("Registratie gestart! Controleer je e-mail voor verificatie.")
        st.stop()

# Main UI Sidebar Logout
with st.sidebar:
    user_email = st.session_state.user.get('email', 'Onbekend') if st.session_state.user else 'Onbekend'
    st.write(f"Ingelogd als: {user_email}")
    if st.button("Log uit"):
        for key in ['session','user','login_error','signup_error','signup_success']:
            st.session_state[key] = None
        components.html("<script>window.location.reload();</script>", height=0)

# SerpAPI-key uit secrets
SERPAPI_KEY = st.secrets.get("SERPAPI_KEY")

# Function to lookup website URL
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

# Enhanced scrape: emails, phones, addresses, managers
@st.cache_data
def scrape_contactgegevens(url):
    result = {"emails": [], "telefoons": [], "adressen": [], "managers": [], "error": ""}
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        text = soup.get_text(separator="\n")
        # Emails
        result['emails'] = re.findall(r"[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}", text)
        # Phones
        phones = []
        for match in phonenumbers.PhoneNumberMatcher(text, "NL"):
            phones.append(phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.INTERNATIONAL))
        result['telefoons'] = phones
        # Addresses (street+nr or postcode)
        addr_pattern = r"[A-Z][a-z]+(?:straat|laan|weg|plein|dreef)\s*\d+|\d{4}\s?[A-Z]{2}"
        result['adressen'] = re.findall(addr_pattern, text)
        # Managers
        result['managers'] = [line.strip() for line in text.split("\n") if re.search(r"locatiemanager", line, flags=re.IGNORECASE)]
    except Exception as e:
        result['error'] = str(e)
    return result

# Scraper UI
st.title("Kinderopvang Locatiemanager Scraper")
# Mode select
mode = st.radio("Invoermodus:", ["Bestand upload", "Handmatige invoer"])
input_df = pd.DataFrame()
if mode == "Bestand upload":
    uploaded_file = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])
    if uploaded_file:
        input_df = pd.read_excel(uploaded_file)
        st.write("### Ingelezen data", input_df.head())
elif mode == "Handmatige invoer":
    naam = st.text_input("Locatienaam")
    plaats = st.text_input("Plaats")
    if st.button("Voeg toe"):
        if naam and plaats:
            st.session_state.manual_rows.append({"locatienaam": naam, "plaats": plaats})
        else:
            st.warning("Vul zowel locatienaam als plaats in.")
    if st.session_state.manual_rows:
        input_df = pd.DataFrame(st.session_state.manual_rows)
        st.write("### Handmatige invoer", input_df)

# Start scraping
if not input_df.empty and st.button("Start scraping"):
    resultaten = []
    progress = st.progress(0)
    for idx, row in input_df.iterrows():
        naam, plaats = str(row['locatienaam']), str(row['plaats'])
        site = zoek_website_bij_naam(naam, plaats)
        time.sleep(1)
        data = scrape_contactgegevens(site) if site else {'error': 'Geen website'}
        resultaten.append({
            'locatienaam': naam,
            'plaats': plaats,
            'website': site,
            'emails': ", ".join(data.get('emails', [])),
            'telefoons': ", ".join(data.get('telefoons', [])),
            'adressen': ", ".join(data.get('adressen', [])),
            'managers': " | ".join(data.get('managers', [])),
            'error': data.get('error', '')
        })
        progress.progress((idx+1)/len(input_df))
    # Show and export
    res_df = pd.DataFrame(resultaten)
    st.subheader("Resultaten")
    st.dataframe(res_df)
    # Export
    nu = datetime.now().strftime('%Y-%m-%d-%H-%M')
    buf_xlsx = BytesIO(); res_df.to_excel(buf_xlsx, index=False); buf_xlsx.seek(0)
    st.download_button("Download XLSX", data=buf_xlsx,
                       file_name=f"locatiemanager-gegevens-{nu}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.download_button("Download CSV", data=res_df.to_csv(index=False).encode('utf-8'),
                       file_name=f"locatiemanager-gegevens-{nu}.csv",
                       mime="text/csv")
    # Generate PDF
    buf_pdf = BytesIO()
    doc = SimpleDocTemplate(buf_pdf, pagesize=letter)
    data_pdf = [res_df.columns.tolist()] + res_df.values.tolist()
    table = Table(data_pdf)
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ])
    table.setStyle(style)
    doc.build([table])
    buf_pdf.seek(0)
    st.download_button("Download PDF", data=buf_pdf,
                       file_name=f"locatiemanager-gegevens-{nu}.pdf",
                       mime="application/pdf")
    
    # Dashboard
    st.header("Dashboard & Visualisaties")
    totaal = len(res_df)
    succes = res_df['error'].eq('').sum()
    fouten = totaal - succes
    st.metric("Totaal locaties", totaal)
    st.metric("Succesvolle locaties", succes)
    st.metric("Fouten", fouten)
    # Pie chart
    df_vis = res_df.copy()
    df_vis['Status'] = df_vis['error'].apply(lambda x: 'Ok' if x == '' else 'Error')
    pie = alt.Chart(df_vis).mark_arc().encode(
        theta=alt.Theta(field='count()', type='quantitative'),
        color='Status'
    )
    st.altair_chart(pie, use_container_width=True)