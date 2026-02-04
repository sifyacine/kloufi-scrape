import asyncio
import json
import re
import sys
import os
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from utils.emploi import EmploiUtils

try:
    from insert2db.insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] Inserted into '{index}' -> {data['titre']}")

# ====================== MAIN SCRAPING FUNCTION ======================

async def scrape_single_url_with_crawl4ai_and_bs4(url, date_depot, employeur, poste):
    print(f"\nScraping detail page: {url}")

    browser_config = BrowserConfig(headless=True, browser_type="chromium")
    js_commands = [
        "await new Promise(r => setTimeout(r, 5000));",
        "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",
        "await new Promise(r => setTimeout(r, 3000));",
    ]

    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        js_code=js_commands,
        delay_before_return_html=12
    )

    async with AsyncWebCrawler(verbose=False, config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=config)

        if not result.success:
            print(f"Failed to load {url}: {result.error_message}")
            return

        soup = BeautifulSoup(result.html, "html.parser")

        # === Basic Info ===
        titre_tag = soup.find("h1", class_=re.compile(r"MuiTypography"))
        titre = titre_tag.get_text(strip=True) if titre_tag else "N/A"

        numero = url.split("-")[-1] if "-" in url else "N/A"

        # === Job Criteria Grid ===
        criteria_grid = soup.find("div", {"data-testid": "job-criteria"})
        criteria = {}
        if criteria_grid:
            items = criteria_grid.find_all("div", {"data-testid": "pair-item"})
            for item in items:
                label = item.find("p", class_=re.compile(r"mui-377v8o"))
                value = item.find("p", class_=re.compile(r"mui-htp9kd"))
                if label and value:
                    key = label.get_text(strip=True)
                    val = value.get_text(strip=True)
                    criteria[key] = val

        # Extract fields safely
        lieu_travail = criteria.get("Lieu de travail", "N/A")
        wilaya = EmploiUtils.extract_wilaya(lieu_travail)
        secteur = criteria.get("Secteur d'activité", "N/A")
        type_contrat = criteria.get("Type de contrat", "N/A")
        niveau_poste_raw = criteria.get("Niveau de poste", "N/A")
        niveau_etude_raw = criteria.get("Niveau d'étude (diplome)", "N/A")
        date_expiration = criteria.get("Date d'expiration", "N/A")
        nombre_postes = criteria.get("Nombre de postes", "N/A")

        # Normalize experience level
        niveau_poste_list = [item.strip() for item in niveau_poste_raw.split('|')] if '|' in niveau_poste_raw else [niveau_poste_raw]

        # Normalize diplomas
        diplome_list_raw = [d.strip() for d in niveau_etude_raw.replace("Ou", ",").split(",") if d.strip()]
        diplome_list_normalized = [
            EmploiUtils.normalize_diplome(d) for d in diplome_list_raw 
            if EmploiUtils.normalize_diplome(d) is not None
        ]

        # === Description - Updated to match the new example ===
        # The description is inside a MuiPaper with a varying class (e.g., mui-lfntla, mui-1dpesrd)
        # It contains a direct <div><p>...</p>...</div>
        desc_paper = soup.find("div", class_=re.compile(r"MuiPaper-root.*mui-"))
        description = "N/A"
        if desc_paper:
            inner_div = desc_paper.find("div")
            if inner_div:
                description = inner_div.get_text(separator="\n", strip=True)

        # Fallback if not found (previous class)
        if description == "N/A":
            fallback_div = soup.find("div", class_=re.compile(r"mui-1dpesrd"))
            if fallback_div:
                description = fallback_div.get_text(separator="\n", strip=True)

        # === Salary from description ===
        salaire, unite = EmploiUtils.extract_salary(description)
        as_prix = "Avec prix" if salaire else "Sans prix"

        # === Company Logo / Sector Image ===
        img_tag = soup.find("img", alt="Company Logo") or soup.find("img", src=re.compile(r"/images/sectors/"))
        images = []
        as_photo = "Sans photo"
        if img_tag and img_tag.get("src"):
            src = img_tag["src"]
            if src.startswith("/"):
                src = "https://emploitic.com" + src
            images = [src]
            as_photo = "Avec photo"

        # === Build Final Job Object ===
        job = {
            "date_crawl": datetime.now().isoformat(),
            "url": url,
            "site_origine": "Emploitic.com",
            "titre": titre,
            "niveau": niveau_poste_list,
            "numero": numero,
            "date_depot": date_depot,
            "date_expiration": date_expiration,
            "transaction": "Offres",
            "contrat": type_contrat,
            "diplome": diplome_list_normalized or ["Non spécifié"],
            "diplome_src": diplome_list_raw,
            "domaine": secteur,
            "description": description,
            "employeur": employeur,
            "poste": poste,
            "adresse": lieu_travail,
            "wilaya": wilaya,
            "nombre_postes": nombre_postes,
            "status": 200,
            "date_verif": datetime.now().isoformat(),
            "images": images,
            "as_photo": as_photo,
            "prix": salaire,
            "prix_unit": unite,
            "prix_dec": float(salaire.replace(" ", "")) if salaire and salaire.isdigit() else 0,
            "as_prix": as_prix,
            "vehicle": ""
        }

        print(json.dumps(job, indent=2, ensure_ascii=False))
        insert_data_to_es(job, "emploi")