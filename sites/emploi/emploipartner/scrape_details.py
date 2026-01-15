import re
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import sys
import json

try:
    sys.path.insert(1, '../../global')
    from insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] Inserted into '{index}' -> {data['titre']}")

# ====================== NORMALIZATION FUNCTIONS ======================

def parse_relative_date(date_str):
    """Convert 'il y a environ 2 heures' → '2025-12-17'"""
    date_str = date_str.strip().lower()
    if "il y a" not in date_str:
        return "N/A"
    
    # Remove 'environ' word
    date_str = re.sub(r'environ\s*', '', date_str)
    
    # Match plural and singular forms
    match = re.match(r'il y a (\d+)\s*(heures?|jours?|semaines?|mois|ans?)', date_str)
    if not match:
        return "N/A"
    
    num = int(match.group(1))
    unit = match.group(2).rstrip('s')  # Remove trailing 's' to get singular form
    
    now = datetime.now()
    deltas = {
        "heure": timedelta(hours=num),
        "jour": timedelta(days=num),
        "semaine": timedelta(weeks=num),
        "mois": timedelta(days=num * 30),
        "an": timedelta(days=num * 365),
    }
    
    past_date = now - deltas.get(unit, timedelta(days=0))
    return past_date.strftime('%Y-%m-%d')


def normalize_diplome(diplome_raw):
    """Comprehensive normalization for Algerian diplomas on emploipartner"""
    if not diplome_raw:
        return None

    diplome = diplome_raw.strip().lower()
    diplome = re.sub(r'\s+', ' ', diplome)
    diplome = diplome.replace("é", "e").replace("è", "e")

    mapping = {
        # Bac and below
        "bac": "Bac",
        "baccalaureat": "Bac",
        "bac +0": "Bac",
        "niveau bac": "Bac",

        # Bac +2 / Technical
        "bac +2": "Diplome universitaire",
        "bac+2": "Diplome universitaire",
        "ts": "Diplome professionnel / technique",
        "technicien superieur": "Diplome professionnel / technique",
        "bts": "Diplome professionnel / technique",
        "dut": "Diplome universitaire",

        # Bac +3 / Licence
        "bac +3": "Diplome universitaire",
        "bac+3": "Diplome universitaire",
        "licence": "Diplome universitaire",

        # Master / Engineer
        "bac +5": "Master",
        "bac+5": "Master",
        "master": "Master",
        "ingenieur": "Master",
        "ingeniorat": "Master",

        # No diploma
        "indifferent": None,
        "sans diplome": None,
        "sans diplôme": None,
        "niveau indifferent": None,

        # Professional training
        "formation professionnelle": "Diplome professionnel / technique",
        "certificat": "Diplome professionnel / technique",
    }

    return mapping.get(diplome, diplome_raw)


def normalize_niveau_experience(exp_raw):
    """Normalize experience level from text or tags"""
    if not exp_raw:
        return "Non specifie"

    exp = exp_raw.strip().lower()
    mapping = {
        "debutant": "Debutant",
        "sans experience": "Debutant",
        "jeune diplome": "Debutant",

        "1 a 2 ans": "Junior",
        "1 a 3 ans": "Junior",
        "junior": "Junior",

        "3 a 5 ans": "Experimente",
        "confirme": "Experimente",
        "experimente": "Experimente",

        "plus de 5 ans": "Senior",
        "senior": "Senior",
        "manager": "Senior",
        "chef": "Senior",
    }
    return mapping.get(exp, exp_raw)


def normalize_contrat(contrat_raw):
    """Normalize contract type"""
    if not contrat_raw:
        return "Non specifie"

    contrat = contrat_raw.strip().lower()
    mapping = {
        "sur site": "CDI",
        "temps plein": "CDI",
        "cdi": "CDI",

        "teletravail": "Teletravail",
        "remote": "Teletravail",

        "cdd": "CDD",
        "mission": "CDD",

        "stage": "Stage",
        "alternance": "Alternance",
        "intérim": "Interim",
    }
    return mapping.get(contrat, contrat_raw)


