import re
import json
from datetime import datetime
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from tenacity import retry, stop_after_attempt, wait_exponential
import sys
sys.path.insert(1, '../../../global')
from insert_scrape import insert_data_to_es

def str_to_float(text):
    try:
        num = re.sub(r"[^\d.,]", "", text)
        num = num.replace(",", ".")
        return float(num)
    except Exception:
        return 0

def convert_transmission(text):
    try:
        if not text:
            return ""
        text_lower = text.lower()

        if "semi automatique" in text_lower:
            return "Semi-Automatique"
        elif "automatique" in text_lower or "automatic" in text_lower:
            return "Automatique"
        elif "manuelle" in text_lower or "manuel" in text_lower or "manual gearbox" in text_lower:
            return "Manuelle"
        elif "bvm" in text_lower:
            return "Manuelle"
        else:
            return text
    except Exception:
        return ""

def convert_essence(text):
    try:
        if not text:
            return ""
        text_lower = text.lower()

        if "essence hybrid électrique" in text_lower:
            return "Essence / Hybride / Electrique"
        elif "essence hybride" in text_lower or "essence hybrid" in text_lower:
            return "Essence / Hybride"
        elif "essence gpl" in text_lower:
            return "Essence / GPL"
        elif "hybrid" in text_lower or "hybride" in text_lower:
            return "Hybride"
        elif "electrique" in text_lower or "electric" in text_lower:
            return "Electrique"
        elif "diesel" in text_lower:
            return "Diesel"
        elif "essence" in text_lower or "gasoline" in text_lower:
            return "Essence"
        else:
            return text
    except Exception:
        return ""

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1))

async def extract_car_details(url):
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        text_mode=False,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=url,
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                delay_before_return_html=15
            )
        )
    
    if not result.success:
        raise Exception(f"Failed to load page: {result.error_message}")

    soup = BeautifulSoup(result.html, "html.parser")
    
    # Title extraction
    title = ""
    try:
        title_elem = soup.find("h1", class_="headline-1")
        if title_elem:
            title = title_elem.get_text(strip=True)
    except Exception as e:
        print(f"Title error: {e}")


    # Price extraction
    price = ""
    price_value = 0
    try:
        price_elem = soup.find(lambda tag: tag.name == "span" and "à partir de" in tag.text)
        if price_elem:
            strong_tag = price_elem.find("strong")
            if strong_tag:
                price = strong_tag.get_text(strip=True)
                # Extract only digits (and optionally dot/comma for decimal support)
                numeric_part = re.findall(r"\d+", price)
                if numeric_part:
                    price_value = int("".join(numeric_part))
    except Exception as e:
        print(f"Price error: {e}")


    # Image extraction
    images = []
    try:
        gallery_links = soup.find_all("a", class_="gallery")
        for link in gallery_links:
            img_url = link.get("href", "")
            if img_url and "public/img/big/" in img_url:
                images.append("https://www.easyexport.fr/" + img_url)
    except Exception as e:
        print(f"Image error: {e}")

    # Vehicle data extraction from technical tables
    vehicle_data = {}
    try:
        fiche_tables = soup.find_all("div", class_="fiche_technique")
        for table in fiche_tables:
            for row in table.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) == 2:
                    key = cols[0].get_text(strip=True).lower()
                    value = cols[1].get_text(strip=True)
                    # Normalize keys
                    key = re.sub(r'\W+', '_', key)
                    vehicle_data[key] = value
    except Exception as e:
        print(f"Vehicle data error: {e}")
    

    # Année (year) extraction
    annee = ""
    try:
        # Find all selection spans in the panneau div
        panneau_div = soup.find("div", class_="panneau")
        if panneau_div:
            for span in panneau_div.find_all("span", class_="selection"):
                text = span.get_text(strip=True)
                if "IMMATRICULATION" in text:
                    # Extract year using regex to find 4-digit number
                    match = re.search(r'\b\d{4}\b', text)
                    if match:
                        annee = match.group()
                    break  # Stop after finding the first matching span
    except Exception as e:
        print(f"Année extraction error: {e}")

    # Options extraction
    options = []
    try:
        options_section = soup.find("div", class_="txt_contenu")
        if options_section:
            # Extract all list items from both columns
            options = [li.get_text(" ", strip=True).replace('\xa0', ' ') 
                    for ul in options_section.find_all("ul") 
                    for li in ul.find_all("li")]
            # Remove duplicates while preserving order
            seen = set()
            options = [x for x in options if not (x in seen or seen.add(x))]
    except Exception as e:
        print(f"Options error: {e}")

    # Description extraction
    description = ""
    try:
        desc_paragraphs = []
        description_section = soup.find("div", class_="txt_contenu")
        if description_section:
            # Get all paragraphs after the options tables
            for p in description_section.find_all("p"):
                text = p.get_text(" ", strip=True).replace('\xa0', ' ')
                if text and not text.isspace():
                    desc_paragraphs.append(text)
            description = " ".join(desc_paragraphs)
    except Exception as e:
        print(f"Description error: {e}")

    # Mapping to final structure with empty strings for missing values
    vehicle_info = {
        "titre": title,
        "description": description,
        "numero": vehicle_data.get("modèle", "").replace(" ", "_") + "_" + str(price_value),
        "date_depot": datetime.now().isoformat(),
        "site_origine": "Easyexport.fr",
        "categorie": "Automobiles & Vehicules",
        "category": "voiture",
        "images": images,
        "url": url,
        "annee": annee,
        "marque": vehicle_data.get("marque", ""),
        "model": vehicle_data.get("modèle", ""),
        "km": vehicle_data.get("kilométrage", ""),
        "km_unit": "KM",
        "moteur": vehicle_data.get("motorisation", ""),
        "couleur": vehicle_data.get("couleur", ""),
        "options": options,
        "energie": convert_essence(vehicle_data.get("motorisation", "")),
        "transmission": convert_transmission(vehicle_data.get("transmission", "")),
        "prix": price,
        "prix_value": price_value,
        "prix_dec": price_value,
        "prix_unit": "€",
        "etat": "Neuf" if "neufs" in url else "Occasion",
        "date_crawl": datetime.now().isoformat(),
        "status": "200",
        "as_photo": "Avec photo" if images else "Sans photo",
        "as_prix": "Avec prix" if price_value else "Sans prix",
        "wilaya": "",
        "commune": "",
        "tax": "HT" if price_value else "",
    }

    # Ensure all fields are strings or empty lists
    for key in vehicle_info:
        if vehicle_info[key] is None:
            vehicle_info[key] = ""
        elif isinstance(vehicle_info[key], list) and not vehicle_info[key]:
            vehicle_info[key] = []
    
    print(f"Extracted data for {vehicle_info['numero']}")
    insert_data_to_es(vehicle_info, "voiture")
    return vehicle_info