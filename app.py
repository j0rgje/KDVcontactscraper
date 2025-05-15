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
import streamlit.components.v1 as components
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
import json
from typing import List, Dict
from urllib.parse import urljoin
import asyncio
import aiohttp
from PIL import Image
import io
import base64

# Page configuration
st.set_page_config(page_title="Locatiemanager Finder", layout="wide")

# Initialize session state
for key in ["session", "user", "login_error", "signup_error", "signup_success", "manual_rows", 
           "selected_team", "user_role", "search_history", "notes", "teams", "scraping_in_progress", "resultaten"]:
    if key not in st.session_state:
        st.session_state[key] = None if key != "signup_success" else False

if st.session_state.manual_rows is None:
    st.session_state.manual_rows = []
if st.session_state.search_history is None:
    st.session_state.search_history = []
if st.session_state.notes is None:
    st.session_state.notes = {}
if st.session_state.teams is None:
    st.session_state.teams = []
if st.session_state.scraping_in_progress is None:
    st.session_state.scraping_in_progress = False
if st.session_state.resultaten is None:
    st.session_state.resultaten = []

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
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                if res.user and res.session:
                    st.session_state.session = res.session
                    st.session_state.user = {"email": res.user.email, "id": res.user.id}
                    st.session_state.login_error = None
                    st.rerun()
                else:
                    st.session_state.login_error = "Ongeldige inloggegevens. Controleer je e-mail en wachtwoord."
            except Exception as e:
                st.session_state.login_error = f"Inloggen mislukt: {str(e)}"
                
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
    
    # Settings expander met account info en team beheer
    with st.expander("⚙️ Instellingen"):
        st.write(f"📧 Account: {user_email}")
        
        # Team management sectie
        st.subheader("🏢 Team Beheer")
        if st.session_state.user:
            # Haal teams op waar gebruiker lid van is
            teams_response = supabase.table('teams').select('*').execute()
            teams = teams_response.data if hasattr(teams_response, 'data') else []
            st.session_state.teams = teams
            
            if teams:
                team_names = [team['name'] for team in teams]
                selected_team = st.selectbox("Selecteer Team", ["Persoonlijk"] + team_names)
                st.session_state.selected_team = selected_team
                
                if selected_team != "Persoonlijk":
                    team = next(team for team in teams if team['name'] == selected_team)
                    
                    # Team beheer opties voor team eigenaar
                    if team.get('owner_id') == st.session_state.user['id']:
                        st.markdown("---")
                        st.markdown("##### Team Instellingen")
                        
                        # Team leden beheer
                        with st.expander("👥 Teamleden Beheren"):
                            new_member = st.text_input("Voeg teamlid toe (email)")
                            if st.button("➕ Lid Toevoegen", key="add_member"):
                                try:
                                    supabase.table('team_members').insert({
                                        'team_id': team['id'],
                                        'user_email': new_member
                                    }).execute()
                                    st.success(f"Gebruiker {new_member} toegevoegd aan team!")
                                except Exception as e:
                                    st.error(f"Kon gebruiker niet toevoegen: {str(e)}")
                        
                        # Logo upload sectie
                        with st.expander("🖼️ Team Logo"):
                            uploaded_file = st.file_uploader("Upload team logo (PNG, JPG)", type=['png', 'jpg', 'jpeg'])
                            if uploaded_file is not None:
                                try:
                                    # Open en resize het logo
                                    image = Image.open(uploaded_file)
                                    # Behoud aspect ratio en maak max 200px breed
                                    max_width = 200
                                    ratio = max_width / image.size[0]
                                    new_size = (max_width, int(image.size[1] * ratio))
                                    image = image.resize(new_size, Image.LANCZOS)
                                    
                                    # Converteer naar base64
                                    buffered = io.BytesIO()
                                    image.save(buffered, format="PNG")
                                    img_str = base64.b64encode(buffered.getvalue()).decode()
                                    img_data = f"data:image/png;base64,{img_str}"
                                    
                                    # Update het logo in de database
                                    supabase.table('teams').update({
                                        'logo_url': img_data
                                    }).eq('id', team['id']).execute()
                                    
                                    st.success("Logo succesvol geüpload!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Kon logo niet uploaden: {str(e)}")
                            
                            if team.get('logo_url'):
                                if st.button("🗑️ Verwijder Logo"):
                                    try:
                                        supabase.table('teams').update({
                                            'logo_url': None
                                        }).eq('id', team['id']).execute()
                                        st.success("Logo verwijderd!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Kon logo niet verwijderen: {str(e)}")
                        
                        # Team verwijderen optie
                        with st.expander("⚠️ Gevaarlijke Zone"):
                            st.warning("Let op: Deze actie kan niet ongedaan worden gemaakt!")
                            if st.button("🗑️ Team Verwijderen", type="primary"):
                                try:
                                    # Verwijder eerst alle team members
                                    supabase.table('team_members').delete().eq('team_id', team['id']).execute()
                                    # Verwijder dan het team zelf
                                    supabase.table('teams').delete().eq('id', team['id']).execute()
                                    st.success("Team succesvol verwijderd!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Kon team niet verwijderen: {str(e)}")
            
            # Team aanmaken
            st.markdown("---")
            with st.expander("➕ Nieuw Team Aanmaken"):
                new_team_name = st.text_input("Team naam")
                if st.button("Team Aanmaken"):
                    try:
                        supabase.table('teams').insert({
                            'name': new_team_name,
                            'owner_id': st.session_state.user['id']
                        }).execute()
                        st.success("Team aangemaakt!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Kon team niet aanmaken: {str(e)}")
        
        st.markdown("---")
        if st.button("🚪 Log uit"):
            supabase.auth.sign_out()
            for key in ['session','user','login_error','signup_error','signup_success','selected_team']:
                st.session_state[key] = None
            st.rerun()

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