def extract_wilaya_from_city(city):
    """Map common Algerian cities to wilayas"""
    if not city:
        return "N/A"

    city_lower = city.strip().lower()
    mapping = {
        "alger": "Alger", "algiers": "Alger",
        "oran": "Oran",
        "constantine": "Constantine",
        "annaba": "Annaba",
        "blida": "Blida",
        "batna": "Batna",
        "setif": "Setif", "sétif": "Setif",
        "sidi bel abbes": "Sidi Bel Abbes",
        "biskra": "Biskra",
        "tlemcen": "Tlemcen",
        "mostaganem": "Mostaganem",
        "bejaia": "Bejaia", "béjaïa": "Bejaia",
        "tizi ouzou": "Tizi Ouzou",
        "ouargla": "Ouargla",
        "hassi messaoud": "Ouargla",
        "ghardaia": "Ghardaia",
    }
    return mapping.get(city_lower, city.title())


def extract_salary_from_text(text):
    """Look for salary in description (rare on emploipartner, but possible)"""
    if not text:
        return "", "", "Sans prix"

    patterns = [
        r'(\d[\d\s]*\d?)\s*[-–]\s*(\d[\d\s]*\d?)\s*(da|dzd)',
        r'(?:salaire|remuneration).{0,20}(\d[\d\s]*\d?)\s*(da|dzd)',
        r'(\d[\d\s]*\d?)\s*(da|dzd|dinars?)',
    ]

    text_lower = text.lower()
    for pattern in patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            amount1 = re.sub(r'\s', '', match.group(1))
            amount2 = re.sub(r'\s', '', match.group(2)) if match.lastindex >= 2 and match.group(2) else None
            if amount2:
                return f"{amount1}-{amount2}", "DA", "Avec prix"
            return amount1, "DA", "Avec prix"
    return "", "", "Sans prix"


def extract_company_logo(soup):
    """Extract company logo from avatar container"""
    images = []
    as_photo = "Sans photo"
    
    # Look for logo in avatar container
    avatar_container = soup.find("div", class_=re.compile(r"avatar-container"))
    if avatar_container:
        logo_img = avatar_container.find("img", class_=re.compile(r"avatar-image"))
        if logo_img and logo_img.get("src"):
            src = logo_img["src"]
            if src.startswith("http"):
                images = [src]
            elif src != "/images/company-placeholder.png":  # Skip placeholder
                images = ["https://api-v4.emploipartner.com" + src]
            if images:
                as_photo = "Avec photo"
    
    return images, as_photo


def extract_date_depot(soup):
    """Extract date depot from relative time format"""
    date_depot = "N/A"
    
    # Find div with relative date format
    date_divs = soup.find_all("div", class_=re.compile(r"text-gray-600"))
    for div in date_divs:
        text = div.get_text(strip=True)
        if "il y a" in text.lower():
            date_depot = parse_relative_date(text)
            break
    
    return date_depot


def extract_requirements_from_tags(soup):
    """Extract diploma, experience, contract, and job count from tag containers"""
    contrat_raw = ""
    diplome_raw_list = []
    experience_raw = ""
    nombre_postes = "1 poste"
    
    # Find all tag containers with bg-gray-100 and rounded-full
    tag_containers = soup.find_all("div", class_=re.compile(r"bg-gray-100.*rounded-full"))
    
    for tag in tag_containers:
        p_tag = tag.find("p")
        if not p_tag:
            continue
        
        value = p_tag.get_text(strip=True)
        value_lower = value.lower()
        
        # Detect contract type
        if "site" in value_lower or "teletravail" in value_lower or "remote" in value_lower:
            contrat_raw = value
        
        # Detect diploma (Bac, Bac +2, Bac +3, etc.)
        elif "bac" in value_lower or "+" in value_lower:
            diplome_raw_list.append(value)
        
        # Detect experience (with "an" or "ans")
        elif ("an" in value_lower or "ans" in value_lower) and "exp" in value_lower:
            experience_raw = value
        
        # Detect number of positions
        elif "poste" in value_lower:
            nombre_postes = value
    
    return contrat_raw, diplome_raw_list, experience_raw, nombre_postes


# ====================== MAIN SCRAPING FUNCTION ======================

