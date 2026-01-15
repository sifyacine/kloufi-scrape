import re
import asyncio
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
import sys
try:
    sys.path.insert(1, '../../../global')
    from insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index_name):
        print(f"[Mock] Would insert into index '{index_name}': {data.get('titre', 'No title')}")


def str_to_float(text):
    try:
        num = re.sub(r"[^\d.,]", "", text)
        num = num.replace(",", ".")
        return float(num)
    except Exception:
        return ""

def convert_property_type(raw_key):
    valid_types = {
        "Appartement", "Villa", "Local", "Terrain", "Studio", "Hangar",
        "Niveau de villa", "Immeuble", "Duplex", "Carcasse", "Autre",
        "Bungalow", "Terrain agricole", "Usine", "Chalet", "Commerce",
        "Locaux", "Bureau", "Autres", "Salle", "Hostel", "Dortoir",
        "Ferme", "Hotel", "Triplex", "Maison", "Pavillon", "Auberge", "Résidence"
    }

    normalization_map = {
        "bungalow": "Bungalow",
        "bungalows": "Bungalow",
        "niveau": "Niveau de villa",
        "niveau de villa": "Niveau de villa",
        "terrain-agricole": "Terrain agricole",
        "terrain agricole": "Terrain agricole",
        "appartements": "Appartement",
        "immeubles": "Immeuble",
        "commerce, local": "Commerce",
        "bureaux": "Bureau",
        "ferme, terrain": "Ferme",
        "residence": "Résidence",
        "résidence": "Résidence"
    }

    if not raw_key or not isinstance(raw_key, str):
        return ""

    cleaned = raw_key.strip().lower()

    normalized = normalization_map.get(cleaned, cleaned).capitalize()
    if normalized in valid_types:
        return normalized

    lowered = raw_key.lower()
    for key, value in normalization_map.items():
        if key in lowered:
            normalized_candidate = value
            if normalized_candidate in valid_types:
                return normalized_candidate

    for valid in valid_types:
        if valid.lower() in lowered:
            return valid

    return ""

def parse_address(address_details):
    adresse = ""
    commune = ""
    wilaya = ""
    for detail in address_details:
        strong = detail.find("strong")
        if strong:
            label = strong.get_text(strip=True).lower()
            value = detail.get_text(strip=True).replace(strong.get_text(strip=True), "").strip().lstrip(":")
            if "adresse" in label:
                adresse = value
            elif "ville" in label or "daïra" in label:
                if adresse:
                    adresse += f", {value}"
                else:
                    adresse = value
            elif "zones" in label or "commune" in label:
                commune = value.replace("Commune de ", "").strip()
            elif "région" in label:
                wilaya = value
    full_adresse = f"{adresse}, {commune}, {wilaya}".strip(", ").strip()
    return full_adresse, commune, wilaya

