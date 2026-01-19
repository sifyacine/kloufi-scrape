import re
import asyncio
import json
import sys
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from utils.emploi import EmploiUtils

try:
    sys.path.insert(1, '../../global')
    from insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] Inserting data to ES index '{index}'")

def parse_diplome(diplome_text):
    # Use regex to split the diploma text by commas and trim extra spaces
    return [item.strip() for item in re.split(r',\s*', diplome_text) if item.strip()]

def parse_header_info(soup):
    """
    Parse header information from the job header containing the job title, employer, location.
    """
    header_data = {
        "titre": "",
        "employeur": "",
        "adresse": "",
        "wilaya": "",
        "images": []
    }
    
    # Extract job title
    h1_title = soup.select_one("h1.h5.text-dark")
    if h1_title:
        header_data["titre"] = re.sub(r'\s+', ' ', h1_title.get_text(strip=True))
    
    # Extract wilaya/location
    h4_location = soup.select_one("h4.h6.text-muted")
    if h4_location:
        wilaya_text = re.sub(r'\s+', ' ', h4_location.get_text(strip=True))
        header_data["wilaya"] = wilaya_text
        header_data["adresse"] = wilaya_text
    
    # Extract employeur from the list-group-item with fa-user icon
    employer_li = soup.select_one("li.list-group-item i.fa-user")
    if employer_li:
        # Get the parent li and extract just the text (not the icon's text)
        employer_text = employer_li.parent.get_text(strip=True)
        header_data["employeur"] = re.sub(r'\s+', ' ', employer_text)
    
    # Look for company images if any
    img_tags = soup.select("img.company-logo") or soup.select("div.slider-annonce img")
    for img in img_tags:
        src = img.get("src")
        if src:
            header_data["images"].append(src)

    return header_data

def extract_carax_details(soup):
    """
    Extract details from the carax section which contains categorization information.
    """
    details = {}
    carax_section = soup.find("div", class_="carax")
    if carax_section:
        for li in carax_section.find_all("li"):
            strong_tag = li.find("strong")
            span_tag = li.find("span")
            if strong_tag and span_tag:
                key = re.sub(r'[:\s]+', ' ', strong_tag.get_text(strip=True)).strip().lower()
                value = span_tag.get_text(strip=True)
                details[key] = value
    return details

def parse_description(soup):
    """
    Extract the job description from the description section.
    """
    desc_div = soup.find("div", class_="description")
    if desc_div:
        return re.sub(r'\s+', ' ', desc_div.get_text(" ", strip=True))
    return ""

async def extract_job_details(url):
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        text_mode=False
    )
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=url,
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                delay_before_return_html=5
            )
        )
        if not result.success:
            raise Exception(f"Failed to load job detail page: {result.error_message}")
        
        soup = BeautifulSoup(result.html, "html.parser")
        
        # 1) Header info (title, employeur, adresse, wilaya, images)
        header = parse_header_info(soup)

        # 2) Extract details from carax section
        carax_details = extract_carax_details(soup)
        
        # 3) Extract and normalize category/domain
        domaine = EmploiUtils.normalize_domaine(carax_details.get("catégories", ""))
        
        # 4) Get publication date
        date_depot = EmploiUtils.normalize_date(carax_details.get("publiée le", ""))
        
        # 5) Get description
        description = parse_description(soup)
        
        # 6) Extract diploma from description since it's not in a structured field
        raw_diplomes = EmploiUtils.extract_diplome_from_description(description)
        
        # Extract specific diploma mentioned in the description
        if "Diplôme en langues" in description:
            raw_diplomes.append("Diplôme en langues")
        
        # 7) Normalize diplomas
        diplome = [
            EmploiUtils.normalize_diplome(item)
            for item in raw_diplomes
            if EmploiUtils.normalize_diplome(item)
        ]
        
        # If no specific diploma was found but there are mentions of education requirements
        if not diplome and "diplôme" in description.lower():
            diplome = ["Diplome universitaire"]  # Default assumption
        
        # 8) Determine contract type (not present in the example HTML)
        contrat = ""
        
        # 9) Extract employer from header
        employeur = header.get("employeur", "")
        
        # 10) Extract number of positions (not present in the example HTML)
        poste = ""
        
        job_details = {
            "date_crawl": datetime.now().isoformat(),
            "url": url,
            "site_origine": "Cvya.dz",
            "titre": header.get("titre", ""),
            "niveau": [],  # Not present in the example HTML
            "numero": url.rstrip("/").split("/")[-1].split(".")[0] if "." in url.rstrip("/").split("/")[-1] else url.rstrip("/").split("/")[-1],
            "date_depot": date_depot,
            "transaction": "Offres",
            "contrat": contrat,
            "diplome": diplome,
            "diplome_src": raw_diplomes,
            "domaine": domaine,
            "description": description,
            "employeur": employeur,
            "poste": poste,
            "adresse": header.get("adresse", ""),
            "wilaya": header.get("wilaya", ""),
            "status": 200,
            "date_verif": datetime.now().isoformat(),
            "images": header.get("images", []),
            "as_photo": "Avec photo" if header.get("images") else "Sans photo",
            "prix": "",
            "prix_unit": "",
            "prix_dec": "",
            "as_prix": "Sans prix",
            "vehicle": "False"
        }
        
        print("Extracted Job Details:", job_details)
        insert_data_to_es(job_details, "emploi")
        return job_details
