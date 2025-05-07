# Kinderopvang Locatiemanager Scraper

Streamlit-webapplicatie om zakelijke contactgegevens (e-mail, telefoon, adres, functietitel) van kinderopvanglocaties in Nederland te verzamelen.

Nu met **gratis DuckDuckGo-zoekmethode** (geen betaalde API nodig).

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

## 🚀 Gebruik
```bash
streamlit run app.py
```
1. Upload een Excelbestand (`voorbeeld_bestand.xlsx`).
2. Klik op **Start scraping**.
3. Download de resultaten.

## 📄 .gitignore
```
__pycache__/
*.pyc
*.xlsx
.env
```
