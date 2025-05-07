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
from serpapi import GoogleSearch
from authlib.integrations.requests_client import OAuth2Session
import altair as alt

# 1) Pagina-configuratie
st.set_page_config(page_title="Locatiemanager Finder", layout="wide")
st.title("Kinderopvang Locatiemanager Scraper")

# 2) Login keuze: Google OAuth of Admin
login_method = st.selectbox(
    "Login via:", ["Google OAuth", "Admin"]
)

authenticated = False

if login_method == "Google OAuth":
    # Google OAuth setup
    CLIENT_ID = st.secrets.get("GOOGLE_CLIENT_ID", "")
    CLIENT_SECRET = st.secrets.get("GOOGLE_CLIENT_SECRET", "")
    REDIRECT_URI = st.secrets.get("REDIRECT_URI", "")
    oauth = OAuth2Session(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scope="openid email profile",
        redirect_uri=REDIRECT_URI,
    )
    if "code" not in st.experimental_get_query_params():
        auth_url, state = oauth.create_authorization_url(
            "https://accounts.google.com/o/oauth2/auth"
        )
        st.session_state["oauth_state"] = state
        st.markdown(f"[Log in met Google]({auth_url})")
        st.stop()
    else:
        code = st.experimental_get_query_params()["code"][0]
        token = oauth.fetch_token(
            "https://oauth2.googleapis.com/token",
            code=code,
        )
        userinfo = oauth.get(
            "https://openidconnect.googleapis.com/v1/userinfo"
        ).json()
        st.success(f"Ingelogd als {userinfo['email']}")
        authenticated = True

elif login_method == "Admin":
    # Admin login credentials
    admin_user = "JornBrem"
    admin_pass = "ewfpoiWF14rq"
    user = st.text_input("Admin gebruikersnaam")
    pwd = st.text_input("Wachtwoord", type="password")
    if st.button("Login als Admin"):
        if user == admin_user and pwd == admin_pass:
            st.success("Admin ingelogd")
            authenticated = True
        else:
            st.error("Onjuiste gebruikersnaam of wachtwoord")
            st.stop()

# Stop als niet geauthenticeerd
if not authenticated:
    st.stop()

# 3) SerpAPI Key beheer
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
if not SERPAPI_KEY:
    key = st.text_input("SerpAPI Key", type="password")
    if key:
        SERPAPI_KEY = key
        st.session_state["SERPAPI_KEY"] = key
elif "SERPAPI_KEY" in st.session_state:
    SERPAPI_KEY = st.session_state["SERPAPI_KEY"]

# 4) Zoek- en scrape-functies (met caching)
@st.cache_data
def zoek_website(locatienaam: str, plaats: str) -> str | None:
    params = {
        "engine": "google",
        "q": f"{locatienaam} {plaats} kinderopvang",
        "api_key": SERPAPI_KEY,
        "num": 1,
    }
    try:
        resp = GoogleSearch(params).get_dict()
        return resp.get("organic_results", [])[0].get("link")
    except Exception:
        return None

@st.cache_data
def scrape_page(url: str) -> dict:
    result = {"emails": [], "telefoons": [], "adressen": [], "managers": [], "error": ""}
    try:
        r = requests.get(url, timeout=10); r.raise_for_status(); content = r.text
        if not re.search(r"[@0-9]", content):
            with sync_playwright() as p:
                b = p.chromium.launch(headless=True)
                pg = b.new_page(); pg.goto(url, timeout=15000)
                content = pg.content(); b.close()
        soup = BeautifulSoup(content, "html.parser"); text = soup.get_text(separator="\n")
        result["emails"] = re.findall(r"[\w\.-]+@[\w\.-]+", text)
        result["telefoons"] = [
            phonenumbers.format_number(m.number, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
            for m in phonenumbers.PhoneNumberMatcher(text, "NL")
        ]
        result["adressen"] = list({
            tag.get_text(strip=True)
            for tag in soup.find_all(["address","p","span","div"])
            if re.search(r"\b[A-Z][a-z]+(?:straat|laan|weg|plein|dreef)\s*\d+", tag.get_text())
        })
        result["managers"] = [
            line.strip() for line in text.split("\n")
            if re.search(r"\blocatiemanager\b", line, flags=re.IGNORECASE)
        ]
    except Exception as e:
        result["error"] = str(e)
    return result

# 5) UI: modus keuze (bulk of handmatig)
mode = st.radio("Invoermodus:", ["Bulk upload", "Handmatige invoer"])
input_df = pd.DataFrame()
if mode == "Bulk upload":
    file = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])
    if file: input_df = pd.read_excel(file)
elif mode == "Handmatige invoer":
    naam = st.text_input("Locatienaam"); plaats = st.text_input("Plaats")
    if st.button("Voeg toe"): input_df = input_df.append({"locatienaam":naam,"plaats":plaats}, ignore_index=True)

# 6) Filters & export-opties
with st.expander("Filters & Export-opties"):
    no_manager = st.checkbox("Alleen locaties zonder manager")
    provincie = st.selectbox("Filter provincie:", ["", "Drenthe","Flevoland","Friesland","Gelderland","Groningen","Limburg","Noord-Brabant","Noord-Holland","Overijssel","Utrecht","Zeeland","Zuid-Holland"])
    export_csv = st.checkbox("CSV export")
    export_pdf = st.checkbox("PDF report")

# 7) Start scraping
if st.button("Start scraping") and not input_df.empty:
    results = []; errors = []; progress = st.progress(0); status=st.empty()
    for i, row in input_df.iterrows():
        status.text(f"Verwerk {i+1}/{len(input_df)}: {row['locatienaam']}")
        site = zoek_website(row['locatienaam'],row['plaats']); time.sleep(1)
        data = scrape_page(site) if site else {'error':'Geen website'}
        results.append({**row.to_dict(), **data, 'website':site})
        if data['error']: errors.append({'locatie':row['locatienaam'],'error':data['error']})
        progress.progress((i+1)/len(input_df))
    df_res = pd.DataFrame(results)
    if no_manager: df_res = df_res[df_res['managers'].map(len)==0]
    if provincie: df_res = df_res[df_res['plaats']==provincie]
    st.header("Dashboard & Statistieken")
    st.metric("Totaal locaties", len(results))
    succes=df_res['error'].eq('').sum(); st.metric("Succespercentage", f"{succes}/{len(results)}")
    chart=alt.Chart(pd.DataFrame({'idx':range(len(df_res)),'ok':df_res['error'].eq('').astype(int)})).mark_line().encode(x='idx',y='ok')
    st.altair_chart(chart, use_container_width=True)
    buf=BytesIO(); df_res.to_excel(buf,index=False); buf.seek(0)
    st.download_button("Download XLSX",buf,file_name=f"res-{datetime.now().strftime('%Y%m%d-%H%M')}.xlsx")
    if export_csv: st.download_button("Download CSV", df_res.to_csv(index=False).encode('utf-8'),file_name='res.csv')
    if export_pdf: st.info("PDF-export in ontwikkeling")
    st.subheader("Resultaten")
    st.dataframe(df_res)
    if errors: st.warning("Fouten:" ), st.table(pd.DataFrame(errors))
