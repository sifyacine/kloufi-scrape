import re
import json
from datetime import datetime
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
import sys

try:
    sys.path.insert(1, '../../global')
    from insert_scrape import insert_data_to_es
except ImportError:

    def insert_data_to_es(data, index):
        print(f"[Mock] there is a problem in saving data'{index}'")

def str_to_float(text):
    try:
        num = re.sub(r"[^\d.,]", "", text)
        num = num.replace(",", ".")
        return float(num)
    except Exception:
        return 0

def extract_engine_size(performance_text):
    """
    Extract engine size in liters from performance text.
    Examples: "1.8L", "2.0 L", "1800cc", "2000 cm³"
    Returns: float (engine size in liters) or 0 if not found
    """
    if not performance_text:
        return 0
    
    # Try to find liters (L)
    liter_match = re.search(r'(\d+\.?\d*)\s*L', performance_text, re.IGNORECASE)
    if liter_match:
        return float(liter_match.group(1))
    
    # Try to find cc or cm³
    cc_match = re.search(r'(\d+)\s*(cc|cm³|cm3)', performance_text, re.IGNORECASE)
    if cc_match:
        cc_value = int(cc_match.group(1))
        return cc_value / 1000.0  # Convert cc to liters
    
    return 0
    
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
                delay_before_return_html=10
            )
        )
    
    if not result.success:
        raise Exception(f"Failed to load page: {result.error_message}")

    soup = BeautifulSoup(result.html, "html.parser")
    
    # Title extraction
    title = ""
    try:
        title_div = soup.find("div", class_="dxim_vehicle_title")
        if title_div:
            make = title_div.find("span", class_="make").get_text(strip=True)
            model = title_div.find("span", class_="model").get_text(strip=True)
            desc = title_div.find("span", class_="model_description").get_text(strip=True)
            title = f"{make} {model} {desc}"
    except Exception as e:
        print(f"Title error: {e}")
    
    # Price and Tax extraction
    price = ""
    price_value = 0
    tax = ""
    try:
        netto_span = soup.find("span", class_="price_netto price_small")
        brutto_span = soup.find("span", class_="price_big price_brutto")

        if netto_span:
            raw_net = netto_span.get_text(separator=" ").split("€")[0]
            digits = re.sub(r"[^\d]", "", raw_net)
            price = digits
            price_value = int(digits) if digits else 0
            tax = "HT"
        elif brutto_span:
            raw_gross = brutto_span.get_text(separator=" ").split("€")[0]
            digits = re.sub(r"[^\d]", "", raw_gross)
            price = digits
            price_value = int(digits) if digits else 0
            tax = "TTC"
    except Exception as e:
        print(f"Price extraction error: {e}")
    

    def extract_text_or_default(soup, selector, default=""):
        """Extract text from a given selector or return a default value."""
        element = soup.select_one(selector)
        if element:
            return element.get_text(strip=True)
        else:
            print(f"Element not found for selector: {selector}")
            return default

    def extract_images_from_carousel(soup):
        """
        Extract all unique image URLs from the vehicle carousel.
        Removes duplicates from Slick cloned slides.
        """
        images = []
        seen = set()

        try:
            # Find ALL thumbnail anchors
            links = soup.select("a.dxim_image_thumbnail_link")

            for link in links:
                # Prefer data-src (full image)
                img_url = link.get("data-src")

                # Fallback to <img src="...">
                if not img_url:
                    img_tag = link.find("img")
                    if img_tag:
                        img_url = img_tag.get("src")

                # Add only unique URLs
                if img_url and img_url not in seen:
                    seen.add(img_url)
                    images.append(img_url)

            print(f"[IMAGE] Extracted {len(images)} unique images")

        except Exception as e:
            print(f"[IMAGE ERROR] {e}")

        return images

    # Image extraction
    images = []
    try:
        images = extract_images_from_carousel(soup)
    except Exception as e:
        print(f"Image error: {e}")

    # Vehicle data extraction
    vehicle_data = {}
    try:
        specs_div = soup.find("div", class_="dxim_vehicle_specifics_list_single")
        if specs_div:
            for field in specs_div.find_all("div", class_="field"):
                label = field.find("div", class_="label").get_text(strip=True).replace(":", "").lower()
                value = field.find("div", class_="fact").get_text(strip=True)
                # Normalize keys
                key = re.sub(r'\W+', '_', label)
                vehicle_data[key] = value
    except Exception as e:
        print(f"Vehicle data error: {e}")

    # Extract fuel type and engine size for filtering
    raw_fuel = vehicle_data.get("fuel", "")
    energie = normalize_energie(raw_fuel)
    
    raw_performance = vehicle_data.get("performance", "")
    engine_size = extract_engine_size(raw_performance)
    
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


    # Options extraction (not present in provided HTML)
    options = []

    # Description extraction (not present in provided HTML)
    description = ""
    raw_km = vehicle_data.get("mileage", "")
    km = 0
    if raw_km:
        km_digits = re.sub(r"[^\d]", "", raw_km)
        try:
            km = int(km_digits)
        except ValueError:
            km = 0
    def extract_first_registration_year(soup):
        elem = soup.select_one("div.fact.first_registration")
        if not elem:
            return ""

        text = elem.get_text(strip=True)

        # Expect formats like "04/2025" or "2025"
        match = re.search(r"(\d{4})", text)
        if match:
            return match.group(1)  # Return 2025

        return ""

    # Split title into words
    words = title.split()
    # marque = first word
    marque = words[0] if len(words) >= 1 else ""
    # model = second + third words (or whatever remains)
    model = ""
    if len(words) >= 3:
        model = " ".join(words[1:3])
    elif len(words) == 2:
        model = words[1]

    # Mapping to final structure
    vehicle_info = {
        "titre": title,
        "description": description,
        "numero": vehicle_data.get("internal_number", "").replace(" ", "_") + "_" + str(price_value),
        "date_depot": datetime.now().isoformat(),
        "site_origine": "Dickreich.com",
        "categorie": "Automobiles & Vehicules",
        "category": "voiture",
        "images": images,
        "url": url,
        "annee": extract_first_registration_year(soup),
        "marque": marque,  
        "model": model,  
        "km": km,
        "km_unit": "KM",
        "moteur": raw_performance,
        "couleur": vehicle_data.get("manufacturer_color", ""),
        "options": options,
        "energie": energie,
        "transmission": normalize_transmission(vehicle_data.get("gearbox", "")),
        "prix": price,
        "prix_value": price_value,
        "prix_dec": price_value,
        "prix_unit": "€",
        "tax": tax,
        "etat": "Neuf" if "neuf" in title.lower() else "Occasion",
        "date_crawl": datetime.now().isoformat(),
        "status": "200",
        "as_photo": "Avec photo" if images else "Sans photo",
        "as_prix": "Avec prix" if price_value else "Sans prix",
        "wilaya": "",
        "commune": "",
        "engine_size_liters": engine_size,  # Added for reference
    }

    # Clean empty fields
    for key in vehicle_info:
        if vehicle_info[key] is None:
            vehicle_info[key] = ""
        elif isinstance(vehicle_info[key], list) and not vehicle_info[key]:
            vehicle_info[key] = []
    
    print(f"✅ ACCEPTED: {vehicle_info['numero']} - {energie} {engine_size}L - {km} km- {vehicle_info['annee']}")
    insert_data_to_es(vehicle_info, "voiture")
    return vehicle_info