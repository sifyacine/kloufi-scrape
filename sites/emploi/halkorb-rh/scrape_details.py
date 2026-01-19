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

def parse_header_info(soup):
    """
    Parse header information from the first panel containing the job title, employer, location and image.
    """
    header_data = {
        "titre": "",
        "employeur": "",
        "adresse": "",
        "wilaya": "",
        "images": []
    }
    
    # Find the header panel using more specific selector
    header_panel = soup.select_one("div.panel.panel-bordered > header.panel-body")
    
    if header_panel:
        # Extract job title
        h3 = header_panel.find("h3")
        if h3:
            header_data["titre"] = re.sub(r'\s+', ' ', h3.get_text(strip=True))
        
        # Extract employer
        company_span = header_panel.find("span", attrs={"data-qa": "company-name"})
        if company_span:
            # Find the strong tag within the span for the company name
            strong_tag = company_span.find("strong")
            if strong_tag:
                header_data["employeur"] = re.sub(r'\s+', ' ', strong_tag.get_text(strip=True))
            else:
                header_data["employeur"] = re.sub(r'\s+', ' ', company_span.get_text(strip=True))
        
        # Extract location
        location_span = header_panel.find("span", attrs={"data-qa": "job-locations"})
        if location_span:
            # Find the strong tag within the span for the location
            strong_tag = location_span.find("strong")
            if strong_tag:
                loc_text = re.sub(r'\s+', ' ', strong_tag.get_text(strip=True))
            else:
                loc_text = re.sub(r'\s+', ' ', location_span.get_text(strip=True))
            
            header_data["adresse"] = loc_text
            
            # Extract wilaya (first part of the address before comma)
            parts = [p.strip() for p in loc_text.split(",") if p.strip()]
            if parts:
                header_data["wilaya"] = parts[0]
        
        # Extract company logo image
        img_tag = header_panel.find("img")
        if img_tag:
            src = img_tag.get("src")
            if src:
                header_data["images"].append(src)
    
    return header_data

def parse_dl_details(soup):
    """
    Parse job details from definition lists (<dl> tags) found within panels.
    Uses regex to extract numeric values (e.g. number of postes) for better matching.
    """
    details = {}
    
    # Find all panels with dl tags
    panels = soup.find_all("div", class_="panel panel-bordered")
    
    for panel in panels:
        panel_body = panel.find("div", class_="panel-body")
        if not panel_body:
            continue
            
        for dl in panel_body.find_all("dl"):
            dt = dl.find("dt")
            dd = dl.find("dd")
            
            if dt and dd:
                key = re.sub(r'\s+', ' ', dt.get_text(strip=True)).lower()
                value = re.sub(r'\s+', ' ', dd.get_text(strip=True))
                details[key] = value
    
    return details

def parse_description(soup):
    """
    Extract the job description from the description panel.
    """
    # Find the details-description div which contains the job description
    desc_div = soup.find("div", class_="details-description")
    
    if desc_div:
        # Extract all text content while preserving some structure
        description = desc_div.get_text(" ", strip=True)
        # Clean up whitespace
        description = re.sub(r'\s+', ' ', description)
        return description
    
    return ""

async def extract_job_details(url=None, html_content=None):
    """
    Parse job details from either a URL or provided HTML content.
    Returns a structured dictionary with all job information.
    """
    if not url and not html_content:
        raise ValueError("Either URL or HTML content must be provided")
    
    # If URL is provided, fetch the page
    if url and not html_content:
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
            
            html_content = result.html
    
    # Parse the HTML content
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Extract header information
    header = parse_header_info(soup)
    
    # Extract details from definition lists
    dl_details = parse_dl_details(soup)
    
    # Extract job description
    description = parse_description(soup)
    
    # Extract specific fields with proper cleaning
    poste_text = dl_details.get("nombre de postes", "")
    poste = ""
    if poste_text:
        match = re.search(r'\d+', poste_text)
        if match:
            poste = match.group()
    
    # Get sector/domain and normalize it
    domaine_raw = dl_details.get("secteur d'activité", "")
    domaine = EmploiUtils.normalize_domaine(domaine_raw)
    
    # Get and normalize posting date
    date_depot_text = dl_details.get("date de création", "")
    date_depot = EmploiUtils.normalize_date(date_depot_text)
    
    # Get position level
    niveau_text = dl_details.get("niveau de poste", "")
    niveau = [niveau_text] if niveau_text else []
    
    # Get diploma requirements and normalize
    diplome_text = dl_details.get("niveau d'étude (diplome)", "")
    diplome_raw = [diplome_text] if diplome_text else []
    diplome = [EmploiUtils.normalize_diplome(d) for d in diplome_raw if EmploiUtils.normalize_diplome(d)]
    
    # Get contract type
    contrat = dl_details.get("type de contrat", "")
    
    # Extract job ID from URL if available
    job_id = ""
    if url:
        # Extract job ID from URL patterns like:
        # https://ats.talenteo.com/job-apply/fe387f329528662e66fe?src=joblisting
        
        # First, remove any query parameters
        base_url = url.split("?")[0]
        
        # Extract using regex pattern matching job-apply/ID or job/ID
        id_match = re.search(r'(?:job|job-apply)/([a-zA-Z0-9]+)', base_url)
        if id_match:
            job_id = id_match.group(1)
    
    # Compile all job details into a structured dictionary
    job_details = {
        "date_crawl": datetime.now().isoformat(),
        "url": url or "",
        "site_origine": "Talenteo.com" if url and "talenteo.com" in url else "Talenteo.com",
        "titre": header.get("titre", ""),
        "niveau": niveau,
        "numero": job_id,
        "date_depot": date_depot,
        "transaction": "Offres",
        "contrat": contrat,
        "diplome": diplome,
        "diplome_src": diplome_raw,  # Store original diploma text
        "domaine": domaine,
        "domaine_src": domaine_raw,  # Store original domain/sector text
        "description": description,
        "employeur": header.get("employeur", ""),
        "poste": poste,
        "adresse": header.get("adresse", ""),
        "wilaya": header.get("wilaya", ""),
        "status": 200,
        "date_verif": datetime.now().isoformat(),
        "images": header.get("images", []),
        "as_photo": "Avec photo" if header.get("images", []) else "Sans photo",
        "prix": "",
        "prix_unit": "",
        "prix_dec": "",
        "as_prix": "Sans prix",
        "vehicle": "False"
    }
    
    print("Extracted Job Details:", job_details)
    return job_details
