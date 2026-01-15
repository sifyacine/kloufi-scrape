import re
import json
from datetime import datetime
from time import sleep
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from tenacity import retry, stop_after_attempt, wait_exponential
import sys
sys.path.insert(1, '../../global')
from insert_scrape import insert_data_to_es

def str_to_float(text):
    """Convert a string price to a float, handling commas and non-numeric characters."""
    try:
        num = re.sub(r"[^\d.,]", "", text)
        num = num.replace(",", ".")
        return float(num)
    except Exception:
        return 0
    
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

def save_to_json_file(data, filename=fr"voiture\autobessah\data\scraped_vehicles.json"):
    """
    Save a dictionary (data) to a JSON file. If the file already exists, append the new entry.
    """
    try:
        # Read existing data if the file exists
        try:
            with open(filename, 'r') as f:
                existing_data = json.load(f)
        except FileNotFoundError:
            existing_data = []

        # Append new data
        existing_data.append(data)

        # Write back to the file
        with open(filename, 'w') as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False)
        print(f"Data saved to {filename}.")
    except Exception as e:
        print(f"Error saving data to file: {e}")


def extract_model(title, brand):
    """Extract the model from the title based on the brand."""
    if not brand:
        return ""
    words = title.split()
    try:
        index = words.index(brand)
        if index + 1 < len(words):
            return words[index + 1]
    except ValueError:
        pass
    return ""

def normalize_energie(value: str) -> str:
        """
        Normalize fuel type/energy source.
        """
        if not value:
            return ""
            
        mapping = {
            # Essence
            "Essence": "Essence",
            "Petrol": "Essence",
            "Gasoline": "Essence",
            "Essence, Compatible E-10": "Essence",

            # Diesel
            "Diesel": "Diesel",
            "Diesel, Compatible E-10": "Diesel",

            # GPL
            "GPL": "GPL",
            "GPL, Compatible E-10": "GPL",
            "Essence / GPL": "GPL",

            # Electrique
            "Electrique": "Electrique",

            # Hybride
            "Hybride": "Hybride",
            "Hybrid": "Hybride",
            "Hybrid (gasoline/electric)": "Hybride",
            "Hybride (essence/électrique)": "Hybride",
            "Hybride (diesel/électrique)": "Hybride",

            # Hybride Rechargeable
            "Hybride (essence/électrique), Hybride rechargeable": "Hybride Rechargeable",
            "Hybride (essence/électrique), Compatible E-10, Hybride rechargeable": "Hybride Rechargeable",

            # Multi-énergie
            "Essence / Hybride": "Multi-énergie",
            "Essence / Hybride / Electrique": "Multi-énergie",

            # Unknown entries mapped as requested
            "energie-1": "Essence",
            "energie-2": "Diesel",
            "energie-3": "GPL",
        }

        return mapping.get(value.strip(), "Multi-énergie")

def normalize_transmission(value: str) -> str:
        """
        Normalize transmission type.
        """
        if not value:
            return ""

        val_upper = value.strip().upper()
        
        # Checking for specific keywords
        if val_upper in ["AT", "DCT", "CVT", "E-CVT", "DHT", "AMT", "TCT", "E-CVT+AT", "ISR"]:
            return "Automatique"
            
        if "SEMI" in val_upper:
            return "Semi-Automatique"
            
        if "AUTOMATIQUE" in val_upper or "AUTOMATIC" in val_upper:
            return "Automatique"
            
        if "MANUELLE" in val_upper or "MANUAL" in val_upper or "MÉCANIQUE" in val_upper or "MT" == val_upper:
            return "Manuelle"
            
        return value.strip()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1))
