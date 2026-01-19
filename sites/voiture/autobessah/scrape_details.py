import re
import json
from datetime import datetime
from time import sleep
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from tenacity import retry, stop_after_attempt, wait_exponential
import sys, os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from utils.voiture import VoitureUtils

try:
    sys.path.insert(1, '../../global')
    from insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] there is a problem in saving data'{index}'")

def save_to_json_file(data, filename=fr"voiture\autobessah\data\scraped_vehicles.json"):
    """
    Save a dictionary (data) to a JSON file. If the file already exists, append the new entry.
    """
    try:
        try:
            with open(filename, 'r') as f:
                existing_data = json.load(f)
        except FileNotFoundError:
            existing_data = []

        existing_data.append(data)
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
        index = [w.lower() for w in words].index(brand.lower())
        if index + 1 < len(words):
            return words[index + 1]
    except ValueError:
        pass
    return ""

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
    title = VoitureUtils.extract_text(soup, "h1.product-page__heading")

    # Price extraction (current & old)
    price_raw = VoitureUtils.extract_text(soup, "span.product__price__price")
    old_price_raw = VoitureUtils.extract_text(soup, "s.product__price__old-price")
    
    _, price_value_str, price_decimal, _ = VoitureUtils.parse_price(price_raw)
    
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
                    match = re.search(r"\b(\d{4})\b", raw_year)
                    if match:
                        annee = match.group(1)
                break
    except Exception as e:
        print("Year extraction error:", e)

    # Numero extraction
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
        "site_origine": "Autobessah.fr",
        "categorie": "Automobiles & Vehicules",
        "category": "voiture",
        "images": images,
        "url": url,
        "papers": "",
        "annee": annee,
        "marque": marque,
        "model": model,
        "km": "",
        "km_unit": "KM",
        "moteur": "",
        "couleur": vehicle_data.get("couleur_disponible", ""),
        "options": options,
        "energie": VoitureUtils.normalize_fuel(vehicle_data.get("énergie", "")),
        "transmission": VoitureUtils.normalize_transmission(vehicle_data.get("transmission", "")),
        "prix": price_raw,
        "prix_value": price_value_str,
        "prix_dec": price_decimal,
        "old_price": old_price_raw,
        "prix_unit": "€",
        "export": "true",
        "etat": "Neuf",
        "date_crawl": datetime.now().isoformat(),
        "status": "200",
        "as_photo": "Avec photo" if images else "Sans photo",
        "as_prix": "Avec prix" if price_value_str else "Sans prix",
        "wilaya": "",
        "commune": "",
        "tax": "HT" if price_raw else "",
    }

    # Ensure all fields are strings or empty lists
    for key in vehicle_info:
        if vehicle_info[key] is None:
            vehicle_info[key] = ""
        elif isinstance(vehicle_info[key], list) and not vehicle_info[key]:
            vehicle_info[key] = []

    print(f"Extracted data for {vehicle_info['numero']}")
    insert_data_to_es(vehicle_info, index_name="voiture")
    return vehicle_info