# Kinderopvang Locatiemanager Scraper

Streamlit-webapp met:
- Multi-user login: Google OAuth of Admin
- Bulk upload & handmatige invoer
- SerpAPI-zoek, Playwright-fallback
- Filters (geen manager, provincie)
- Export: XLSX, CSV, PDF (placeholder)
- Dashboard & visualisaties

## Structuur
```
kinderopvang-locatiemanager-scraper/
├── app.py
├── requirements.txt
├── voorbeeld_bestand.xlsx
├── README.md
└── .gitignore
```

## Installatie
```bash
git clone https://github.com/<jouw-gebruikersnaam>/kinderopvang-locatiemanager-scraper.git
cd kinderopvang-locatiemanager-scraper
pip install -r requirements.txt
playwright install
```

## Configuratie (Secrets)
Plaats in `.streamlit/secrets.toml` (niet commiten):
```toml
GOOGLE_CLIENT_ID = "<your_client_id>"
GOOGLE_CLIENT_SECRET = "<your_client_secret>"
REDIRECT_URI = "http://localhost:8501"
```

## Gebruik
```bash
streamlit run app.py
```
- Kies login-methode (Google of Admin)
- Stel je SerpAPI-key in
- Kies Bulk upload of Handmatige invoer
- Start scraping en download resultaten