# Enhanced async scraping functions
async def fetch_page(session, url):
    try:
        async with session.get(url, timeout=10) as response:
            return await response.text()
    except Exception as e:
        return None

async def scrape_deep(url, max_depth=2):
    result = {"emails": set(), "telefoons": set(), "adressen": set(), "managers": set(), "error": ""}
    visited = set()
    base_url = url

    async with aiohttp.ClientSession() as session:
        async def process_page(url, depth):
            if depth > max_depth or url in visited:
                return
            visited.add(url)
            
            html = await fetch_page(session, url)
            if not html:
                return

            soup = BeautifulSoup(html, 'html.parser')
            text = soup.get_text(separator="\n")
            
            # Extract data
            result['emails'].update(re.findall(r"[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}", text))
            for match in phonenumbers.PhoneNumberMatcher(text, "NL"):
                result['telefoons'].add(phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.INTERNATIONAL))
            result['adressen'].update(re.findall(r"[A-Z][a-z]+(?:straat|laan|weg|plein|dreef)\s*\d+|\d{4}\s?[A-Z]{2}", text))
            result['managers'].update(line.strip() for line in text.split("\n") if re.search(r"locatiemanager|manager|directeur", line, flags=re.IGNORECASE))
            
            # Find more links
            if depth < max_depth:
                links = soup.find_all('a', href=True)
                for link in links:
                    href = link['href']
                    if href.startswith('/') or href.startswith(base_url):
                        full_url = urljoin(base_url, href)
                        if full_url not in visited and base_url in full_url:
                            await process_page(full_url, depth + 1)

        try:
            await process_page(url, 0)
        except Exception as e:
            result['error'] = str(e)

    return {k: list(v) if isinstance(v, set) else v for k, v in result.items()}

