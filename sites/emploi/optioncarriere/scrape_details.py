import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
import sys
sys.path.insert(1, '../../global')

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
    Handles both relative dates like "il y a 3 jours", "il y a 12 heures"
    and actual dates like "28-04-2025 à 18:37:44".
    """
    if not date_text:
        return ""
    
    # Normalize the text (lowercase, replace multiple spaces)
    date_text = re.sub(r'\s+', ' ', date_text.lower().strip())
    
    # 1) Standard absolute date (DD-MM-YYYY)
    std_match = re.search(r'(\d{2}-\d{2}-\d{4})', date_text)
    if std_match:
        try:
            day, month, year = std_match.group(1).split('-')
            return datetime(int(year), int(month), int(day)).strftime('%Y-%m-%d')
        except ValueError:
            pass  # fall back to relative parsing
    
    # Get "now" once
    now = datetime.now()
    
    # 2) Relative patterns
    patterns = [
        (r'il y a (\d+)\s+an',      lambda n: now - timedelta(days=n*365)),
        (r'il y a (\d+)\s+ans',     lambda n: now - timedelta(days=n*365)),
        (r'il y a (\d+)\s+mois',    lambda n: now - timedelta(days=n*30)),
        (r'il y a (\d+)\s+semaine', lambda n: now - timedelta(weeks=n)),
        (r'il y a (\d+)\s+semaines',lambda n: now - timedelta(weeks=n)),
        (r'il y a (\d+)\s+jour',     lambda n: now - timedelta(days=n)),
        (r'il y a (\d+)\s+jours',    lambda n: now - timedelta(days=n)),
        (r'il y a (\d+)\s+heure',    lambda n: now - timedelta(hours=n)),
        (r'il y a (\d+)\s+heures',   lambda n: now - timedelta(hours=n)),
        (r'il y a (\d+)\s+minute',   lambda n: now - timedelta(minutes=n)),
        (r'il y a (\d+)\s+minutes',  lambda n: now - timedelta(minutes=n)),
    ]
    
    for pattern, delta_fn in patterns:
        m = re.search(pattern, date_text)
        if m:
            return delta_fn(int(m.group(1))).strftime('%Y-%m-%d')
    
    # 3) Special words
    if "aujourd'hui" in date_text or "aujourd" in date_text:
        return now.strftime('%Y-%m-%d')
    if "hier" in date_text:
        return (now - timedelta(days=1)).strftime('%Y-%m-%d')
    
    # If nothing matches, return original
    return date_text

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
    diploma_pattern = r'[Tt]itulaire\s+d\'un\s+([^,\.;]+)'
    diploma_match = re.search(diploma_pattern, description, re.IGNORECASE)
    if diploma_match:
        diplomes.append(diploma_match.group(1).strip())
    
    diploma_pattern = r'[Bb]ac\s*\+\s*(\d+)'
    diploma_matches = re.findall(diploma_pattern, description)
    for match in diploma_matches:
        diplomes.append(f"Bac+{match}")
    
    return diplomes

async def extract_job_details(url, entry_data=None):
    """
    Extract detailed job information from the job detail page.
    If entry_data is provided, it will be used to enhance the job details.
    """
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
        
        # Initialize with data from the listing page if available
        job_details = {
            "date_crawl": normalize_date(datetime.now().isoformat()),
            "url": url,
            "site_origine": "optioncarriere.dz",
            "titre": entry_data.get("title", "") if entry_data else "",
            "niveau": [],
            "numero": url.rstrip("/").split("/")[-1],
            "date_depot": "",
            "transaction": "Offres",
            "contrat": "",
            "diplome": [],
            "diplome_src": [],
            "domaine": "",
            "description": "",
            "employeur": entry_data.get("company", "") if entry_data else "",
            "poste": "",
            "adresse": entry_data.get("location", "") if entry_data else "",
            "wilaya": entry_data.get("location", "") if entry_data else "",
            "status": 200,
            "date_verif": normalize_date(datetime.now().isoformat()),
            "images": [],
            "as_photo": "Sans photo",
            "prix": "",
            "prix_unit": "",
            "prix_dec": "",
            "as_prix": "Sans prix",
            "vehicle": "False"
        }
        
        # Extract title from h1 if not already set
        if not job_details["titre"]:
            title_tag = soup.find("h1")
            if title_tag:
                job_details["titre"] = title_tag.get_text(strip=True)
        
        # Extract company/employer from .company
        company_tag = soup.find("p", class_="company")
        if company_tag and company_tag.find("a"):
            job_details["employeur"] = company_tag.find("a").get_text(strip=True)
        
        # Extract logo/image if available
        logo_img = soup.find("img", class_="logo")
        if logo_img and "src" in logo_img.attrs:
            job_details["images"].append(logo_img["src"])
            job_details["as_photo"] = "Avec photo"
        
        # Extract location from .details
        details_ul = soup.find("ul", class_="details")
        if details_ul:
            for li in details_ul.find_all("li"):
                # Look for location icon
                if li.find("svg") and "icon-location" in li.find("svg").get("class", []):
                    location_text = li.get_text(strip=True)
                    job_details["adresse"] = location_text
                    # Try to extract wilaya from location
                    wilaya_match = re.search(r',\s*([^,]+)$', location_text)
                    if wilaya_match:
                        job_details["wilaya"] = wilaya_match.group(1).strip()
                
                # Look for contract type
                if li.find("svg") and "icon-contract2" in str(li.find("svg")):
                    job_details["contrat"] = li.get_text(strip=True)
        
        # Extract posted date from tags
        tags_ul = soup.find("ul", class_="tags")
        if tags_ul:
            date_badge = tags_ul.find("span", class_="badge")
            if date_badge:
                date_text = date_badge.get_text(strip=True)
                job_details["date_depot"] = normalize_date(date_text)
        
        # Extract job description
        content_section = soup.find("section", class_="content")
        if content_section:
            # Get all text content, preserving line breaks
            description = ""
            for elem in content_section.contents:
                if isinstance(elem, str):
                    description += elem
                elif elem.name == "span" and "br" in elem.get("class", []):
                    description += "\n"
                elif elem.name == "b":
                    description += f"\n{elem.get_text(strip=True)}: "
                elif elem.name == "ul":
                    for li in elem.find_all("li"):
                        description += f"\n- {li.get_text(strip=True)}"
                else:
                    description += elem.get_text(" ", strip=True)
            
            job_details["description"] = description.strip()
            
            # Extract diploma information from description
            raw_diplomes = extract_diplome_from_description(description)
            job_details["diplome_src"] = raw_diplomes
            job_details["diplome"] = [
                normalize_diplome(item)
                for item in raw_diplomes
                if normalize_diplome(item)
            ]
            
            # Combine title and description for broader analysis
            combined_text = f"{job_details['titre']}".lower()

            # Medecine & Santé
            if any(keyword in combined_text for keyword in ["médec", "health", "santé", "pharmac", "hospital", "infirm", "nurse", "doctor", "medical", "clinique", "urgences", "soins"]):
                job_details["domaine"] = "Medecine & Santé"

            # Recherche & Développement
            elif any(keyword in combined_text for keyword in ["r&d", "recherche", "research", "développement", "scientifique", "innovation", "laboratoire", "expérimentation", "thèse", "prototype"]):
                job_details["domaine"] = "Recherche & developpement"

            # Juridique
            elif any(keyword in combined_text for keyword in ["juridique", "legal", "droit", "avocat", "contract", "loi", "compliance", "litige", "notaire", "réglementation"]):
                job_details["domaine"] = "Juridique"

            # Comptabilité & Audit  
            elif any(keyword in combined_text for keyword in ["comptab", "audit", "financ", "account", "tax", "fiscal", "bilan", "trésorerie", "paie", "controll"]):
                job_details["domaine"] = "Comptabilité & Audit"

            # Informatique & Internet
            elif any(keyword in combined_text for keyword in ["dev", "développeur", "software", "program", "code", "it", "tech", "network", "data", "cyber", "système", "cloud", "frontend", "backend", "fullstack"]):
                job_details["domaine"] = "Informatique & Internet"

            # Construction & Travaux
            elif any(keyword in combined_text for keyword in ["construction", "bâtiment", "travaux", "architect", "genie civil", "chantier", "maçon", "terrassement", "béton", "charpente"]):
                job_details["domaine"] = "Construction & Travaux"

            # Industrie & Production
            elif any(keyword in combined_text for keyword in ["industr", "product", "manufactur", "usine", "engineer", "ingénieur", "qualité", "maintenance", "machine", "assemblage"]):
                job_details["domaine"] = "Industrie & Production"

            # Achat & Logistique
            elif any(keyword in combined_text for keyword in ["achat", "procurement", "logisti", "supply", "invent", "stock", "approvis", "fournisseur", "entrepôt", "commande", "commercial"]):
                job_details["domaine"] = "Achat & Logistique"

            # Tourisme & Gastronomie
            elif any(keyword in combined_text for keyword in ["touris", "gastrono", "hôtellerie", "restauration", "chef", "cuisine", "voyage", "bartender", "serveur", "hôtel"]):
                job_details["domaine"] = "Tourisme & Gastronomie"

            # Bureautique & Secretariat
            elif any(keyword in combined_text for keyword in ["secretar", "bureautiq", "reception", "assistan", "accueil", "agenda", "courrier", "standardiste", "dactylo"]):
                job_details["domaine"] = "Bureautique & Secretariat"

            # Commercial & Marketing
            elif any(keyword in combined_text for keyword in ["market", "brand", "digital", "seo", "publicité", "média", "communication", "campagne", "merchandising", "études de marché"]):
                job_details["domaine"] = "Commercial & Marketing"

            # Commerce & Vente
            elif any(keyword in combined_text for keyword in ["vente", "sales", "retail", "commercial", "clientèle", "business dev", "account manager", "négociation", "démarchage"]):
                job_details["domaine"] = "Commerce & Vente"

            # Services
            elif any(keyword in combined_text for keyword in ["service client", "support", "conseiller", "aide à domicile", "ménage", "sécurité", "nettoyage", "call center", "assistance", "hotline"]):
                job_details["domaine"] = "Services"

            # Administration & Management (catch-all for leadership/operations roles)
            elif any(keyword in combined_text for keyword in ["admin", "gestion", "management", "directeur", "manager", "rh", "ressources humaines", "opération", "stratégie", "coordination"]):
                job_details["domaine"] = "Administration & Management"

            else:
                job_details["domaine"] = "Autre"
            
            # Check for source
            source_p = content_section.find("p", class_="source")
            if source_p and source_p.get("data-source"):
                job_details["source"] = source_p.get("data-source")
        
        print(f"Extracted job details for: {job_details['titre']}")
        return job_details