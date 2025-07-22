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
from streamlit_modal import Modal
import subprocess
import tempfile
import os
import openai
import hashlib
from datetime import datetime
import json

# Page configuration must be the first Streamlit command
st.set_page_config(page_title="Locatiemanager Finder", layout="wide")

# Supabase initialization
SUPABASE_URL = st.secrets.get("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Application configuration
APP_CONFIG = {
    "login_logo_url": "https://github.com/j0rgje/KDVcontactscraper/blob/main/ChatGPT%20Image%2016%20mei%202025,%2011_54_16.png?raw=true",
    "login_logo_width": 200,
    "app_name": "Locatiemanager Finder",
    "admin_emails": ["jornbrem@gmail.com"]  # Voeg hier admin emails toe
}

# Functies voor app settings
def load_app_settings():
    try:
        settings = supabase.table('app_settings').select('*').execute()
        if settings.data:
            for setting in settings.data:
                if setting['key'] == 'login_logo_width':
                    APP_CONFIG[setting['key']] = int(setting['value'])
                else:
                    APP_CONFIG[setting['key']] = setting['value']
    except Exception as e:
        st.error(f"Kon app instellingen niet laden: {str(e)}")

def save_app_setting(key: str, value: str):
    try:
        # Check of de instelling al bestaat
        existing = supabase.table('app_settings').select('*').eq('key', key).execute()
        if existing.data:
            # Update bestaande instelling
            supabase.table('app_settings').update({'value': str(value), 'updated_at': datetime.now().isoformat()}).eq('key', key).execute()
        else:
            # Maak nieuwe instelling aan
            supabase.table('app_settings').insert({'key': key, 'value': str(value)}).execute()
        return True
    except Exception as e:
        st.error(f"Kon instelling niet opslaan: {str(e)}")
        return False

# Function to initialize app settings if they don't exist
def initialize_app_settings():
    try:
        # Check if settings exist
        settings = supabase.table('app_settings').select('*').execute()
        if not settings.data:
            # Initialize with default settings
            supabase.table('app_settings').insert([
                {
                    'key': 'login_logo_url',
                    'value': "https://github.com/j0rgje/KDVcontactscraper/blob/main/ChatGPT%20Image%2016%20mei%202025,%2011_54_16.png?raw=true"
                },
                {
                    'key': 'login_logo_width',
                    'value': "200"
                }
            ]).execute()
            st.success("Logo instellingen zijn geïnitialiseerd!")
    except Exception as e:
        st.error(f"Kon initiële instellingen niet aanmaken: {str(e)}")

# Laad app settings bij opstarten
load_app_settings()
initialize_app_settings()

# Admin/dev mode check functie
def is_admin_user(user_email: str) -> bool:
    return user_email in APP_CONFIG["admin_emails"] if user_email else False

# Initialize modal voor team verwijderen en teamlid verwijderen
modal = Modal("Team verwijderen", key="delete_modal")
member_modal = Modal("Teamlid verwijderen", key="delete_member_modal")

# Custom CSS voor de pop-up dialog
st.markdown("""
    <style>
    .modal-overlay {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-color: rgba(0,0,0,0.5);
        z-index: 1000;
        display: flex;
        justify-content: center;
        align-items: center;
    }
    .modal-content {
        background-color: white;
        padding: 20px;
        border-radius: 5px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        width: 400px;
        text-align: center.
    }
    .modal-buttons {
        display: flex;
        justify-content: center;
        gap: 10px;
        margin-top: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

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

# Authentication flow
if not st.session_state.session:
    # Toon het geconfigureerde logo
    try:
        st.image(APP_CONFIG["login_logo_url"], width=APP_CONFIG["login_logo_width"])
    except Exception as e:
        st.error(f"Kon het logo niet laden: {str(e)}")
        
    st.title(APP_CONFIG["app_name"])
    
    st.sidebar.title("Authenticatie")
    action = st.sidebar.radio("Actie:", ["Inloggen", "Registreren"])
    
    # Check URL parameters voor verificatie
    params = st.query_params
    
    # Check voor succesvol geverifieerd emailadres
    is_verified = (
        'access_token' in params and 
        'type' in params and 
        params['type'] == 'signup'
    )
    
    if is_verified:
        st.success("✅ Je e-mailadres is succesvol bevestigd! Je kunt hieronder inloggen met je geregistreerde e-mailadres en wachtwoord.")
        # We verwijderen de parameters pas na het tonen van de melding
        st.query_params.clear()
    
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
                    if res.user.email_confirmed_at or res.user.confirmed_at:
                        st.session_state.session = res.session
                        st.session_state.user = {"email": res.user.email, "id": res.user.id}
                        st.session_state.login_error = None
                        st.rerun()
                    else:
                        st.session_state.login_error = "Je e-mail adres is nog niet geverifieerd. Check je inbox voor de verificatie link."
                else:
                    st.session_state.login_error = "Ongeldige inloggegevens. Controleer je e-mail en wachtwoord."
            except Exception as e:
                if "Email not confirmed" in str(e):
                    st.session_state.login_error = "Je e-mail adres is nog niet geverifieerd. Check je inbox voor de verificatie link."
                else:
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
            try:
                # Gebruik de Streamlit app URL als redirect_to
                res = supabase.auth.sign_up({
                    "email": email,
                    "password": password,
                    "options": {
                        "email_redirect_to": "https://kdvcontactscraper-bexaokddvtospg8sthcwp5.streamlit.app/"
                    }
                })
                if hasattr(res, 'error') and res.error:
                    st.session_state.signup_error = res.error.message
                else:
                    st.session_state.signup_success = True
                    st.session_state.signup_error = None
            except Exception as e:
                st.session_state.signup_error = str(e)

        if st.session_state.signup_error:
            st.error(st.session_state.signup_error)
        if st.session_state.signup_success:
            st.success("✉️ Check je e-mail om je account te bevestigen!")
            st.info("Na het verifiëren van je e-mail word je automatisch teruggestuurd naar deze pagina waar je kunt inloggen.")
        st.stop()

# Main UI Sidebar
with st.sidebar:
    user_email = st.session_state.user.get('email', 'Onbekend') if st.session_state.user else 'Onbekend'
    
    # Admin settings interface
    if is_admin_user(user_email):
        st.markdown("---")
        st.subheader("👨‍💼 Admin Instellingen")
        new_logo_url = st.text_input("Login Logo URL", value=APP_CONFIG["login_logo_url"])
        new_logo_width = st.number_input("Logo breedte (px)", value=APP_CONFIG["login_logo_width"], min_value=50, max_value=800)
        if st.button("Update Logo Instellingen"):
            success = True
            # Update beide instellingen in de database
            if not save_app_setting('login_logo_url', new_logo_url):
                success = False
            if not save_app_setting('login_logo_width', str(new_logo_width)):
                success = False
                
            if success:
                # Als beide updates succesvol waren, update de lokale config
                APP_CONFIG["login_logo_url"] = new_logo_url
                APP_CONFIG["login_logo_width"] = new_logo_width
                st.success("Logo instellingen bijgewerkt!")
                # Laad de instellingen opnieuw uit de database
                load_app_settings()
                time.sleep(0.5)  # Kleine vertraging om de database update tijd te geven
                st.rerun()
    
    # Logout button at the top
    if st.button("🚪 Log uit"):
        supabase.auth.sign_out()
        for key in ['session','user','login_error','signup_error','signup_success','selected_team']:
            st.session_state[key] = None
        st.rerun()
    
    # Settings sectie
    st.subheader("⚙️ Instellingen")
    st.write(f"📧 Account: {user_email}")
    
    # Team management sectie
    st.markdown("---")
    st.subheader("🏢 Team Beheer")
    if st.session_state.user:
        # Haal teams op waar gebruiker lid van is
        teams_response = supabase.table('teams').select('*').execute()
        teams = teams_response.data if hasattr(teams_response, 'data') else []
        st.session_state.teams = teams
        
        if teams:
            # Maak kolommen voor team selectie en verwijder knop
            col1, col2 = st.columns([3, 1])
            with col1:
                selected_team = st.selectbox("Selecteer Team", ["Persoonlijk"] + [team['name'] for team in teams])
                st.session_state.selected_team = selected_team
            
            # Toon verwijder knop alleen als een team is geselecteerd (niet voor "Persoonlijk")
            if selected_team != "Persoonlijk":
                team = next(team for team in teams if team['name'] == selected_team)
                
                # Alleen team eigenaar kan verwijderen
                if team.get('owner_id') == st.session_state.user['id']:
                    with col2:
                        if st.button("🗑️", key=f"delete_{team['id']}", help="Verwijder team"):
                            st.session_state.show_delete_confirm = True
                            st.session_state.delete_team_id = team['id']
                            st.session_state.delete_team_name = selected_team
                            st.rerun()

    # Toon de bevestigingsdialoog met modal
    if st.session_state.get('show_delete_confirm'):
        with modal.container():
            st.warning(f"Weet je zeker dat je het team '{st.session_state.delete_team_name}' wilt verwijderen?")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Ja", key="confirm_delete"):
                    try:
                        team_id = st.session_state.delete_team_id
                        # Verwijder eerst alle team members
                        supabase.table('team_members').delete().eq('team_id', team_id).execute()
                        # Verwijder dan het team zelf
                        supabase.table('teams').delete().eq('id', team_id).execute()
                        st.session_state.show_delete_confirm = False
                        st.session_state.delete_team_id = None
                        st.session_state.delete_team_name = None
                        st.rerun()
                    except Exception as e:
                        st.error(f"Kon team niet verwijderen: {str(e)}")
            with col2:
                if st.button("Nee", key="cancel_delete"):
                    st.session_state.show_delete_confirm = False
                    st.session_state.delete_team_id = None
                    st.session_state.delete_team_name = None
                    modal.close()
                    st.rerun()

# Vervolg van de sidebar code
with st.sidebar:
    if st.session_state.user and st.session_state.selected_team != "Persoonlijk":
        team = next((t for t in st.session_state.teams if t['name'] == st.session_state.selected_team), None)
        if team and team.get('owner_id') == st.session_state.user['id']:
            st.markdown("---")
            st.markdown("##### Team Instellingen")
            
            # Team leden beheer
            st.subheader("👥 Teamleden Beheren")
            
            # Huidige teamleden ophalen en weergeven
            team_members = supabase.table('team_members').select('*').eq('team_id', team['id']).execute()
            if team_members.data:
                st.write("Huidige teamleden:")
                for member in team_members.data:
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(member['user_email'])
                    with col2:
                        if st.button("🗑️", key=f"delete_member_{member['id']}", help="Verwijder teamlid"):
                            st.session_state.show_delete_member_confirm = True
                            st.session_state.delete_member_email = member['user_email']
                            st.session_state.delete_member_team_id = team['id']
                            st.rerun()
            
            # Toon de bevestigingsdialoog voor het verwijderen van een teamlid
            if st.session_state.get('show_delete_member_confirm'):
                with member_modal.container():
                    st.warning(f"Weet je zeker dat je het teamlid '{st.session_state.delete_member_email}' wilt verwijderen?")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Ja", key="confirm_delete_member"):
                            try:
                                # Verwijder het teamlid
                                supabase.table('team_members').delete().eq('team_id', st.session_state.delete_member_team_id).eq('user_email', st.session_state.delete_member_email).execute()
                                st.session_state.show_delete_member_confirm = False
                                st.session_state.delete_member_email = None
                                st.session_state.delete_member_team_id = None
                                st.rerun()
                            except Exception as e:
                                st.error(f"Kon teamlid niet verwijderen: {str(e)}")
                    with col2:
                        if st.button("Nee", key="cancel_delete_member"):
                            st.session_state.show_delete_member_confirm = False
                            st.session_state.delete_member_email = None
                            st.session_state.delete_member_team_id = None
                            member_modal.close()
                            st.rerun()
            
            # Nieuw teamlid toevoegen
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
            
            # Logo beheer
            st.markdown("---")
            st.subheader("🖼️ Team Logo")
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
        
        # Team aanmaken
        st.markdown("---")
        st.subheader("➕ Nieuw Team")
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
async def fetch_page(session, url, attempt=1, max_attempts=3):
    """Enhanced page fetching with multiple user agents and anti-bot measures"""
    
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
    ]
    
    headers = {
        'User-Agent': user_agents[(attempt - 1) % len(user_agents)],
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'nl-NL,nl;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"'
    }
    
    try:
        # Add delay between attempts to avoid being flagged as bot
        if attempt > 1:
            await asyncio.sleep(2 * attempt)
            
        timeout = aiohttp.ClientTimeout(total=20, connect=10)
        
        async with session.get(
            url, 
            headers=headers,
            timeout=timeout,
            ssl=False,  # Disable SSL verification as fallback
            allow_redirects=True
        ) as response:
            
            if response.status == 200:
                content = await response.text()
                return content
            elif response.status == 403 and attempt < max_attempts:
                # Try with different user agent on 403 Forbidden
                return await fetch_page(session, url, attempt + 1, max_attempts)
            elif response.status == 429 and attempt < max_attempts:
                # Rate limited, wait longer and retry
                await asyncio.sleep(5 * attempt)
                return await fetch_page(session, url, attempt + 1, max_attempts)
            else:
                return f"HTTP_ERROR_{response.status}"
                
    except asyncio.TimeoutError:
        if attempt < max_attempts:
            return await fetch_page(session, url, attempt + 1, max_attempts)
        return "TIMEOUT_ERROR"
    except Exception as e:
        error_msg = str(e)
        if attempt < max_attempts:
            # Try again with different approach
            return await fetch_page(session, url, attempt + 1, max_attempts)
        return f"FETCH_ERROR: {error_msg}"

def extract_main_content(html):
    """Extraheert hoofdinhoud van HTML en converteert naar schone tekst"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove unwanted elements
    unwanted_tags = ['script', 'style', 'nav', 'header', 'footer', 'aside', 'ads', 'advertisement']
    for tag in unwanted_tags:
        for element in soup.find_all(tag):
            element.decompose()
    
    # Remove elements by class/id (common patterns for non-content)
    unwanted_patterns = [
        'nav', 'navigation', 'menu', 'sidebar', 'footer', 'header', 
        'advertisement', 'ads', 'social', 'share', 'breadcrumb',
        'cookie', 'popup', 'modal', 'overlay'
    ]
    
    for pattern in unwanted_patterns:
        # Find by class
        for element in soup.find_all(attrs={'class': lambda x: x and any(pattern in str(c).lower() for c in x)}):
            element.decompose()
        # Find by id  
        for element in soup.find_all(attrs={'id': lambda x: x and pattern in str(x).lower()}):
            element.decompose()
    
    # Try to find main content area
    main_content = None
    
    # Priority order for main content selectors
    content_selectors = [
        'main', 'article', '[role="main"]',
        '.main-content', '.content', '.post-content', 
        '.entry-content', '.page-content', '.article-content',
        '.container .content', '.wrapper .content'
    ]
    
    for selector in content_selectors:
        main_content = soup.select_one(selector)
        if main_content:
            break
    
    # If no specific main content found, use body but filter more aggressively
    if not main_content:
        main_content = soup.find('body')
        if main_content:
            # Remove more potential noise when using full body
            noise_selectors = [
                'nav', 'header', 'footer', 'aside', '.sidebar', 
                '.widget', '.menu', '.navigation'
            ]
            for selector in noise_selectors:
                for element in main_content.select(selector):
                    element.decompose()
    
    if not main_content:
        main_content = soup  # Last resort
    
    # Convert to structured text
    return html_to_structured_text(main_content)

def html_to_structured_text(element):
    """Converteert HTML element naar gestructureerde tekst"""
    if not element:
        return ""
    
    text_parts = []
    
    def process_element(elem, level=0):
        if elem.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            # Headers with markdown-style formatting
            header_level = int(elem.name[1])
            prefix = '#' * header_level + ' '
            text_parts.append(f"\n{prefix}{elem.get_text(strip=True)}\n")
        
        elif elem.name in ['p', 'div', 'section']:
            # Paragraphs and divs
            text = elem.get_text(separator=' ', strip=True)
            if text and len(text) > 10:  # Ignore very short texts
                text_parts.append(f"{text}\n")
        
        elif elem.name in ['ul', 'ol']:
            # Lists
            for li in elem.find_all('li', recursive=False):
                list_text = li.get_text(separator=' ', strip=True)
                if list_text:
                    text_parts.append(f"• {list_text}\n")
        
        elif elem.name == 'table':
            # Tables - extract as structured text
            for row in elem.find_all('tr'):
                cells = [cell.get_text(strip=True) for cell in row.find_all(['td', 'th'])]
                if any(cells):  # If row has content
                    text_parts.append(" | ".join(cells) + "\n")
        
        elif elem.name in ['span', 'strong', 'em', 'b', 'i']:
            # Inline elements - just get text
            text = elem.get_text(separator=' ', strip=True)
            if text:
                text_parts.append(f"{text} ")
        
        elif elem.name == 'br':
            text_parts.append("\n")
        
        elif elem.name is None:  # Text node
            text = str(elem).strip()
            if text and len(text) > 2:
                text_parts.append(f"{text} ")
        
        else:
            # For other elements, recurse into children
            if hasattr(elem, 'children'):
                for child in elem.children:
                    if hasattr(child, 'name'):
                        process_element(child, level + 1)
    
    process_element(element)
    
    # Join and clean up
    result = ''.join(text_parts)
    
    # Clean up multiple newlines and spaces
    result = re.sub(r'\n\s*\n\s*\n+', '\n\n', result)  # Max 2 newlines
    result = re.sub(r' +', ' ', result)  # Multiple spaces to single
    result = result.strip()
    
    return result

async def quick_check_url(url):
    """Quick check if URL is reachable before full scraping"""
    try:
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=10)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.head(url) as response:
                return response.status in [200, 301, 302, 403]  # 403 might still have content
    except:
        return False

async def scrape_deep(url, max_depth=2):
    result = {"emails": set(), "telefoons": set(), "adressen": set(), "managers": set(), "error": "", "debug_info": []}
    visited = set()
    base_url = url
    
    # Quick check if URL is reachable first
    result["debug_info"].append(f"Starting scrape of: {url}")
    if not await quick_check_url(url):
        result["error"] = "Website is not reachable"
        result["debug_info"].append("-> Pre-check failed: URL is not accessible")
        return {k: list(v) if isinstance(v, set) else v for k, v in result.items()}

    # Configure session to be more browser-like
    connector = aiohttp.TCPConnector(ssl=False, limit=10)
    jar = aiohttp.CookieJar()
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(
        connector=connector,
        cookie_jar=jar,
        timeout=timeout
    ) as session:
        async def process_page(url, depth):
            if depth > max_depth or url in visited:
                return
            visited.add(url)
            
            result["debug_info"].append(f"Scraping: {url} (depth: {depth})")
            
            html = await fetch_page(session, url)
            if not html or isinstance(html, str) and html.startswith(('HTTP_ERROR', 'TIMEOUT_ERROR', 'FETCH_ERROR')):
                error_msg = html if html else "No content returned"
                result["debug_info"].append(f"Failed to fetch {url}: {error_msg}")
                if html and 'HTTP_ERROR_403' in html:
                    result["debug_info"].append("-> Website may be blocking automated requests")
                elif html and 'TIMEOUT_ERROR' in html:
                    result["debug_info"].append("-> Request timed out - website may be slow or blocking")
                elif html and 'FETCH_ERROR' in html:
                    result["debug_info"].append("-> Network or SSL error occurred")
                return

            # Extract main content using advanced content extraction
            structured_text = extract_main_content(html)
            result["debug_info"].append(f"Extracted {len(structured_text)} characters of structured text")
            
            # Also get the original soup for fallback
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove script and style elements from soup  
            for script in soup(["script", "style"]):
                script.extract()
            
            # Get basic text as fallback
            basic_text = soup.get_text(separator=" ", strip=True)
            
            # Also get text from specific contact-related elements
            contact_selectors = [
                'div[class*="contact"]', 'div[class*="Contact"]',
                'div[class*="team"]', 'div[class*="Team"]',
                'div[class*="staff"]', 'div[class*="Staff"]',
                'div[class*="medewerker"]', 'div[class*="Medewerker"]',
                'div[class*="locatie"]', 'div[class*="Locatie"]',
                'section[class*="contact"]', 'section[class*="team"]',
                'footer', '.footer'
            ]
            
            contact_text = ""
            for selector in contact_selectors:
                elements = soup.select(selector)
                for elem in elements:
                    contact_text += " " + elem.get_text(separator=" ", strip=True)
            
            # Use structured text as primary, with fallbacks
            full_text = structured_text + " " + contact_text + " " + basic_text
            
            # Extract emails - verbeterde regex
            email_patterns = [
                r"[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}",
                r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
                r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
            ]
            
            for pattern in email_patterns:
                emails = re.findall(pattern, full_text)
                # Filter out common non-email matches
                for email in emails:
                    if not any(skip in email.lower() for skip in ['@example', '@domain', '@test', 'noreply', 'no-reply']):
                        result['emails'].add(email.lower().strip())
            
            # Extract phone numbers - betere detectie
            phone_text = re.sub(r'[^\d\s\+\-\(\)]+', ' ', full_text)  # Clean text for phone detection
            try:
                for match in phonenumbers.PhoneNumberMatcher(phone_text, "NL"):
                    formatted = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
                    result['telefoons'].add(formatted)
                    
                # Also try to find phone numbers with regex as backup
                phone_patterns = [
                    r'(?:\+31|0031|0)[\s\-]?6[\s\-]?[\d\s\-]{8}',  # Dutch mobile
                    r'(?:\+31|0031|0)[\s\-]?[1-9][\d\s\-]{8}',     # Dutch landline
                    r'\b\d{2,3}[\s\-]?\d{6,7}\b',                  # Simple pattern
                    r'\b\d{10,11}\b'                               # Just digits
                ]
                
                for pattern in phone_patterns:
                    phones = re.findall(pattern, full_text)
                    for phone in phones:
                        cleaned = re.sub(r'[^\d\+]', '', phone)
                        if len(cleaned) >= 9:
                            result['telefoons'].add(phone.strip())
                            
            except Exception as e:
                result["debug_info"].append(f"Phone extraction error: {str(e)}")
            
            # Extract addresses - verbeterde patronen
            address_patterns = [
                r'\b[A-Z][a-z]+(?:straat|laan|weg|plein|dreef|park|square|boulevard)\s*\d+[a-z]?\b',
                r'\b\d{4}\s?[A-Z]{2}\s+[A-Z][a-z]+',  # Postcode + plaats
                r'\b\d{4}\s?[A-Z]{2}\b'  # Alleen postcode
            ]
            
            for pattern in address_patterns:
                addresses = re.findall(pattern, full_text)
                result['adressen'].update(addr.strip() for addr in addresses)
            
            # Extract managers - uitgebreidere zoektermen
            manager_keywords = [
                r'locatiemanager', r'locatie\s*manager',
                r'manager', r'directeur', r'directrice',
                r'leidinggevende', r'teamleider', r'teamleidster',
                r'hoofd\s*vestiging', r'vestigingsmanager',
                r'pedagogisch\s*medewerker', r'pm\b',
                r'locatiecoördinator', r'coördinator'
            ]
            
            lines = full_text.split('\n')
            for line in lines:
                line = line.strip()
                if len(line) > 5 and len(line) < 100:  # Reasonable length for a name/title
                    for keyword in manager_keywords:
                        if re.search(keyword, line, flags=re.IGNORECASE):
                            # Try to extract name from the line
                            # Look for patterns like "Manager: John Doe" or "John Doe - Manager"
                            name_patterns = [
                                r'([A-Z][a-z]+\s+[A-Z][a-z]+)',  # First Last
                                r'([A-Z]\.\s*[A-Z][a-z]+)',      # F. Last
                                r'([A-Z][a-z]+\s+[A-Z]\.\s*[A-Z][a-z]+)'  # First F. Last
                            ]
                            
                            for name_pattern in name_patterns:
                                names = re.findall(name_pattern, line)
                                for name in names:
                                    if not any(skip in name.lower() for skip in ['lorem', 'ipsum', 'example']):
                                        result['managers'].add(f"{name.strip()} ({keyword})")
                            
                            # If no name found, add the whole line if it's reasonable
                            if not result['managers']:
                                result['managers'].add(line[:80] + ("..." if len(line) > 80 else ""))
                            break
            
            result["debug_info"].append(f"Found on {url}: {len(result['emails'])} emails, {len(result['telefoons'])} phones, {len(result['adressen'])} addresses, {len(result['managers'])} managers")
            
            # Find more links for deeper scraping
            if depth < max_depth:
                contact_links = []
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    text = link.get_text(strip=True).lower()
                    
                    # Look for contact/team related links
                    if any(word in text for word in ['contact', 'team', 'over', 'medewerker', 'locatie']):
                        if href.startswith('/'):
                            full_url = urljoin(base_url, href)
                        elif href.startswith(base_url):
                            full_url = href
                        else:
                            continue
                            
                        if full_url not in visited and base_url in full_url:
                            contact_links.append(full_url)
                
                # Process a few promising links
                for link in contact_links[:3]:  # Limit to avoid too many requests
                    await process_page(link, depth + 1)

        try:
            await process_page(url, 0)
        except Exception as e:
            result['error'] = str(e)
            result["debug_info"].append(f"Main scraping error: {str(e)}")

    # Convert sets to lists and remove debug_info from final result
    final_result = {k: list(v) if isinstance(v, set) else v for k, v in result.items() if k != "debug_info"}
    
    # Add debug info only if there were issues
    if result.get('error') or not any([final_result.get('emails'), final_result.get('telefoons'), final_result.get('adressen')]):
        final_result['debug_info'] = result["debug_info"]
    
    return final_result

# Function to backup search if SerpAPI fails
async def backup_search(locatienaam, plaats):
    query = f"{locatienaam} {plaats} kinderopvang"
    search_url = f"https://www.google.com/search?q={query}"
    
    # Configure session to be more browser-like for Google search
    connector = aiohttp.TCPConnector(ssl=False, limit=5)
    jar = aiohttp.CookieJar()
    timeout = aiohttp.ClientTimeout(total=15)
    
    async with aiohttp.ClientSession(
        connector=connector,
        cookie_jar=jar,
        timeout=timeout
    ) as session:
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
    
    # Enhanced headers to mimic real browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'nl-NL,nl;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    try:
        # Create session with headers
        session = requests.Session()
        session.headers.update(headers)
        
        # Try multiple approaches
        for attempt in range(2):
            try:
                if attempt == 0:
                    resp = session.get(url, timeout=15, verify=True)
                else:
                    # Second attempt: disable SSL verification
                    resp = session.get(url, timeout=15, verify=False)
                
                if resp.status_code == 200:
                    break
                elif resp.status_code == 403:
                    # Try with different User-Agent
                    session.headers.update({
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
                    })
                    continue
                else:
                    resp.raise_for_status()
                    
            except requests.exceptions.SSLError:
                if attempt == 0:
                    continue  # Try again without SSL verification
                else:
                    raise
        
        resp.raise_for_status()
        
        # Extract main content using advanced content extraction
        structured_text = extract_main_content(resp.text)
        
        # Also get basic soup text as fallback
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Remove script and style elements from soup
        for script in soup(["script", "style"]):
            script.extract()
        
        basic_text = soup.get_text(separator=" ", strip=True)
        
        # Combine structured and basic text
        text = structured_text + " " + basic_text
        
        # Enhanced email extraction
        email_patterns = [
            r"[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}",
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        ]
        
        emails = set()
        for pattern in email_patterns:
            found = re.findall(pattern, text)
            for email in found:
                if not any(skip in email.lower() for skip in ['example', 'test', 'noreply']):
                    emails.add(email.lower().strip())
        result['emails'] = list(emails)
        
        # Enhanced phone extraction
        phones = set()
        try:
            for match in phonenumbers.PhoneNumberMatcher(text, "NL"):
                formatted = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
                phones.add(formatted)
                
            # Backup regex patterns for Dutch phones
            phone_patterns = [
                r'(?:\+31|0031|0)[\s\-]?6[\s\-]?[\d\s\-]{8}',  # Dutch mobile
                r'(?:\+31|0031|0)[\s\-]?[1-9][\d\s\-]{8}',     # Dutch landline
            ]
            
            for pattern in phone_patterns:
                found_phones = re.findall(pattern, text)
                for phone in found_phones:
                    cleaned = re.sub(r'[^\d\+]', '', phone)
                    if len(cleaned) >= 9:
                        phones.add(phone.strip())
                        
        except Exception:
            pass
            
        result['telefoons'] = list(phones)
        
        # Enhanced address extraction
        addr_patterns = [
            r'\b[A-Z][a-z]+(?:straat|laan|weg|plein|dreef|park|boulevard)\s*\d+[a-z]?\b',
            r'\b\d{4}\s?[A-Z]{2}\s+[A-Z][a-z]+',  # Postcode + plaats
            r'\b\d{4}\s?[A-Z]{2}\b'  # Alleen postcode
        ]
        
        addresses = set()
        for pattern in addr_patterns:
            found = re.findall(pattern, text)
            addresses.update(addr.strip() for addr in found)
        result['adressen'] = list(addresses)
        
        # Enhanced manager extraction
        manager_keywords = [
            r'locatiemanager', r'locatie\s*manager',
            r'manager', r'directeur', r'directrice',
            r'leidinggevende', r'teamleider', r'teamleidster'
        ]
        
        managers = set()
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if 10 < len(line) < 80:  # Reasonable length
                for keyword in manager_keywords:
                    if re.search(keyword, line, flags=re.IGNORECASE):
                        managers.add(line)
                        break
        result['managers'] = list(managers)
        
    except Exception as e:
        result['error'] = str(e)
    return result

# Advanced scraping fallback methods
def selenium_scrape_fallback(url):
    """Selenium-gebaseerde scraper voor websites die requests blokkeren"""
    try:
        # Check if we can import selenium
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        # Chrome options voor headless browsing
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Start browser
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(url)
        
        # Wait for page load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Get page source
        html_content = driver.page_source
        driver.quit()
        
        # Extract content
        structured_text = extract_main_content(html_content)
        return {"success": True, "content": structured_text, "method": "selenium"}
        
    except ImportError:
        return {"success": False, "error": "Selenium not installed", "method": "selenium"}
    except Exception as e:
        return {"success": False, "error": str(e), "method": "selenium"}

def proxy_scrape_fallback(url):
    """Scraping via verschillende proxy's"""
    # Gratis proxy lijst (in echte implementatie zou je betere proxies gebruiken)
    proxies = [
        {'http': 'http://proxy1.com:8080', 'https': 'https://proxy1.com:8080'},
        {'http': 'http://proxy2.com:3128', 'https': 'https://proxy2.com:3128'},
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'nl-NL,nl;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    for i, proxy in enumerate(proxies):
        try:
            response = requests.get(url, proxies=proxy, headers=headers, timeout=15)
            if response.status_code == 200:
                content = extract_main_content(response.text)
                return {"success": True, "content": content, "method": f"proxy_{i+1}"}
        except Exception as e:
            continue
    
    return {"success": False, "error": "All proxies failed", "method": "proxy"}

def scrapeowl_api_fallback(url):
    """Scraping via ScrapeOwl API service"""
    try:
        # Dit zou een echte API key nodig hebben
        api_key = st.secrets.get("SCRAPEOWL_API_KEY", "demo_key")
        api_url = "https://api.scrapeowl.com/v1/scrape"
        
        payload = {
            'api_key': api_key,
            'url': url,
            'render_js': True,
            'wait_for': 2000,
        }
        
        response = requests.post(api_url, data=payload, timeout=30)
        if response.status_code == 200:
            content = extract_main_content(response.text)
            return {"success": True, "content": content, "method": "scrapeowl"}
        else:
            return {"success": False, "error": f"API error: {response.status_code}", "method": "scrapeowl"}
            
    except Exception as e:
        return {"success": False, "error": str(e), "method": "scrapeowl"}

def wayback_machine_fallback(url):
    """Haal content op via Wayback Machine"""
    try:
        # Wayback Machine API
        wayback_url = f"http://archive.org/wayback/available?url={url}"
        response = requests.get(wayback_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('archived_snapshots', {}).get('closest'):
                archived_url = data['archived_snapshots']['closest']['url']
                
                # Haal gearchiveerde versie op
                archived_response = requests.get(archived_url, timeout=15)
                if archived_response.status_code == 200:
                    content = extract_main_content(archived_response.text)
                    return {"success": True, "content": content, "method": "wayback", "archived_url": archived_url}
        
        return {"success": False, "error": "No archived version found", "method": "wayback"}
        
    except Exception as e:
        return {"success": False, "error": str(e), "method": "wayback"}

def curl_subprocess_fallback(url):
    """Gebruik curl via subprocess (soms werkt dit als requests faalt)"""
    try:
        # Curl command met browser headers
        curl_cmd = [
            'curl', '-s', '-L', '--max-time', '15',
            '-H', 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            '-H', 'Accept-Language: nl-NL,nl;q=0.9,en;q=0.8',
            '-H', 'DNT: 1',
            '-H', 'Connection: keep-alive',
            url
        ]
        
        result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=20)
        
        if result.returncode == 0 and result.stdout:
            content = extract_main_content(result.stdout)
            return {"success": True, "content": content, "method": "curl"}
        else:
            return {"success": False, "error": f"Curl failed: {result.stderr}", "method": "curl"}
            
    except Exception as e:
        return {"success": False, "error": str(e), "method": "curl"}

def playwright_scrape_fallback(url):
    """Playwright browser automation (alternatief voor Selenium)"""
    try:
        import subprocess
        import tempfile
        import os
        
        # Gebruik playwright via subprocess als het niet direct beschikbaar is
        playwright_code = f'''
import asyncio
from playwright.async_api import async_playwright

async def scrape_page():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("{url}")
        content = await page.content()
        await browser.close()
        return content

print(asyncio.run(scrape_page()))
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(playwright_code)
            temp_file = f.name
        
        try:
            result = subprocess.run(['python', temp_file], capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout:
                content = extract_main_content(result.stdout)
                return {"success": True, "content": content, "method": "playwright"}
            else:
                return {"success": False, "error": "Playwright execution failed", "method": "playwright"}
        finally:
            os.unlink(temp_file)
            
    except ImportError:
        return {"success": False, "error": "Playwright not installed", "method": "playwright"}
    except Exception as e:
        return {"success": False, "error": str(e), "method": "playwright"}

def httpx_scrape_fallback(url):
    """HTTP/2 scraping met HTTPX library"""
    try:
        import httpx
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'nl-NL,nl;q=0.9,en;q=0.8',
        }
        
        with httpx.Client(http2=True, timeout=15, headers=headers) as client:
            response = client.get(url)
            if response.status_code == 200:
                content = extract_main_content(response.text)
                return {"success": True, "content": content, "method": "httpx_http2"}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}", "method": "httpx_http2"}
                
    except ImportError:
        return {"success": False, "error": "HTTPX not installed", "method": "httpx_http2"}
    except Exception as e:
        return {"success": False, "error": str(e), "method": "httpx_http2"}

def google_cache_scrape_fallback(url):
    """Scraping via Google Cache"""
    try:
        cache_url = f"http://webcache.googleusercontent.com/search?q=cache:{url}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(cache_url, headers=headers, timeout=15)
        if response.status_code == 200:
            content = extract_main_content(response.text)
            return {"success": True, "content": content, "method": "google_cache"}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}", "method": "google_cache"}
            
    except Exception as e:
        return {"success": False, "error": str(e), "method": "google_cache"}

def archive_today_scrape_fallback(url):
    """Scraping via Archive.today"""
    try:
        # Zoek eerst naar een gearchiveerde versie
        search_url = f"http://archive.today/newest/{url}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(search_url, headers=headers, timeout=15, allow_redirects=True)
        if response.status_code == 200:
            content = extract_main_content(response.text)
            return {"success": True, "content": content, "method": "archive_today"}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}", "method": "archive_today"}
            
    except Exception as e:
        return {"success": False, "error": str(e), "method": "archive_today"}

def scraperapi_scrape_fallback(url):
    """Scraping via ScraperAPI service"""
    try:
        api_key = st.secrets.get("SCRAPERAPI_KEY", "demo_key")
        api_url = "http://api.scraperapi.com"
        
        params = {
            'api_key': api_key,
            'url': url,
            'render': 'true',
            'country_code': 'nl'
        }
        
        response = requests.get(api_url, params=params, timeout=30)
        if response.status_code == 200:
            content = extract_main_content(response.text)
            return {"success": True, "content": content, "method": "scraperapi"}
        else:
            return {"success": False, "error": f"API error: {response.status_code}", "method": "scraperapi"}
            
    except Exception as e:
        return {"success": False, "error": str(e), "method": "scraperapi"}

def mobile_user_agent_scrape_fallback(url):
    """Scraping met mobile user agent"""
    mobile_agents = [
        'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36',
        'Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
    ]
    
    for i, user_agent in enumerate(mobile_agents):
        try:
            headers = {
                'User-Agent': user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'nl-NL,nl;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate',
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                content = extract_main_content(response.text)
                return {"success": True, "content": content, "method": f"mobile_agent_{i+1}"}
                
        except Exception:
            continue
    
    return {"success": False, "error": "All mobile agents failed", "method": "mobile_agent"}

def tor_proxy_scrape_fallback(url):
    """Scraping via TOR network (als beschikbaar)"""
    try:
        # TOR proxy configuratie
        tor_proxies = {
            'http': 'socks5h://127.0.0.1:9050',
            'https': 'socks5h://127.0.0.1:9050'
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0'
        }
        
        response = requests.get(url, proxies=tor_proxies, headers=headers, timeout=20)
        if response.status_code == 200:
            content = extract_main_content(response.text)
            return {"success": True, "content": content, "method": "tor_proxy"}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}", "method": "tor_proxy"}
            
    except Exception as e:
        return {"success": False, "error": str(e), "method": "tor_proxy"}

def different_dns_scrape_fallback(url):
    """Scraping met verschillende DNS servers"""
    dns_servers = ['8.8.8.8', '1.1.1.1', '9.9.9.9']  # Google, Cloudflare, Quad9
    
    for dns in dns_servers:
        try:
            # Dit zou een meer geavanceerde DNS implementatie nodig hebben
            # Voor nu gebruiken we een simpele aanpak
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                content = extract_main_content(response.text)
                return {"success": True, "content": content, "method": f"dns_{dns}"}
                
        except Exception:
            continue
    
    return {"success": False, "error": "All DNS servers failed", "method": "different_dns"}

def save_html_for_ai_analysis(url, html_content, method_used="unknown"):
    """Sla HTML op voor AI-analyse en return file info"""
    try:
        # Maak unieke filename gebaseerd op URL en timestamp
        url_hash = hashlib.md5(url.encode()).hexdigest()[:10]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"scraped_{url_hash}_{timestamp}.html"
        
        # Create een tijdelijke directory als het niet bestaat
        temp_dir = "scraped_html"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
        
        filepath = os.path.join(temp_dir, filename)
        
        # Sla HTML op met metadata
        html_with_metadata = f"""
<!DOCTYPE html>
<!-- SCRAPING METADATA -->
<!-- URL: {url} -->
<!-- Method: {method_used} -->
<!-- Timestamp: {datetime.now().isoformat()} -->
<!-- Filename: {filename} -->
<!-- END METADATA -->

{html_content}
"""
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_with_metadata)
        
        return {
            "success": True,
            "filepath": filepath,
            "filename": filename,
            "url": url,
            "method": method_used,
            "timestamp": datetime.now().isoformat(),
            "file_size": len(html_content)
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "filepath": None
        }

def ai_extract_contact_data(html_content, url="unknown", use_openai=True, model="gpt-3.5-turbo"):
    """Gebruik AI om contactgegevens uit HTML te extraheren"""
    
    # Clean de HTML voor AI processing
    structured_text = extract_main_content(html_content)
    
    # Limiteer de tekst tot ~3000 tekens om binnen API limieten te blijven
    if len(structured_text) > 3000:
        structured_text = structured_text[:3000] + "..."
    
    system_prompt = """Je bent een expert in het extraheren van contactgegevens van kinderopvang websites. 
Analyseer de gegeven tekst en extraher ALLEEN de volgende informatie:

BELANGRIJK: Geef ALLEEN echte, concrete gegevens terug. Geen placeholders of voorbeelden.

Zoek naar:
1. E-mailadressen (echte email adressen, geen voorbeelden)
2. Nederlandse telefoonnummers (mobiel en vast)
3. Adressen (straatnaam + nummer, postcodes)
4. Namen van locatiemanagers, directeuren, of andere contactpersonen
5. Openingstijden (indien vermeld)
6. Vestigingsnamen of locatie-informatie

Retourneer het resultaat in dit EXACTE JSON formaat:
{
    "emails": ["email1@example.nl", "email2@company.com"],
    "telefoons": ["+31 6 12345678", "030-1234567"],
    "adressen": ["Straatnaam 123", "1234 AB Plaatsnaam"],
    "managers": ["Jan de Manager - Locatiemanager", "Marie Janssen - Directeur"],
    "openingstijden": ["Ma-Vr 7:30-18:30", "Za 8:00-17:00"],
    "vestiging_info": ["Vestigingsnaam", "Locatie details"],
    "confidence": 0.8
}

Als je geen informatie vindt, gebruik lege arrays []. Confidence is een getal tussen 0-1."""

    user_prompt = f"""
Website URL: {url}

Tekst om te analyseren:
{structured_text}

Extraher alle contactgegevens volgens de instructies."""

    try:
        if use_openai:
            # OpenAI API call
            openai_api_key = st.secrets.get("OPENAI_API_KEY", "")
            
            if not openai_api_key or openai_api_key == "":
                return {
                    "success": False,
                    "error": "OpenAI API key niet gevonden in secrets",
                    "extracted_data": None
                }
            
            openai.api_key = openai_api_key
            
            response = openai.ChatCompletion.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=1000
            )
            
            ai_response = response.choices[0].message.content.strip()
            
            # Parse JSON response
            try:
                extracted_data = json.loads(ai_response)
                
                return {
                    "success": True,
                    "extracted_data": extracted_data,
                    "raw_response": ai_response,
                    "method": "openai_gpt3.5",
                    "text_length": len(structured_text)
                }
                
            except json.JSONDecodeError as e:
                return {
                    "success": False,
                    "error": f"JSON parse error: {str(e)}",
                    "raw_response": ai_response,
                    "extracted_data": None
                }
        
        else:
            # Fallback: gebruik regel-gebaseerde extractie
            return {
                "success": False,
                "error": "AI extraction not available",
                "extracted_data": None
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"AI extraction failed: {str(e)}",
            "extracted_data": None
        }

def try_all_fallback_methods(url, combine_results=True):
    """Probeer alle beschikbare methoden en combineer de resultaten"""
    methods = [
        ("🤖 Selenium Browser", selenium_scrape_fallback),
        ("🎭 Playwright Browser", playwright_scrape_fallback),
        ("📚 Wayback Machine", wayback_machine_fallback),
        ("📂 Archive.today", archive_today_scrape_fallback),
        ("🔍 Google Cache", google_cache_scrape_fallback),
        ("🔧 Curl Subprocess", curl_subprocess_fallback),
        ("🌐 Proxy Rotation", proxy_scrape_fallback),
        ("📱 Mobile User Agents", mobile_user_agent_scrape_fallback),
        ("🚀 HTTP/2 (HTTPX)", httpx_scrape_fallback),
        ("🧅 TOR Network", tor_proxy_scrape_fallback),
        ("🌍 DNS Rotation", different_dns_scrape_fallback),
        ("🛠️ ScrapeOwl API", scrapeowl_api_fallback),
        ("⚡ ScraperAPI", scraperapi_scrape_fallback)
    ]
    
    results = []
    all_content = []
    successful_methods = []
    
    for method_name, method_func in methods:
        try:
            st.info(f"🔄 Probeer methode: {method_name}")
            result = method_func(url)
            results.append({
                "method": method_name,
                "result": result
            })
            
            if result.get("success"):
                successful_methods.append(method_name)
                content = result.get("content", "")
                if content:
                    all_content.append({
                        "method": method_name,
                        "content": content
                    })
                st.success(f"✅ {method_name} succesvol!")
            else:
                error_msg = result.get("error", "Unknown error")
                st.warning(f"❌ {method_name} gefaald: {error_msg}")
                
        except Exception as e:
            st.error(f"❌ {method_name} exception: {str(e)}")
            results.append({
                "method": method_name, 
                "result": {"success": False, "error": str(e)}
            })
    
    if not combine_results:
        # Oude gedrag - return eerste succesvolle
        for result_data in results:
            if result_data["result"].get("success"):
                return {
                    "success": True,
                    "content": result_data["result"].get("content", ""),
                    "method": result_data["method"],
                    "all_attempts": results
                }
    
    if all_content:
        # Combineer alle content
        combined_content = "\n\n--- CONTENT VAN MEERDERE METHODEN ---\n\n"
        for content_data in all_content:
            combined_content += f"=== {content_data['method']} ===\n"
            combined_content += content_data['content']
            combined_content += "\n\n"
        
        return {
            "success": True,
            "content": combined_content,
            "method": f"Gecombineerd ({len(successful_methods)} methoden)",
            "successful_methods": successful_methods,
            "all_attempts": results,
            "individual_contents": all_content
        }
    
    # Alle methoden gefaald
    return {
        "success": False,
        "error": "All fallback methods failed",
        "all_attempts": results
    }

def extract_and_combine_contact_data(content_list):
    """Combineer contactgegevens van meerdere content bronnen"""
    combined_data = {
        'emails': set(),
        'telefoons': set(), 
        'adressen': set(),
        'managers': set(),
        'sources': {}  # Track which source found what
    }
    
    for content_data in content_list:
        method = content_data['method']
        content = content_data['content']
        
        # Initialize source tracking
        combined_data['sources'][method] = {
            'emails': [],
            'telefoons': [],
            'adressen': [],
            'managers': []
        }
        
        # Extract emails
        email_patterns = [
            r"[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}",
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        ]
        
        for pattern in email_patterns:
            emails = re.findall(pattern, content)
            for email in emails:
                email = email.lower().strip()
                if not any(skip in email for skip in ['example', 'test', 'noreply', 'no-reply']):
                    combined_data['emails'].add(email)
                    combined_data['sources'][method]['emails'].append(email)
        
        # Extract phone numbers
        try:
            for match in phonenumbers.PhoneNumberMatcher(content, "NL"):
                formatted = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
                combined_data['telefoons'].add(formatted)
                combined_data['sources'][method]['telefoons'].append(formatted)
                
            # Backup regex for phones
            phone_patterns = [
                r'(?:\+31|0031|0)[\s\-]?6[\s\-]?[\d\s\-]{8}',  # Dutch mobile
                r'(?:\+31|0031|0)[\s\-]?[1-9][\d\s\-]{8}',     # Dutch landline
                r'\b\d{2,3}[\s\-]?\d{6,7}\b'
            ]
            
            for pattern in phone_patterns:
                phones = re.findall(pattern, content)
                for phone in phones:
                    cleaned = re.sub(r'[^\d\+]', '', phone)
                    if len(cleaned) >= 9:
                        phone = phone.strip()
                        combined_data['telefoons'].add(phone)
                        combined_data['sources'][method]['telefoons'].append(phone)
                        
        except Exception:
            pass
        
        # Extract addresses  
        addr_patterns = [
            r'\b[A-Z][a-z]+(?:straat|laan|weg|plein|dreef|park|boulevard)\s*\d+[a-z]?\b',
            r'\b\d{4}\s?[A-Z]{2}\s+[A-Z][a-z]+',
            r'\b\d{4}\s?[A-Z]{2}\b'
        ]
        
        for pattern in addr_patterns:
            addresses = re.findall(pattern, content)
            for addr in addresses:
                addr = addr.strip()
                combined_data['adressen'].add(addr)
                combined_data['sources'][method]['adressen'].append(addr)
        
        # Extract managers
        manager_keywords = [
            r'locatiemanager', r'locatie\s*manager',
            r'manager', r'directeur', r'directrice',
            r'leidinggevende', r'teamleider', r'teamleidster',
            r'hoofd\s*vestiging', r'vestigingsmanager',
            r'pedagogisch\s*medewerker', r'pm\b'
        ]
        
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if 10 < len(line) < 100:
                for keyword in manager_keywords:
                    if re.search(keyword, line, flags=re.IGNORECASE):
                        combined_data['managers'].add(line)
                        combined_data['sources'][method]['managers'].append(line)
                        break
    
    # Convert sets to lists
    return {
        'emails': list(combined_data['emails']),
        'telefoons': list(combined_data['telefoons']),
        'adressen': list(combined_data['adressen']),
        'managers': list(combined_data['managers']),
        'sources': combined_data['sources']
    }

# Scraper UI
if st.session_state.session:
    st.title("Kinderopvang Locatiemanager Scraper")

# Tabs voor hoofdnavigatie
tab1, tab2, tab3 = st.tabs(["Zoeken", "Geschiedenis", "Notities"])

with tab1:
    # Mode select
    mode = st.radio("Invoermodus:", ["Bestand upload", "Handmatige invoer", "Test website"])
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
                if naam and plaats:  # Changed from 'naam en plaats'
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
    
    elif mode == "Test website":
        st.info("Test de scraper met een directe website URL om te zien of de informatie correct wordt geëxtraheerd.")
        test_url = st.text_input("Website URL (bijvoorbeeld: https://example.com)")
        
        # Content extraction optie
        use_content_extraction = st.checkbox("Gebruik geavanceerde content extractie", value=True, 
                                           help="Extraheert alleen de hoofdinhoud en filtert ruis weg")
        
        # Fallback methode keuze
        fallback_method = st.selectbox(
            "Kies fallback methode bij blokkering:",
            [
                "Automatisch (probeer alle methoden)",
                "🤖 Selenium Browser Automation", 
                "🎭 Playwright Browser Automation",
                "📚 Wayback Machine Archive",
                "📂 Archive.today Archive",
                "🔍 Google Cache",
                "🔧 Curl Subprocess",
                "🌐 Proxy Rotation",
                "📱 Mobile User Agents",
                "🚀 HTTP/2 (HTTPX)",
                "🧅 TOR Network Proxy",
                "🌍 DNS Server Rotation",
                "🛠️ ScrapeOwl API Service",
                "⚡ ScraperAPI Service"
            ],
            help="Deze methode wordt gebruikt als de standaard scraper wordt geblokkeerd"
        )
        
        # Combinatie optie
        combine_all_methods = st.checkbox(
            "🔄 Gebruik ALLE methoden en combineer resultaten", 
            value=True,
            help="Probeert alle scraping methoden (ook als één succesvol is) en combineert alle gevonden data"
        )
        
        # Overzicht van alle beschikbare methoden
        with st.expander("📋 Overzicht van alle 13+ scraping methoden"):
            st.write("""
            **Browser Automation:**
            - 🤖 Selenium (Chrome headless, JavaScript support)
            - 🎭 Playwright (Modern browser automation)
            
            **Archive Services:**
            - 📚 Wayback Machine (Internet Archive)
            - 📂 Archive.today (Recent archives)
            - 🔍 Google Cache (Cached versions)
            
            **Network Techniques:**
            - 🔧 Curl Subprocess (Different network stack)
            - 🌐 Proxy Rotation (Different IP addresses)  
            - 📱 Mobile User Agents (iPhone/Android/iPad)
            - 🚀 HTTP/2 Support (Modern protocol)
            - 🧅 TOR Network (Anonymous routing)
            - 🌍 DNS Server Rotation (Google/Cloudflare/Quad9)
            
            **Commercial APIs:**
            - 🛠️ ScrapeOwl (Professional scraping service)
            - ⚡ ScraperAPI (Enterprise anti-bot bypassing)
            
            **Elke methode gebruikt andere technieken om bot-detectie te omzeilen!**
            """)
        
        st.info("💡 **Tip**: Gebruik 'Alle methoden combineren' voor maximale data-opbrengst!")
        
        # Debug mode toggle
        debug_mode = st.checkbox("🐛 Debug modus", help="Toont gedetailleerde informatie over elke stap")
        
        # AI Extraction options
        st.markdown("---")
        st.subheader("🤖 AI-gebaseerde Extractie")
        
        use_ai_extraction = st.checkbox(
            "🧠 Gebruik AI voor contactgegevens extractie", 
            value=True,
            help="Gebruikt ChatGPT om intelligent contactgegevens uit HTML te extraheren"
        )
        
        save_html_files = st.checkbox(
            "💾 Sla HTML bestanden op", 
            value=True,
            help="Bewaart HTML bestanden lokaal voor analyse en debugging"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            ai_model_choice = st.selectbox(
                "AI Model:",
                ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"],
                help="Kies het OpenAI model voor extractie"
            )
        
        with col2:
            compare_methods = st.checkbox(
                "🔍 Vergelijk AI vs Regex", 
                value=True,
                help="Toont vergelijking tussen AI extractie en traditionele regex"
            )
        
        # OpenAI API key check
        openai_api_key = st.secrets.get("OPENAI_API_KEY", "")
        if use_ai_extraction and not openai_api_key:
            st.warning("⚠️ OpenAI API key niet gevonden in secrets. AI extractie wordt overgeslagen.")
        elif use_ai_extraction and openai_api_key:
            st.success("✅ OpenAI API key gevonden. AI extractie beschikbaar.")
        
        if test_url and st.button("Test Scraping"):
            with st.spinner("Bezig met testen van website..."):
                try:
                    # Test de scraping functie direct
                    if debug_mode:
                        st.info("🔍 Start standaard async scraper...")
                    result = asyncio.run(scrape_deep(test_url))
                    if debug_mode:
                        st.write(f"**Standaard scraper resultaat:** {len(result.get('emails', []))} emails, {len(result.get('telefoons', []))} telefoons")
                    
                    # Check if we need to try advanced fallback methods
                    has_useful_data = (result.get('emails') or result.get('telefoons') or result.get('adressen') or result.get('managers'))
                    scraper_failed = (result.get('error') or 
                                    not has_useful_data or
                                    any('HTTP_ERROR_403' in str(debug) for debug in result.get('debug_info', [])))
                    
                    if debug_mode:
                        st.write(f"**Scraper status:** {'✅ Heeft data' if has_useful_data else '❌ Geen data'}, {'❌ Gefaald' if scraper_failed else '✅ Succesvol'}")
                    
                    # Quick fallback to requests if async scraper completely failed
                    if scraper_failed and not has_useful_data:
                        if debug_mode:
                            st.info("🔧 Probeer basis requests fallback...")
                        else:
                            st.info("🔧 Standaard scraper gefaald, probeer alternatieve methode...")
                        basic_fallback = scrape_contactgegevens(test_url)
                        if basic_fallback and not basic_fallback.get('error'):
                            has_basic_data = (basic_fallback.get('emails') or basic_fallback.get('telefoons') or basic_fallback.get('adressen'))
                            if has_basic_data:
                                result = basic_fallback
                                result['debug_info'] = ['Async scraper gefaald', 'Basis requests scraper succesvol!']
                                scraper_failed = False  # Mark as no longer failed
                                st.success("✅ Basis requests scraper werkte!")
                    
                    if scraper_failed or combine_all_methods:
                        if combine_all_methods:
                            st.info("🔄 Gebruik alle beschikbare methoden en combineer resultaten...")
                            # Gebruik altijd alle methoden als combinatie is aangevinkt
                            advanced_result = try_all_fallback_methods(test_url, combine_results=True)
                        else:
                            st.info("Standaard scraper gefaald, probeer geavanceerde methoden...")
                            
                            # Try the selected fallback method
                            advanced_result = None
                            
                            if fallback_method == "Automatisch (probeer alle methoden)":
                                advanced_result = try_all_fallback_methods(test_url, combine_results=False)
                            elif fallback_method == "🤖 Selenium Browser Automation":
                                advanced_result = selenium_scrape_fallback(test_url)
                            elif fallback_method == "🎭 Playwright Browser Automation":
                                advanced_result = playwright_scrape_fallback(test_url)
                            elif fallback_method == "📚 Wayback Machine Archive":
                                advanced_result = wayback_machine_fallback(test_url)
                            elif fallback_method == "📂 Archive.today Archive":
                                advanced_result = archive_today_scrape_fallback(test_url)
                            elif fallback_method == "🔍 Google Cache":
                                advanced_result = google_cache_scrape_fallback(test_url)
                            elif fallback_method == "🔧 Curl Subprocess":
                                advanced_result = curl_subprocess_fallback(test_url)
                            elif fallback_method == "🌐 Proxy Rotation":
                                advanced_result = proxy_scrape_fallback(test_url)
                            elif fallback_method == "📱 Mobile User Agents":
                                advanced_result = mobile_user_agent_scrape_fallback(test_url)
                            elif fallback_method == "🚀 HTTP/2 (HTTPX)":
                                advanced_result = httpx_scrape_fallback(test_url)
                            elif fallback_method == "🧅 TOR Network Proxy":
                                advanced_result = tor_proxy_scrape_fallback(test_url)
                            elif fallback_method == "🌍 DNS Server Rotation":
                                advanced_result = different_dns_scrape_fallback(test_url)
                            elif fallback_method == "🛠️ ScrapeOwl API Service":
                                advanced_result = scrapeowl_api_fallback(test_url)
                            elif fallback_method == "⚡ ScraperAPI Service":
                                advanced_result = scraperapi_scrape_fallback(test_url)
                        
                        if advanced_result and advanced_result.get('success'):
                            content = advanced_result.get('content', '')
                            
                            # Save HTML and perform AI extraction if enabled
                            saved_files = []
                            ai_results = []
                            
                            if content and 'individual_contents' in advanced_result:
                                # Multiple methods - process each one
                                for content_item in advanced_result['individual_contents']:
                                    method_name = content_item['method']
                                    method_content = content_item['content']
                                    
                                    # Save HTML if enabled
                                    if save_html_files and method_content:
                                        # We need raw HTML, not structured text - let's get it differently
                                        st.info(f"💾 HTML opslaan voor {method_name}...")
                                        
                                        # For now, save the structured content as HTML-like
                                        pseudo_html = f"<html><body><div class='extracted-content'>{method_content.replace('\n', '<br>')}</div></body></html>"
                                        file_info = save_html_for_ai_analysis(test_url, pseudo_html, method_name)
                                        if file_info['success']:
                                            saved_files.append(file_info)
                                            st.success(f"✅ HTML opgeslagen: {file_info['filename']}")
                                    
                                    # AI extraction if enabled
                                    if use_ai_extraction and openai_api_key and method_content:
                                        st.info(f"🤖 AI extractie voor {method_name}...")
                                        ai_result = ai_extract_contact_data(
                                            method_content, 
                                            test_url, 
                                            use_openai=True,
                                            model=ai_model_choice
                                        )
                                        if ai_result['success']:
                                            ai_result['method'] = method_name
                                            ai_results.append(ai_result)
                                            st.success(f"✅ AI extractie voltooid voor {method_name}")
                                        else:
                                            st.warning(f"⚠️ AI extractie gefaald voor {method_name}: {ai_result.get('error', 'Unknown error')}")
                            
                            elif content:
                                # Single method result
                                method_name = advanced_result.get('method', 'unknown')
                                
                                # Save HTML if enabled
                                if save_html_files:
                                    st.info(f"💾 HTML opslaan voor {method_name}...")
                                    pseudo_html = f"<html><body><div class='extracted-content'>{content.replace('\n', '<br>')}</div></body></html>"
                                    file_info = save_html_for_ai_analysis(test_url, pseudo_html, method_name)
                                    if file_info['success']:
                                        saved_files.append(file_info)
                                        st.success(f"✅ HTML opgeslagen: {file_info['filename']}")
                                
                                # AI extraction if enabled
                                if use_ai_extraction and openai_api_key:
                                    st.info(f"🤖 AI extractie voor {method_name}...")
                                    ai_result = ai_extract_contact_data(
                                        content, 
                                        test_url, 
                                        use_openai=True,
                                        model=ai_model_choice
                                    )
                                    if ai_result['success']:
                                        ai_result['method'] = method_name
                                        ai_results.append(ai_result)
                                        st.success(f"✅ AI extractie voltooid voor {method_name}")
                                    else:
                                        st.warning(f"⚠️ AI extractie gefaald voor {method_name}: {ai_result.get('error', 'Unknown error')}")
                            
                            if content:
                                # Check if we have individual contents from multiple methods
                                if 'individual_contents' in advanced_result and advanced_result['individual_contents']:
                                    st.success(f"✅ Data gecombineerd van {len(advanced_result['successful_methods'])} methoden!")
                                    
                                    # Use advanced extraction with source tracking
                                    combined_contact_data = extract_and_combine_contact_data(advanced_result['individual_contents'])
                                    
                                    result = {
                                        'emails': combined_contact_data['emails'],
                                        'telefoons': combined_contact_data['telefoons'],
                                        'adressen': combined_contact_data['adressen'], 
                                        'managers': combined_contact_data['managers'],
                                        'sources': combined_contact_data['sources'],  # Track sources
                                        'debug_info': [
                                            f"Gecombineerde data van: {', '.join(advanced_result.get('successful_methods', []))}",
                                            f"Totaal emails: {len(combined_contact_data['emails'])}",
                                            f"Totaal telefoons: {len(combined_contact_data['telefoons'])}",
                                            f"Totaal adressen: {len(combined_contact_data['adressen'])}",
                                            f"Totaal managers: {len(combined_contact_data['managers'])}",
                                        ]
                                    }
                                else:
                                    # Single method result
                                    st.success(f"✅ Succesvol gescraped met: {advanced_result.get('method')}")
                                    
                                    # Parse the content for contact info (original logic)
                                    emails = re.findall(r"[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}", content)
                                    phones = []
                                    try:
                                        for match in phonenumbers.PhoneNumberMatcher(content, "NL"):
                                            phones.append(phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.INTERNATIONAL))
                                    except:
                                        pass
                                    
                                    addr_patterns = [
                                        r'\b[A-Z][a-z]+(?:straat|laan|weg|plein|dreef)\s*\d+[a-z]?\b',
                                        r'\b\d{4}\s?[A-Z]{2}\b'
                                    ]
                                    addresses = []
                                    for pattern in addr_patterns:
                                        addresses.extend(re.findall(pattern, content))
                                    
                                    managers = []
                                    lines = content.split('\n')
                                    for line in lines:
                                        if 10 < len(line.strip()) < 80:
                                            if re.search(r'locatiemanager|manager|directeur', line, flags=re.IGNORECASE):
                                                managers.append(line.strip())
                                    
                                    # Update result with found data
                                    result = {
                                        'emails': emails,
                                        'telefoons': phones, 
                                        'adressen': addresses,
                                        'managers': managers,
                                        'debug_info': [
                                            f"Succesvol met: {advanced_result.get('method', 'unknown')}",
                                            f"Content lengte: {len(content)} characters"
                                        ]
                                    }
                                
                                # Show all attempts if available
                                if 'all_attempts' in advanced_result:
                                    result['debug_info'].append("--- Alle pogingen ---")
                                    for attempt in advanced_result['all_attempts']:
                                        method = attempt['method']
                                        success = attempt['result'].get('success', False)
                                        error = attempt['result'].get('error', '')
                                        result['debug_info'].append(f"{method}: {'✅' if success else '❌'} {error}")
                            else:
                                result['debug_info'].append(f"Fallback methode werkte maar leverde geen content op")
                        else:
                            error_msg = advanced_result.get('error', 'Unknown error') if advanced_result else 'No result'
                            result['debug_info'] = result.get('debug_info', []) + [f"Alle geavanceerde methoden gefaald: {error_msg}"]
                    
                    st.subheader("Test Resultaten")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("**📧 Emails gevonden:**")
                        if result.get('emails'):
                            for email in result['emails']:
                                st.write(f"• {email}")
                        else:
                            st.write("Geen emails gevonden")
                        
                        st.write("**📞 Telefoonnummers gevonden:**")
                        if result.get('telefoons'):
                            for phone in result['telefoons']:
                                st.write(f"• {phone}")
                        else:
                            st.write("Geen telefoonnummers gevonden")
                    
                    with col2:
                        st.write("**📍 Adressen gevonden:**")
                        if result.get('adressen'):
                            for addr in result['adressen']:
                                st.write(f"• {addr}")
                        else:
                            st.write("Geen adressen gevonden")
                        
                        st.write("**👥 Managers/Medewerkers gevonden:**")
                        if result.get('managers'):
                            for manager in result['managers']:
                                st.write(f"• {manager}")
                        else:
                            st.write("Geen managers gevonden")
                    
                    # Show source breakdown if available
                    if 'sources' in result and result['sources']:
                        st.subheader("📊 Data per methode")
                        
                        # Create tabs for each successful method
                        method_names = list(result['sources'].keys())
                        if len(method_names) > 1:
                            tabs = st.tabs(method_names)
                            
                            for i, (method, method_data) in enumerate(result['sources'].items()):
                                with tabs[i]:
                                    st.write(f"**Data gevonden door {method}:**")
                                    
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        if method_data['emails']:
                                            st.write("📧 **Emails:**")
                                            for email in method_data['emails']:
                                                st.write(f"• {email}")
                                        if method_data['telefoons']:
                                            st.write("📞 **Telefoons:**")
                                            for phone in method_data['telefoons']:
                                                st.write(f"• {phone}")
                                    
                                    with col2:
                                        if method_data['adressen']:
                                            st.write("📍 **Adressen:**")
                                            for addr in method_data['adressen']:
                                                st.write(f"• {addr}")
                                        if method_data['managers']:
                                            st.write("👥 **Managers:**")
                                            for manager in method_data['managers']:
                                                st.write(f"• {manager}")
                                    
                                    # Show stats
                                    total_items = (len(method_data['emails']) + 
                                                 len(method_data['telefoons']) + 
                                                 len(method_data['adressen']) + 
                                                 len(method_data['managers']))
                                    st.info(f"Totaal {total_items} items gevonden door {method}")
                        else:
                            # Single method, show simplified view  
                            st.info("Data gevonden door één methode (zie hierboven)")
                            
                        # Summary comparison
                        st.subheader("🎯 Samenvatting per methode")
                        summary_data = []
                        for method, data in result['sources'].items():
                            summary_data.append({
                                'Methode': method,
                                'Emails': len(data['emails']),
                                'Telefoons': len(data['telefoons']),
                                'Adressen': len(data['adressen']),
                                'Managers': len(data['managers']),
                                'Totaal': len(data['emails']) + len(data['telefoons']) + len(data['adressen']) + len(data['managers'])
                            })
                        
                        if summary_data:
                            import pandas as pd
                            summary_df = pd.DataFrame(summary_data)
                            st.dataframe(summary_df)
                    
                    # Show AI extraction results if available
                    if 'ai_results' in locals() and ai_results:
                        st.markdown("---")
                        st.subheader("🤖 AI Extractie Resultaten")
                        
                        # Combined AI results
                        all_ai_emails = set()
                        all_ai_phones = set()
                        all_ai_addresses = set()
                        all_ai_managers = set()
                        all_ai_openingstijden = set()
                        all_ai_vestiging_info = set()
                        
                        for ai_result in ai_results:
                            extracted = ai_result.get('extracted_data', {})
                            all_ai_emails.update(extracted.get('emails', []))
                            all_ai_phones.update(extracted.get('telefoons', []))
                            all_ai_addresses.update(extracted.get('adressen', []))
                            all_ai_managers.update(extracted.get('managers', []))
                            all_ai_openingstijden.update(extracted.get('openingstijden', []))
                            all_ai_vestiging_info.update(extracted.get('vestiging_info', []))
                        
                        st.subheader("🎯 Gecombineerde AI Resultaten")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write("**📧 AI - Emails gevonden:**")
                            for email in all_ai_emails:
                                st.write(f"• {email}")
                            
                            st.write("**📞 AI - Telefoonnummers gevonden:**")
                            for phone in all_ai_phones:
                                st.write(f"• {phone}")
                            
                            st.write("**📍 AI - Adressen gevonden:**")
                            for addr in all_ai_addresses:
                                st.write(f"• {addr}")
                        
                        with col2:
                            st.write("**👥 AI - Managers gevonden:**")
                            for manager in all_ai_managers:
                                st.write(f"• {manager}")
                            
                            st.write("**🕒 AI - Openingstijden:**")
                            for tijd in all_ai_openingstijden:
                                st.write(f"• {tijd}")
                            
                            st.write("**🏢 AI - Vestiging info:**")
                            for info in all_ai_vestiging_info:
                                st.write(f"• {info}")
                        
                        # Show individual AI results per method
                        if len(ai_results) > 1:
                            st.subheader("🔍 AI Resultaten per methode")
                            ai_tabs = st.tabs([f"🤖 {ai_res['method']}" for ai_res in ai_results])
                            
                            for i, ai_result in enumerate(ai_results):
                                with ai_tabs[i]:
                                    extracted = ai_result.get('extracted_data', {})
                                    confidence = extracted.get('confidence', 'Onbekend')
                                    
                                    st.info(f"**Model:** {ai_result.get('method', 'unknown')} | **Confidence:** {confidence}")
                                    
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        if extracted.get('emails'):
                                            st.write("📧 **Emails:**")
                                            for email in extracted['emails']:
                                                st.write(f"• {email}")
                                        if extracted.get('telefoons'):
                                            st.write("📞 **Telefoons:**")
                                            for phone in extracted['telefoons']:
                                                st.write(f"• {phone}")
                                    
                                    with col2:
                                        if extracted.get('adressen'):
                                            st.write("📍 **Adressen:**")
                                            for addr in extracted['adressen']:
                                                st.write(f"• {addr}")
                                        if extracted.get('managers'):
                                            st.write("👥 **Managers:**")
                                            for manager in extracted['managers']:
                                                st.write(f"• {manager}")
                                    
                                    if extracted.get('openingstijden'):
                                        st.write("🕒 **Openingstijden:**")
                                        for tijd in extracted['openingstijden']:
                                            st.write(f"• {tijd}")
                                    
                                    if extracted.get('vestiging_info'):
                                        st.write("🏢 **Vestiging Info:**")
                                        for info in extracted['vestiging_info']:
                                            st.write(f"• {info}")
                        
                        # Comparison between AI and Regex if enabled
                        if compare_methods and result:
                            st.markdown("---")
                            st.subheader("🔍 Vergelijking: AI vs Regex")
                            
                            comparison_data = []
                            
                            # Compare emails
                            regex_emails = set(result.get('emails', []))
                            ai_only_emails = all_ai_emails - regex_emails
                            regex_only_emails = regex_emails - all_ai_emails
                            common_emails = all_ai_emails & regex_emails
                            
                            comparison_data.append({
                                'Type': 'Emails',
                                'Regex': len(regex_emails),
                                'AI': len(all_ai_emails),
                                'Gemeenschappelijk': len(common_emails),
                                'Alleen AI': len(ai_only_emails),
                                'Alleen Regex': len(regex_only_emails)
                            })
                            
                            # Compare phones
                            regex_phones = set(result.get('telefoons', []))
                            ai_only_phones = all_ai_phones - regex_phones
                            regex_only_phones = regex_phones - all_ai_phones
                            common_phones = all_ai_phones & regex_phones
                            
                            comparison_data.append({
                                'Type': 'Telefoons',
                                'Regex': len(regex_phones),
                                'AI': len(all_ai_phones),
                                'Gemeenschappelijk': len(common_phones),
                                'Alleen AI': len(ai_only_phones),
                                'Alleen Regex': len(regex_only_phones)
                            })
                            
                            # Compare addresses
                            regex_addresses = set(result.get('adressen', []))
                            ai_only_addresses = all_ai_addresses - regex_addresses
                            regex_only_addresses = regex_addresses - all_ai_addresses
                            common_addresses = all_ai_addresses & regex_addresses
                            
                            comparison_data.append({
                                'Type': 'Adressen',
                                'Regex': len(regex_addresses),
                                'AI': len(all_ai_addresses),
                                'Gemeenschappelijk': len(common_addresses),
                                'Alleen AI': len(ai_only_addresses),
                                'Alleen Regex': len(regex_only_addresses)
                            })
                            
                            comp_df = pd.DataFrame(comparison_data)
                            st.dataframe(comp_df)
                            
                            # Show unique findings
                            if ai_only_emails or ai_only_phones or ai_only_addresses:
                                st.subheader("🤖 Uniek gevonden door AI:")
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    if ai_only_emails:
                                        st.write("**📧 Emails:**")
                                        for email in ai_only_emails:
                                            st.write(f"• {email}")
                                with col2:
                                    if ai_only_phones:
                                        st.write("**📞 Telefoons:**")
                                        for phone in ai_only_phones:
                                            st.write(f"• {phone}")
                                with col3:
                                    if ai_only_addresses:
                                        st.write("**📍 Adressen:**")
                                        for addr in ai_only_addresses:
                                            st.write(f"• {addr}")
                            
                            if regex_only_emails or regex_only_phones or regex_only_addresses:
                                st.subheader("🔧 Uniek gevonden door Regex:")
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    if regex_only_emails:
                                        st.write("**📧 Emails:**")
                                        for email in regex_only_emails:
                                            st.write(f"• {email}")
                                with col2:
                                    if regex_only_phones:
                                        st.write("**📞 Telefoons:**")
                                        for phone in regex_only_phones:
                                            st.write(f"• {phone}")
                                with col3:
                                    if regex_only_addresses:
                                        st.write("**📍 Adressen:**")
                                        for addr in regex_only_addresses:
                                            st.write(f"• {addr}")
                    
                    # Show saved files info
                    if 'saved_files' in locals() and saved_files:
                        st.markdown("---")
                        st.subheader("💾 Opgeslagen HTML Bestanden")
                        
                        for file_info in saved_files:
                            with st.expander(f"📁 {file_info['filename']} ({file_info.get('method', 'unknown')})"):
                                st.write(f"**Bestandsgrootte:** {file_info['file_size']:,} characters")
                                st.write(f"**Timestamp:** {file_info['timestamp']}")
                                st.write(f"**Bestandspad:** `{file_info['filepath']}`")
                                st.write(f"**URL:** {file_info['url']}")
                                st.write(f"**Scraping methode:** {file_info.get('method', 'unknown')}")
                                
                                if st.button(f"🗑️ Verwijder bestand", key=f"delete_{file_info['filename']}"):
                                    try:
                                        if os.path.exists(file_info['filepath']):
                                            os.remove(file_info['filepath'])
                                            st.success(f"✅ Bestand {file_info['filename']} verwijderd")
                                        else:
                                            st.warning("⚠️ Bestand niet gevonden")
                                    except Exception as e:
                                        st.error(f"❌ Kon bestand niet verwijderen: {str(e)}")
                    
                    # Altijd debug info tonen bij test modus
                    if 'debug_info' in result:
                        st.subheader("🐛 Debug Informatie")
                        for debug_line in result['debug_info']:
                            st.text(debug_line)
                    
                    # Toon geëxtraheerde tekst optie
                    if st.checkbox("Toon geëxtraheerde tekst", help="Zie de schone tekst die uit de HTML is gehaald"):
                        try:
                            # Haal de website opnieuw op om de tekst te laten zien
                            import requests
                            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                            resp = requests.get(test_url, headers=headers, timeout=10)
                            if resp.status_code == 200:
                                extracted_text = extract_main_content(resp.text)
                                st.subheader("📄 Geëxtraheerde hoofdinhoud")
                                st.text_area("Schone tekst", extracted_text, height=300)
                            else:
                                st.error(f"Kon website niet laden: HTTP {resp.status_code}")
                        except Exception as e:
                            st.error(f"Fout bij tekst extractie: {str(e)}")
                    
                    if result.get('error'):
                        st.error(f"Fout opgetreden: {result['error']}")
                    
                    # Mogelijkheid om test toe te voegen aan reguliere scraping
                    if st.button("Voeg toe aan scraping lijst"):
                        naam = st.text_input("Locatienaam voor deze test", key="test_naam")
                        plaats = st.text_input("Plaats voor deze test", key="test_plaats")
                        if naam and plaats:
                            st.session_state.manual_rows.append({"locatienaam": naam, "plaats": plaats})
                            st.success("Toegevoegd aan handmatige invoer!")
                        
                except Exception as e:
                    st.error(f"Test mislukt: {str(e)}")
                    st.write("Controleer of de URL correct is en probeer opnieuw.")

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
                        # First try the advanced async scraper
                        data = await scrape_deep(site)
                        
                        # If that fails due to bot blocking, fallback to requests-based scraper
                        if (data.get('error') or 
                            (not data.get('emails') and not data.get('telefoons') and not data.get('adressen')) or
                            any('HTTP_ERROR_403' in str(debug) for debug in data.get('debug_info', []))):
                            
                            # No progress.text available in this context
                            fallback_data = scrape_contactgegevens(site)
                            
                            # If fallback found data, use it
                            if not fallback_data.get('error') and (fallback_data.get('emails') or fallback_data.get('telefoons')):
                                data = fallback_data
                                data['debug_info'] = [f"Gebruikt fallback scraper (requests) na async failure"]
                            else:
                                # Keep original async result but note the fallback attempt
                                data['debug_info'] = data.get('debug_info', []) + [f"Fallback scraper ook gefaald: {fallback_data.get('error', 'geen data gevonden')}"]
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
            
            # Toon debug info als er problemen zijn
            debug_results = [r for r in st.session_state.resultaten if 'debug_info' in r]
            if debug_results and st.checkbox("Toon debug informatie"):
                st.warning("Debug informatie beschikbaar voor problematische locaties:")
                for result in debug_results:
                    if 'debug_info' in result:
                        with st.expander(f"Debug: {result['locatienaam']} - {result['plaats']}"):
                            st.write("**Website:**", result.get('website', 'Niet gevonden'))
                            st.write("**Debug log:**")
                            for debug_line in result['debug_info']:
                                st.text(debug_line)
            
            # Verwijder debug_info uit dataframe voor normale weergave
            display_df = res_df.drop(columns=['debug_info'], errors='ignore')
            st.dataframe(display_df)
        
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