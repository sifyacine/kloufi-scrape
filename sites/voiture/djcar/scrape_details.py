import re
import json
from datetime import datetime
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
        print(f"[Mock] Inserting data to ES index '{index}'")

def extract_engine_size(moteur_text):
    """
    Extract engine size in liters from engine/moteur text.
    Examples: "1.8L", "2.0 L", "1800cc", "2000 cm³", "1.6 TSI"
    Returns: float (engine size in liters) or 0 if not found
    """
    if not moteur_text:
        return 0
    
    # Try to find liters (L)
    liter_match = re.search(r'(\d+\.?\d*)\s*L', moteur_text, re.IGNORECASE)
    if liter_match:
        return float(liter_match.group(1))
    
    # Try to find cc or cm³
    cc_match = re.search(r'(\d+)\s*(cc|cm³|cm3)', moteur_text, re.IGNORECASE)
    if cc_match:
        cc_value = int(cc_match.group(1))
        return cc_value / 1000.0  # Convert cc to liters
    
    # Try to find just numbers that could be engine size (e.g., "1.6", "2.0")
    number_match = re.search(r'(\d+\.\d+)', moteur_text)
    if number_match:
        potential_size = float(number_match.group(1))
        # Assume it's engine size if between 0.5 and 8.0 liters
        if 0.5 <= potential_size <= 8.0:
            return potential_size
    
    return 0