async def extract_car_details(url):
    # Browser configuration for crawling
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
        title_elem = soup.find("h1", class_="product-page__heading")
        if title_elem:
            title = title_elem.get_text(strip=True)
    except Exception as e:
        print(f"Title error: {e}")

    # Price extraction (current & old)
    price = ""
    price_value = 0
    old_price = ""
    old_price_value = 0

    try:
        # Current price
        price_elem = soup.find("span", class_="product__price__price")
        if price_elem:
            price = price_elem.get_text(strip=True)
            price_value = str_to_float(price)

        # Old price ("<s>" tag)
        old_price_elem = soup.find("s", class_="product__price__old-price")
        if old_price_elem:
            old_price = old_price_elem.get_text(strip=True)
            old_price_value = str_to_float(old_price)

    except Exception as e:
        print(f"Price error: {e}")


    # Image extraction
    images = []
    try:
        image_links = soup.find_all("a", class_="image-gallery__slide-item")
        for link in image_links:
            img_url = link.get("href", "")
            if img_url:
                images.append(img_url)
    except Exception as e:
        print(f"Image error: {e}")

    # Vehicle data extraction from product properties
    vehicle_data = {}
    try:
        properties = soup.find_all("div", class_="product__property")
        for prop in properties:
            label = prop.find("label")
            if label:
                key = label.get_text(strip=True).lower()
                selected_option = prop.find("option", selected=True)
                if selected_option:
                    value = selected_option.get_text(strip=True)
                    key = re.sub(r'\W+', '_', key)
                    vehicle_data[key] = value
    except Exception as e:
        print(f"Vehicle data error: {e}")

    # Extract model from title using brand
    marque = vehicle_data.get("marque", "")
    model = extract_model(title, marque)
    # Year extraction (Année)
    annee = ""
    try:
        li_tags = soup.find_all("li")
        for li in li_tags:
            if "ann\u00e9e" in li.get_text(strip=True).lower():  # "année"
                span = li.find("span")
                if span:
                    raw_year = span.get_text(strip=True).replace("\xa0", " ").strip()
                    # raw_year = "02-2025"
                    # Extract year part
                    match = re.search(r"\b(\d{4})\b", raw_year)
                    if match:
                        annee = match.group(1)  # "2025"
                break
    except Exception as e:
        print("Year extraction error:", e)


    # Numero extraction from reference number
    numero = ""
    try:
        numero_elem = soup.find("span", class_="product-page__number")
        if numero_elem:
            numero = numero_elem.get_text(strip=True).replace("REF:", "").strip()
    except Exception as e:
        print(f"Numero error: {e}")

    # Options extraction
    options = []
    try:
        desc_section = soup.find("div", class_="product-page__description")
        if desc_section:
            for ul in desc_section.find_all("ul"):
                for li in ul.find_all("li"):
                    option = li.get_text(" ", strip=True).replace('\xa0', ' ')
                    if option and option not in options:
                        options.append(option)
    except Exception as e:
        print(f"Options error: {e}")

    # Description extraction
    description = ""
    try:
        desc_section = soup.find("div", class_="product-page__description")
        if desc_section:
            description = desc_section.get_text(" ", strip=True).replace('\xa0', ' ')
    except Exception as e:
        print(f"Description error: {e}")

    # Mapping to final structure
    vehicle_info = {
        "titre": title,
        "description": description,
        "numero": numero,
        "date_depot": datetime.now().isoformat(),
        "site_origine": "Autobessah.fr",  # Updated to match the HTML source
        "categorie": "Automobiles & Vehicules",
        "category": "voiture",
        "images": images,
        "url": url,
        "papers": "",
        "annee": annee,
        "marque": marque,
        "model": model,
        "km": "",  # Assuming new car as no mileage is specified
        "km_unit": "KM",
        "moteur": "",  # Could extract "Cc 1.5" from options if needed
        "couleur": vehicle_data.get("couleur_disponible", ""),
        "options": options,
        "energie": normalize_energie(vehicle_data.get("énergie", "")),
        "transmission": normalize_transmission(vehicle_data.get("transmission", "")),
        "prix": price,
        "prix_value": price_value,
        "prix_dec": price_value,
        "old_price": old_price,
        "prix_unit": "€",
        "export": "true",
        "etat": "Neuf",
        "date_crawl": datetime.now().isoformat(),
        "status": "200",
        "as_photo": "Avec photo" if images else "Sans photo",
        "as_prix": "Avec prix" if price_value else "Sans prix",
        "wilaya": "",
        "commune": "",
        "tax": "HT" if price else "",
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