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
3. Voeg je SerpAPI-key in `app.py` in.

## 🚀 Gebruik
```bash
streamlit run app.py
```
Upload een Excelbestand volgens `voorbeeld_bestand.xlsx`.