def save_to_json_file(data, filename="scraped_vehicles.json"):
    try:
        existing_data = []
        try:
            with open(filename, 'r') as f:
                existing_data = json.load(f)
        except FileNotFoundError:
            pass

        existing_data.append(data)
        with open(filename, 'w') as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False)
        print(f"Data saved to {filename}")
    except Exception as e:
        print(f"Error saving data: {e}")

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
    
    # Title extraction - Updated selector
    title = ""
    try:
        title_elem = soup.find("h2", class_="car-title") or soup.find("meta", {"property": "og:title"})
        title = title_elem.get_text(strip=True) if title_elem else ""
    except Exception as e:
        print(f"Title error: {e}")
    
    # Check if title is empty, then trigger a retry
    if not title:
        print(f"Title is empty for URL: {url}. Retrying extraction...")
        raise Exception("Empty title encountered")
    
    # Price extraction - Updated to more specific selector
    price_raw = ""
    price_value = 0
    try:
        price_elem = soup.find("div", class_="price car-price text-right")
        if price_elem:
            bdi_elem = price_elem.find("bdi", class_="new-price")
            if bdi_elem:
                price_raw = bdi_elem.get_text(strip=True)
    except Exception as e:
        print(f"Price error: {e}")
        
    _, price_value_str, price_decimal, _ = VoitureUtils.parse_price(price_raw)


    # For Djcar.fr (second scraper)
    def extract_images_djcar(soup):
        """
        Extract unique full-resolution image URLs from Djcar's Slick carousel.
        Converts thumbnail URLs (190x138) to full-size images.
        Avoids duplicates from cloned slides.
        """
        images = []
        seen_urls = set()
        
        try:
            # Find all img tags in the carousel (excluding cloned ones)
            img_tags = soup.find_all("img", class_="vehicle-detail-gallery-nav-img")
            
            for img in img_tags:
                # Skip cloned slides (they have slick-cloned class)
                if 'slick-cloned' in img.get('class', []):
                    continue
                
                # Get the src attribute
                img_url = img.get("src")
                
                if img_url:
                    # Convert thumbnail URL to full-size
                    # Remove the size suffix (e.g., -190x138) before the file extension
                    full_size_url = re.sub(r'-\d+x\d+(\.[a-z]+)$', r'\1', img_url)                    
                    # Add to list if not a duplicate
                    if full_size_url not in seen_urls:
                        seen_urls.add(full_size_url)
                        images.append(full_size_url)
            
            print(f"Extracted {len(images)} unique images from Djcar")
            
        except Exception as e:
            print(f"Image extraction error: {e}")
        
        return images
    

    images = extract_images_djcar(soup)
    # Vehicle data extraction - Updated selectors
    vehicle_data = {}
    try:
        data_list = soup.find("ul", class_="car-attributes")
        if data_list:
            for item in data_list.find_all("li"):
                label_elem = item.find("span")
                value_elem = item.find("strong", class_="text-right")
                label = label_elem.get_text(strip=True).lower() if label_elem else ""
                value = value_elem.get_text(strip=True) if value_elem else ""
                if label:
                    key = re.sub(r'\W+', '_', label.replace('é', 'e').replace('è', 'e'))
                    vehicle_data[key] = value
    except Exception as e:
        print(f"Vehicle data error: {e}")

    # Extract fuel type and engine size for filtering
    raw_carburant = vehicle_data.get("carburant", "")
    energie = VoitureUtils.normalize_fuel(raw_carburant)
    
    raw_moteur = vehicle_data.get("engine", "")
    engine_size = extract_engine_size(raw_moteur)
    
    # ================================
    # FILTERING LOGIC
    # ================================
    
    # Skip if Diesel
    if energie == "Diesel":
        print(f"⛔ SKIPPED: {url} - Diesel vehicle")
        return None
    
    # Skip if Essence with engine > 1.8L
    if energie == "Essence" and engine_size > 1.8:
        print(f"⛔ SKIPPED: {url} - Essence vehicle with engine {engine_size}L (> 1.8L)")
        return None
    
    # ================================
    # Continue processing if not filtered
    # ================================

    # Description extraction
    description = ""
    try:
        desc_section = soup.find("div", class_="elementor-widget-text-editor") or soup.find("div", class_="vehicle-description")
        if desc_section:
            description = ' '.join(desc_section.stripped_strings)
    except Exception as e:
        print(f"Description error: {e}")

    if not description:
        description = title  # Use title as description if no separate description found

    # Options extraction
    options = []
    try:
        options_container = soup.find("div", class_="stm-single-listing-car-features")
        if options_container:
            options = [opt.get_text(strip=True) for opt in options_container.find_all("div", class_="stm-option")]
    except Exception as e:
        print(f"Options error: {e}")

    # Split kilometerage into value and unit
    km_raw = vehicle_data.get("kilometrage", "")
    km_val, km_unit = VoitureUtils.normalize_mileage(km_raw)

    # Construct final data with all fields - Updated keys
    vehicle_info = {
        "titre": title,
        "description": description,
        "numero": url.rstrip("/").split("/")[-1],
        "date_depot": datetime.now().isoformat(),
        "site_origine": "Djcar.fr",
        "categorie": "Automobiles & Vehicules",
        "category": "voiture",
        "images": images,
        "url": url,
        "annee": vehicle_data.get("annee", ""),
        "marque": vehicle_data.get("marque", title.split()[0] if title else ""),
        "model": vehicle_data.get("modele", vehicle_data.get("model", "")),
        "km": km_val,
        "km_unit": km_unit, 
        "moteur": raw_moteur,
        "couleur": vehicle_data.get("exterior_color", vehicle_data.get("couleur", "")),
        "options": options,
        "energie": energie,
        "transmission": VoitureUtils.normalize_transmission(vehicle_data.get("transmission", "")),
        "prix": price_raw,
        "prix_value": price_value_str,
        "prix_dec": price_decimal,
        "prix_unit": "€",
        "etat": vehicle_data.get("etat", "Occasion"),
        "date_crawl": datetime.now().isoformat(),
        "status": "200",
        "as_photo": "Avec photo" if images else "Sans photo",
        "as_prix": "Avec prix" if price_decimal > 0 else "Sans prix",
        "wilaya": "",
        "commune": "",
        "tax": "HT",
        "engine_size_liters": engine_size,  # Added for reference
    }

    # Ensure all fields are set properly
    for key in vehicle_info:
        if vehicle_info[key] is None:
            vehicle_info[key] = ""
        elif isinstance(vehicle_info[key], list) and not vehicle_info[key]:
            vehicle_info[key] = []
    
    print(f"✅ ACCEPTED: {vehicle_info['numero']} - {energie} {engine_size}L - {km_val} {km_unit}")
    insert_data_to_es(vehicle_info, "voiture")
    # save_to_json_file(vehicle_info)
    return vehicle_info