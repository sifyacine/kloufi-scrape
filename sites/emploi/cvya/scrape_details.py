import re
import asyncio
import json
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
import sys
sys.path.insert(1, '../../global')

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

def normalize_domaine(domaine):
    mapping = {
        "Formation / Education": "Administration & Management",
        "Achats": "Achat & Logistique",
        "Commercial, vente": "Commerce & Vente",
        "Gestion, comptabilité, finance": "Comptabilité & Audit",
        "Informatique, nouvelles technologies": "Informatique & Internet",
        "Juridique": "Juridique",
        "Management, direction générale": "Administration & Management",
        "Marketing, communication": "Commercial & Marketing",
        "Métiers de la santé et du social": "Medecine & Santé",
        "Métiers des services": "Services",
        "Métiers du BTP": "Construction & Travaux",
        "Production, maintenance, qualité": "Industrie & Production",
        "R&D, gestion de projets": "Recherche & developpement",
        "RH, formation": "Administration & Management",
        "Secrétariat, assistanat":  "Bureautique & Secretariat",
        "Télémarketing, téléassistance": "Commercial & Marketing",
        "Tourisme, hôtellerie, restauration": "Tourisme & Gastronomie",
        "Transport, logistique": "Achat & Logistique",
    }

    return mapping.get(domaine.strip(), domaine.strip())

def normalize_diplome(diplome):
    mapping = {
        "niveau secondaire": "Diplome de collège",
        "niveau terminal": "Diplome de collège",
        "baccalauréat": "Bac",
        "bac +2": "Diplome universitaire",
        "ts bac +2": "Diplome universitaire",
        "ts bac +2 | Formation Professionnelle": "Diplôme professionnel / téchnique",
        "licence": "Diplome universitaire",
        "licence (lmd), bac + 3": "Diplome universitaire",
        "licence bac + 4": "Diplome universitaire",
        "bac + 3": "Diplome universitaire",
        "bac+3": "Diplome universitaire",
        "master 1": "Master",
        "master 1, licence  bac + 4": "Diplome universitaire",
        "master 2, ingéniorat, bac + 5": "Diplome universitaire",
        "baster 2": "Master",
        "ingéniorat": "Diplome universitaire",
        "bac + 5": "Diplome universitaire",
        "magistère bac + 7": "Diplome universitaire",
        "doctorat": "Doctorat",
        "certification": "Diplôme professionnel / téchnique",
        "formation professionnelle": "Diplôme professionnel / téchnique",
        "universitaire sans diplôme": "Diplôme professionnel / téchnique",
        "non diplômante": None,
        "sans diplôme": None,
        "sans diplome": None,
    }
    return mapping.get(diplome.lower() if diplome else "", diplome)

def normalize_date(date_text):
    """
    Convert date text to an actual date in ISO format.
    Handles both relative dates like "il y a 3 jours" and actual dates like "28-04-2025 à 18:37:44"
    """
    if not date_text:
        return ""
    
    # Normalize the text (lowercase, replace multiple spaces)
    date_text = re.sub(r'\s+', ' ', date_text.lower().strip())
    
    # Check if it's a standard date format (DD-MM-YYYY)
    std_date_match = re.search(r'(\d{2}-\d{2}-\d{4})', date_text)
    if std_date_match:
        # Extract just the date part
        date_str = std_date_match.group(1)
        try:
            # Parse the date
            date_parts = date_str.split('-')
            if len(date_parts) == 3:
                day, month, year = date_parts
                target_date = datetime(int(year), int(month), int(day))
                return target_date.strftime('%Y-%m-%d')
        except Exception:
            pass

    # Match patterns like "il y a X jours/semaines/mois/années"
    day_match = re.search(r'il y a (\d+) jour', date_text)
    week_match = re.search(r'il y a (\d+) semaine', date_text)
    month_match = re.search(r'il y a (\d+) mois', date_text)
    year_match = re.search(r'il y a (\d+) an', date_text)
    
    today = datetime.now()
    
    if day_match:
        days = int(day_match.group(1))
        target_date = today - timedelta(days=days)
    elif week_match:
        weeks = int(week_match.group(1))
        target_date = today - timedelta(weeks=weeks)
    elif month_match:
        months = int(month_match.group(1))
        # Approximate months as 30 days
        target_date = today - timedelta(days=months*30)
    elif year_match:
        years = int(year_match.group(1))
        # Approximate years as 365 days
        target_date = today - timedelta(days=years*365)
    elif "aujourd'hui" in date_text or "aujourd" in date_text:
        target_date = today
    elif "hier" in date_text:
        target_date = today - timedelta(days=1)
    else:
        # If we can't parse it, return the original text
        return date_text
    
    # Return in ISO format (YYYY-MM-DD)
    return target_date.strftime('%Y-%m-%d')

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

def extract_diplome_from_description(description):
    """
    Extract diploma information from the job description.
    """
    # Look for mentions of diplomas in the description
    diploma_keywords = [
        "diplôme en", "diplôme d'", "diplôme de",
        "titulaire d'un", "titulaire de", "titulaire du",
        "bac +", "bac+", "licence", "master", "doctorat",
        "formation en", "formation d'", "formation de",
        "niveau d'étude", "niveau étude"
    ]
    
    diplomes = []
    for keyword in diploma_keywords:
        if keyword.lower() in description.lower():
            # Find the sentence containing the keyword
            sentences = re.split(r'[.;\n]', description)
            for sentence in sentences:
                if keyword.lower() in sentence.lower():
                    # Add this as a potential diploma requirement
                    diplomes.append(sentence.strip())
                    break
    
    # Extract specific diploma from description if found
    diploma_pattern = r'diplôme\s+(?:en|d\'|de)\s+([^,\.;]+)'
    diploma_match = re.search(diploma_pattern, description, re.IGNORECASE)
    if diploma_match:
        diplomes.append(diploma_match.group(1).strip())
    
    return diplomes

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
        domaine = normalize_domaine(carax_details.get("catégories", ""))
        
        # 4) Get publication date
        date_depot = normalize_date(carax_details.get("publiée le", ""))
        
        # 5) Get description
        description = parse_description(soup)
        
        # 6) Extract diploma from description since it's not in a structured field
        raw_diplomes = extract_diplome_from_description(description)
        
        # Extract specific diploma mentioned in the description
        if "Diplôme en langues" in description:
            raw_diplomes.append("Diplôme en langues")
        
        # 7) Normalize diplomas
        diplome = [
            normalize_diplome(item)
            for item in raw_diplomes
            if normalize_diplome(item)
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
        return job_details