# Function to backup search if SerpAPI fails
async def backup_search(locatienaam, plaats):
    query = f"{locatienaam} {plaats} kinderopvang"
    search_url = f"https://www.google.com/search?q={query}"
    
    async with aiohttp.ClientSession() as session:
        try:
            html = await fetch_page(session, search_url)
            if html:
                soup = BeautifulSoup(html, 'html.parser')
                for link in soup.find_all('a'):
                    href = link.get('href', '')
                    if 'url?q=' in href and not 'google.com' in href:
                        return href.split('url?q=')[1].split('&')[0]
        except Exception:
            pass
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
if st.session_state.session:
    # Logo weergave bovenaan de pagina
    if st.session_state.selected_team and st.session_state.selected_team != "Persoonlijk":
        team = next((t for t in st.session_state.teams if t['name'] == st.session_state.selected_team), None)
        if team and team.get('logo_url'):
            st.image(team['logo_url'], width=200)
    
    st.title("Kinderopvang Locatiemanager Scraper")

# Tabs voor hoofdnavigatie
tab1, tab2, tab3 = st.tabs(["Zoeken", "Geschiedenis", "Notities"])

with tab1:
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
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("Voeg toe"):
                if naam and plaats:
                    st.session_state.manual_rows.append({"locatienaam": naam, "plaats": plaats})
                else:
                    st.warning("Vul zowel locatienaam als plaats in.")
        
        if st.session_state.manual_rows:
            input_df = pd.DataFrame(st.session_state.manual_rows)
            st.write("### Handmatige invoer", input_df)
            
            # Verwijder optie toevoegen
            with st.expander("Verwijder invoer"):
                te_verwijderen = st.multiselect(
                    "Selecteer rijen om te verwijderen",
                    options=range(len(st.session_state.manual_rows)),
                    format_func=lambda x: f"{st.session_state.manual_rows[x]['locatienaam']} - {st.session_state.manual_rows[x]['plaats']}"
                )
                if st.button("Verwijder geselecteerde"):
                    for index in sorted(te_verwijderen, reverse=True):
                        st.session_state.manual_rows.pop(index)
                    st.rerun()

    # Start scraping
    if not input_df.empty:
        start_button = st.button("Start scraping", disabled=st.session_state.scraping_in_progress)
        if start_button:
            st.session_state.scraping_in_progress = True
            st.rerun()
        
        if st.session_state.scraping_in_progress:
            with st.spinner('Bezig met scrapen van locaties... Dit kan enkele minuten duren.'):
                st.session_state.resultaten = []
                progress = st.progress(0)
                
                async def process_all_locations():
                    for idx, row in input_df.iterrows():
                        naam, plaats = str(row['locatienaam']), str(row['plaats'])
                        
                        # Try SerpAPI first, then fallback
                        site = zoek_website_bij_naam(naam, plaats)
                        if not site:
                            site = await backup_search(naam, plaats)
                        
                        if site:
                            data = await scrape_deep(site)
                        else:
                            data = {'error': 'Geen website gevonden'}

                        resultaat = {
                            'locatienaam': naam,
                            'plaats': plaats,
                            'website': site,
                            'emails': ", ".join(data.get('emails', [])),
                            'telefoons': ", ".join(data.get('telefoons', [])),
                            'adressen': ", ".join(data.get('adressen', [])),
                            'managers': " | ".join(data.get('managers', [])),
                            'error': data.get('error', '')
                        }
                        
                        # Save to history in Supabase
                        if st.session_state.user:
                            try:
                                supabase.table('search_history').insert({
                                    'user_id': st.session_state.user['id'],
                                    'search_data': resultaat,
                                    'timestamp': datetime.now().isoformat()
                                }).execute()
                            except Exception as e:
                                st.warning(f"Kon geschiedenis niet opslaan: {str(e)}")
                        
                        st.session_state.resultaten.append(resultaat)
                        progress.progress((idx+1)/len(input_df))

                # Run async scraping
                asyncio.run(process_all_locations())
                st.session_state.scraping_in_progress = False
                st.success('Scraping voltooid!')
        
        # Show results
        if st.session_state.resultaten:
            res_df = pd.DataFrame(st.session_state.resultaten)
            st.subheader("Resultaten")
            st.dataframe(res_df)
        
        # Export and visualizations
        if st.session_state.resultaten:
            res_df = pd.DataFrame(st.session_state.resultaten)
            
            # Export section
            nu = datetime.now().strftime('%Y-%m-%d-%H-%M')
            buf_xlsx = BytesIO()
            res_df.to_excel(buf_xlsx, index=False)
            buf_xlsx.seek(0)
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