async def scrape_single_url_with_crawl4ai_and_bs4(url):
    print(f"\nScraping emploipartner detail: {url}")

    browser_config = BrowserConfig(headless=True, browser_type="chromium")
    js_commands = [
        "await new Promise(r => setTimeout(r, 5000));",
        "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",
        "await new Promise(r => setTimeout(r, 3000));",
        "window.scrollTo(0, document.body.scrollHeight / 2);",
        "await new Promise(r => setTimeout(r, 2000));"
    ]

    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        js_code=js_commands,
        delay_before_return_html=15
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=config)
        if not result.success:
            print(f"Failed to load {url}: {result.error_message}")
            return

        soup = BeautifulSoup(result.html, "html.parser")

        # === Title ===
        titre_tag = soup.find("p", class_=re.compile(r"text-3xl font-xing-bold"))
        titre = titre_tag.get_text(strip=True) if titre_tag else poste or "N/A"


        def extract_employer(soup):
            """Extract employer name from HTML"""
            employer_tag = soup.find("p", class_="text-xl")
            return employer_tag.get_text(strip=True) if employer_tag else "N/A"


        def extract_position(soup):
            """Extract number of positions from HTML"""
            position_tag = soup.find("p", class_=re.compile(r"first-letter:uppercase text-black text-md"))
            return position_tag.get_text(strip=True) if position_tag else "N/A"


        # === Company Logo ===
        images, as_photo = extract_company_logo(soup)

        # === Date Depot (relative date conversion) ===
        date_depot = extract_date_depot(soup)

        # === Location (Wilaya) ===
        location_tag = soup.find("p", class_=re.compile(r"text-black text-lg"))
        wilaya_raw = location_tag.get_text(strip=True) if location_tag else "N/A"

        # Split by comma and clean up
        parts = [part.strip() for part in wilaya_raw.split(",", 1)]

        # Assign to wilaya and commune
        if len(parts) == 2:
            wilaya, commune = parts  # wilaya before comma, commune after comma
        else:
            wilaya = parts[0]  # Only wilaya is present
            commune = parts[0]  # Same as wilaya, or use "" if commune should be empty
        adresse = wilaya_raw

        # === Tags (contrat, diplome, experience, nb postes) ===
        contrat_raw, diplome_raw_list, experience_raw, nombre_postes = extract_requirements_from_tags(soup)

        # Normalize
        contrat = normalize_contrat(contrat_raw)
        niveau = [normalize_niveau_experience(experience_raw)] if experience_raw else ["Non specifie"]
        diplome_normalized = [normalize_diplome(d) for d in diplome_raw_list if normalize_diplome(d) is not None]

        # === Description (Missions + Profil + Autres) ===
        description_parts = []
        content_sections = soup.find_all("div", class_=re.compile(r"content flex flex-col gap-4"))
        for sec in content_sections:
            text = sec.get_text(separator="\n", strip=True)
            if text:
                description_parts.append(text)

        description = "\n\n".join(description_parts) if description_parts else "N/A"

        # === Salary (from description) ===
        salaire, unite, as_prix = extract_salary_from_text(description)
        prix_dec = 0
        if salaire and '-' not in salaire:
            try:
                prix_dec = float(salaire.replace(" ", ""))
            except:
                pass

        # === Numero (job ID from URL) ===
        numero = url.split("/")[-1] if "/" in url else "N/A"
        # === Employer ===
        employeur = extract_employer(soup)

        # === Position ===
        poste = extract_position(soup)


        # === Final Job Object ===
        job = {
            "date_crawl": datetime.now().isoformat(),
            "url": url,
            "site_origine": "Emploipartner.com",
            "titre": titre,
            "niveau": niveau,
            "numero": numero,
            "date_depot": date_depot,
            "date_expiration": "",
            "transaction": "Offres",
            "contrat": contrat,
            "diplome": diplome_normalized or ["Non specifie"],
            "diplome_src": diplome_raw_list,
            "domaine": "",
            "description": description,
            "employeur": employeur or "Anonyme",
            "poste": poste or titre,
            "adresse": adresse,
            "wilaya": wilaya,
            "commune": commune,
            "nombre_postes": nombre_postes,
            "status": 200,
            "date_verif": datetime.now().isoformat(),
            "images": images,
            "as_photo": as_photo,
            "prix": salaire,
            "prix_unit": unite,
            "prix_dec": prix_dec,
            "as_prix": as_prix,
            "vehicle": "Véhiculée" if "vehiculee" in description.lower() else ""
        }

        print(json.dumps(job, indent=2, ensure_ascii=False))
        insert_data_to_es(job, "emploi")