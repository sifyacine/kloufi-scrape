import asyncio
import json
import re
import sys
import os
from datetime import datetime
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from utils.emploi import EmploiUtils

try:
    from insert2db.insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] Inserting data to ES index '{index}'")

async def extract_job_details(url):
    """Extract detailed information from a globaljob job posting"""
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
            raise Exception(f"Failed to load detail page: {result.error_message}")
        
        soup = BeautifulSoup(result.html, "html.parser")
        
        # Initialize fields
        titre = ""
        date_depot = ""
        wilaya = ""
        diplome_list = []
        diplome_src = []
        contrat = ""
        niveau = []
        description = ""
        employeur = ""
        poste = ""
        images = []
        
        # Extract title - typically in h1 or h2
        title_tag = soup.find("h1") or soup.find("h2", class_=re.compile(r"(job-title|titre)"))
        if title_tag:
            titre = title_tag.get_text(strip=True)
        
        # Extract job details from structured data or specific sections
        # Look for job metadata (contract, location, date, etc.)
        details_section = soup.find("div", class_=re.compile(r"(job-details|details|info)"))
        if details_section:
            # Extract contract type
            contrat_span = details_section.find("span", class_=re.compile(r"(contract|contrat)"))
            if contrat_span:
                contrat = contrat_span.get_text(strip=True)
            
            # Extract location/wilaya
            wilaya_span = details_section.find("span", class_=re.compile(r"(location|wilaya)"))
            if wilaya_span:
                wilaya = EmploiUtils.extract_wilaya(wilaya_span.get_text(strip=True))
            
            # Extract date
            date_span = details_section.find("span", class_=re.compile(r"(date|publication)"))
            if date_span:
                date_depot = EmploiUtils.normalize_date(date_span.get_text(strip=True))
            
            # Extract diploma/degree
            degree_span = details_section.find("span", class_=re.compile(r"(degree|diplome|niveau)"))
            if degree_span:
                degree_text = degree_span.get_text(strip=True)
                diplome_src.append(degree_text)
                normalized = EmploiUtils.normalize_diplome(degree_text)
                if normalized:
                    diplome_list.append(normalized)
            
            # Extract experience level
            exp_span = details_section.find("span", class_=re.compile(r"(experience|niveau)"))
            if exp_span:
                exp_text = exp_span.get_text(strip=True)
                if exp_text:
                    niveau.append(exp_text)
            
            # Extract number of positions
            post_span = details_section.find("span", class_=re.compile(r"(post|poste)"))
            if post_span:
                poste = post_span.get_text(strip=True)
        
        # Extract description
        desc_div = soup.find("div", class_=re.compile(r"(description|content|texte)"))
        if desc_div:
            description = desc_div.get_text(separator="\n", strip=True)
        
        # Extract additional diploma info from description
        if description:
            raw_desc_diplomes = EmploiUtils.extract_diplome_from_description(description)
            diplome_src.extend(raw_desc_diplomes)
            for d in raw_desc_diplomes:
                normalized = EmploiUtils.normalize_diplome(d)
                if normalized and normalized not in diplome_list:
                    diplome_list.append(normalized)
        
        # Extract employer/company logo
        logo_img = soup.find("img", class_=re.compile(r"(logo|company|employer)"))
        if logo_img and logo_img.get("src"):
            src = logo_img["src"]
            if src.startswith("/"):
                src = "https://globaljob-dz.com" + src
            if src.startswith("http"):
                images.append(src)
        
        # Extract numero from URL
        numero = re.search(r"/poste/([^/]+)$", url.rstrip("/"))
        numero = numero.group(1) if numero else url.split("/")[-1]
        
        # Build final job object
        job = {
            "date_crawl": datetime.now().isoformat(),
            "url": url,
            "site_origine": "Globaljob-dz.com",
            "titre": titre,
            "niveau": niveau,
            "numero": numero,
            "date_depot": date_depot or datetime.now().strftime('%Y-%m-%d'),
            "transaction": "Offres",
            "contrat": contrat,
            "diplome": diplome_list or ["Non spécifié"],
            "diplome_src": diplome_src,
            "domaine": "",  # Not always available on globaljob
            "description": description,
            "employeur": employeur,
            "poste": poste,
            "adresse": wilaya,
            "wilaya": wilaya,
            "status": 200,
            "date_verif": datetime.now().isoformat(),
            "images": images,
            "as_photo": "Avec photo" if images else "Sans photo",
            "prix": "",
            "prix_unit": "",
            "prix_dec": "",
            "as_prix": "Sans prix",
            "vehicle": ""
        }
        
        print(json.dumps(job, indent=2, ensure_ascii=False))
        insert_data_to_es(job, "emploi")
        return job