with tab2:
    if st.session_state.user:
        st.header("Zoekgeschiedenis")
        # Haal geschiedenis op uit Supabase
        history_response = supabase.table('search_history')\
            .select('*')\
            .eq('user_id', st.session_state.user['id'])\
            .order('timestamp', desc=True)\
            .execute()
        
        if history_response.data:
            history_df = pd.DataFrame([
                {
                    'timestamp': h['timestamp'],
                    **h['search_data']
                } for h in history_response.data
            ])
            
            # Filter opties
            col1, col2 = st.columns(2)
            with col1:
                filter_date = st.date_input("Filter op datum", value=None)
            with col2:
                filter_plaats = st.selectbox("Filter op plaats", 
                                           ["Alle"] + list(history_df['plaats'].unique()))
            
            # Pas filters toe
            if filter_date:
                history_df = history_df[pd.to_datetime(history_df['timestamp']).dt.date == filter_date]
            if filter_plaats != "Alle":
                history_df = history_df[history_df['plaats'] == filter_plaats]
            
            # Toon geschiedenis
            st.dataframe(history_df)
            
            # Export geschiedenis
            if st.button("Exporteer Geschiedenis"):
                nu = datetime.now().strftime('%Y-%m-%d-%H-%M')
                buf_xlsx = BytesIO()
                history_df.to_excel(buf_xlsx, index=False)
                buf_xlsx.seek(0)
                st.download_button("Download Geschiedenis (XLSX)", 
                                 data=buf_xlsx,
                                 file_name=f"zoekgeschiedenis-{nu}.xlsx",
                                 mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.info("Nog geen zoekgeschiedenis beschikbaar")
    else:
        st.warning("Log in om je zoekgeschiedenis te bekijken")

with tab3:
    if st.session_state.user:
        st.header("Notities")
        
        # Haal bestaande notities op
        notes_response = supabase.table('notes')\
            .select('*')\
            .eq('user_id', st.session_state.user['id'])\
            .execute()
        
        # Converteer naar dict voor snelle lookup
        notes_dict = {note['locatie_id']: note for note in notes_response.data} if notes_response.data else {}
        
        # Toon notities voor laatste zoekresultaten
        if st.session_state.resultaten:
            for idx, res in enumerate(st.session_state.resultaten):
                with st.expander(f"{res['locatienaam']} - {res['plaats']}"):
                    locatie_id = f"{res['locatienaam']}_{res['plaats']}"
                    existing_note = notes_dict.get(locatie_id, {}).get('content', '')
                    new_note = st.text_area("Notitie", value=existing_note, key=f"note_{idx}")
                    
                    if new_note != existing_note:
                        if st.button("Opslaan", key=f"save_{idx}"):
                            try:
                                if locatie_id in notes_dict:
                                    # Update bestaande notitie
                                    supabase.table('notes')\
                                        .update({'content': new_note})\
                                        .eq('locatie_id', locatie_id)\
                                        .execute()
                                else:
                                    # Maak nieuwe notitie
                                    supabase.table('notes')\
                                        .insert({
                                            'user_id': st.session_state.user['id'],
                                            'locatie_id': locatie_id,
                                            'content': new_note
                                        })\
                                        .execute()
                                st.success("Notitie opgeslagen!")
                            except Exception as e:
                                st.error(f"Kon notitie niet opslaan: {str(e)}")
        else:
            st.info("Zoek eerst naar locaties om notities toe te voegen")
    else:
        st.warning("Log in om notities te kunnen maken")