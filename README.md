# Kinderopvang Locatiemanager Scraper

Dit is een Streamlit-webapplicatie waarmee je automatisch de zakelijke contactgegevens (naam locatiemanager en e-mail) ophaalt van kinderopvanglocaties in Nederland.

## 📦 Structuur
```
kinderopvang-locatiemanager-scraper/
├── app.py
├── requirements.txt
├── voorbeeld_bestand.xlsx
├── README.md
└── .gitignore
```

## ⚙️ Installatie
1. Clone deze repository:
   ```bash
git clone https://github.com/<jouw-gebruikersnaam>/kinderopvang-locatiemanager-scraper.git
cd kinderopvang-locatiemanager-scraper
```
2. Installeer dependencies:
   ```bash
pip install -r requirements.txt
```
3. **SerpAPI API Key verkrijgen**
   
   - Ga naar [SerpAPI](https://serpapi.com/) en maak een gratis account aan.
   - Na inloggen vind je je persoonlijke API Key onder "Dashboard → API Key".
   - Vervang in `app.py` de placeholder:
     ```python
     SERPAPI_KEY = "JOUW_SERPAPI_API_KEY_HIER"
     ```
     met jouw gekopieerde key.
   - Optioneel: sla de key op als environment-variabele (aanbevolen):
     ```bash
     export SERPAPI_KEY="<jouw_api_key>"
     ```
     en wijzig `app.py` om te lezen uit `os.getenv("SERPAPI_KEY")`.

## 🚀 Gebruik
```bash
streamlit run app.py
```
Upload een Excelbestand volgens `voorbeeld_bestand.xlsx`.