async def extract_property_details(url):
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        text_mode=False,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=url,
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                delay_before_return_html=5  # Reduced for speed; increase if page not fully loaded
            )
        )
    
    if not result.success:
        raise Exception(f"Failed to load detail page: {result.error_message}")
    
    soup = BeautifulSoup(result.html, "html.parser")
    
    # Initialize fields
    titre = ""
    date_depot = datetime.now().strftime("%Y-%m-%d")  # Fallback to today if not found
    transaction = "vente"
    superficie_text = ""
    no_pieces = ""
    etage = ""
    description_content = ""
    price_text = ""
    images_list = []
    adresse = ""
    commune = ""
    wilaya = ""
    numero = ""
    
    # --- Title ---
    title_h1 = soup.find("h1", class_="entry-title")
    if title_h1:
        titre = title_h1.get_text(strip=True)
    
    # --- Images ---
    carousel_indicators = soup.find("ol", class_="carousel-indicators-classic")
    if carousel_indicators:
        img_tags = carousel_indicators.find_all("img")
        seen = set()
        for img in img_tags:
            src = img.get("src")
            if src and src.startswith("data:image/svg"):  # Lazy-loaded placeholder
                src = img.get("data-lazy-src")
            # If no src or still placeholder, try data-lazy-src anyway
            if not src or src.startswith("data:image/svg"):
                src = img.get("data-lazy-src")
            
            if src and src.startswith("https://www.residencedz.com") and src not in seen:
                # Optional: upgrade to higher resolution by replacing thumbnail size
                src = src.replace("-143x83.", ".")
                # Also handle cases without size suffix (already full)
                images_list.append(src)
                seen.add(src)
        
    # --- Overview (pieces, chambres, bains, surface) ---
    overview_section = soup.find("div", class_="property-page-overview-details-wrapper")
    if overview_section:
        uls = overview_section.find_all("ul", class_="overview_element")
        for ul in uls:
            lis = ul.find_all("li")
            if len(lis) >= 2:
                value = lis[1].get_text(strip=True)
                if "m²" in value or "m<sup>2</sup>" in value:
                    superficie_text = re.sub(r"[^\d.,]", "", value)
                elif "Pièces" in value or "Pièce" in value:
                    no_pieces = re.sub(r"[^\d]", "", value)
    
    # --- Details panel ---
    details_panel = soup.find("div", id="accordion_property_details_collapse")
    if details_panel:
        listing_details = details_panel.find_all("div", class_="listing_detail")
        for detail in listing_details:
            strong = detail.find("strong")
            if strong:
                label = strong.get_text(strip=True).lower()
                value = detail.get_text(separator=" ", strip=True).replace(strong.get_text(strip=True), "").strip().lstrip(":")
                if "prix" in label:
                    price_text = value.split(" ")[0].replace(",", "")
                elif "surface" in label:
                    superficie_text = re.sub(r"[^\d.,]", "", value)
                elif "pièces" in label:
                    no_pieces = value
                elif "id" in label and ("programme" in label or "propriété" in label):
                    numero = value
                elif "étage" in label:
                    etage = value
    
    # --- Description ---
    description_section = soup.find("div", id="wpestate_property_description_section")
    if description_section:
        desc_span = description_section.find("span", id="desc")
        if desc_span:
            description_content = desc_span.get_text(strip=True)
        else:
            paragraphs = description_section.find_all("p")
            description_content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
    
    # --- Address ---
    address_panel = soup.find("div", id="accordion_property_address_collapse")
    if address_panel:
        address_details = address_panel.find_all("div", class_="listing_detail")
        adresse, commune, wilaya = parse_address(address_details)
    
    # --- Fallback numero from URL ---
    if not numero:
        numero = url.rstrip("/").split("/")[-1]
    
    superficie_val = str_to_float(superficie_text)
    prix_dec = str_to_float(price_text) if price_text else 0
    
    now_iso = datetime.now().isoformat()
    
    property_details = {
        "titre": titre,
        "url": url,
        "site_origine": "Residencedz.com",
        "date_crawl": now_iso,
        "numero": numero,
        "date_depot": date_depot,
        "transaction": transaction,
        "category": "immobilier",
        "bien": convert_property_type(titre) if titre else "",
        "superficie": superficie_val,
        "superficie_unit": "m²",
        "no_pieces": no_pieces,
        "description": description_content,
        "prix": price_text + " DA" if price_text else "",
        "prix_dec": prix_dec,
        "prix_unit": "DA" if price_text else "",
        "images": images_list,
        "adresse": adresse,
        "wilaya": wilaya,
        "commune": commune,
        "etage": etage,
        "status": 200,
        "date_verif": now_iso,
        "as_photo": "Avec photo" if images_list else "Sans photo",
        "as_prix": "Avec prix" if price_text else "Sans prix"
    }
     # Send to Elasticsearch immediately
    try:
        insert_data_to_es(property_details, index_name="immobilier")
        print(f"[ES] Inserted: {property_details['titre'][:50]}...")
    except Exception as e:
        print(f"[ES] Failed to insert: {e}")
    
    print(f"Successfully extracted: {titre[:60]}...")
    return property_details