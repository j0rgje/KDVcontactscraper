# Kinderopvang Locatiemanager Scraper

Streamlit-webapplicatie om zakelijke contactgegevens (e-mail, telefoon, adres, functietitel) van kinderopvanglocaties in Nederland te verzamelen.

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
```bash
# Clone
git clone https://github.com/<jouw-gebruikersnaam>/kinderopvang-locatiemanager-scraper.git
cd kinderopvang-locatiemanager-scraper

# Installeer dependencies
pip install -r requirements.txt

# Playwright initialiseren
playwright install
```

## 🔑 SerpAPI API Key
1. Ga naar [SerpAPI](https://serpapi.com/) en maak een gratis account aan.  
2. Na inloggen vind je je API Key onder **Dashboard → API Key**.  
3. Sla de key op als environment-variabele:
   ```bash
   export SERPAPI_KEY="<jouw_api_key>"
   ```
   Of voer de key in in de UI van de app als hierom gevraagd wordt.

## 🚀 Gebruik
```bash
streamlit run app.py
```
1. Voer je SerpAPI Key in (of laat de app ‘m ophalen uit de environment).  
2. Upload een Excelbestand (gebruik `voorbeeld_bestand.xlsx` als template).  
3. Klik op **Start scraping** en bekijk de voortgang.  
4. Download het resultaat als Excel via de download-knop.

## 📝 Voorbeeld bestand (`voorbeeld_bestand.xlsx`)
| locatienaam              | plaats    |
| ------------------------ | --------- |
| Kinderdagverblijf De Zon | Amsterdam |
| Speelhoeve De Vlinder    | Utrecht   |

Opslaan als **`voorbeeld_bestand.xlsx`**.

## 📄 .gitignore
```
__pycache__/
*.pyc
*.xlsx
.env
```
