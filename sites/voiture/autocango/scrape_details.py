import re
import json
from datetime import datetime
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
import sys
sys.path.insert(1, '../../global')
from insert_scrape import insert_data_to_es

def str_to_float(text):
    """Convert a string price to a float, handling US-style formatting."""
    try:
        # Remove currency symbols and letters
        num = re.sub(r"[^\d.,]", "", text)
        # Remove comma (thousands separator)
        num = num.replace(",", "")
        return float(num)
    except Exception:
        return 0

def extract_model(title, brand):
    """Extract the model from the title based on the brand."""
    if not brand or not title:
        return ""
    
    # Try to find the model that comes after the brand
    pattern = rf'{re.escape(brand)}\s+([^\s\d][^\d]+)'
    match = re.search(pattern, title, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # If brand not found in title, try to extract from first part
    words = title.split()
    if len(words) >= 2:
        return words[1] if not words[1].isdigit() and words[1] != "III" else words[0]
    
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

def get_high_quality_image_url(img_url):
    """
    Convert thumbnail URL to high-quality image URL.
    Removes query parameters and replaces low-res specs with high-res ones.
    """
    if not img_url:
        return ""
    
    # Split by '?' to get base URL
    base_url = img_url.split('?')[0]
    
    # Replace the query parameters with higher quality settings
    # Original: ?x-image-process=image/quality,q_10/resize,w_160,h_120/imageslim
    # Better: ?x-image-process=image/quality,q_90/resize,w_800,h_600
    # Or just remove parameters entirely to get original
    
    # Option 1: Return without parameters (original quality, but might be large)
    # return base_url
    
    # Option 2: Add better quality parameters
    high_quality_url = f"{base_url}?x-image-process=image/quality,q_90/resize,w_800,h_600"
    
    return high_quality_url


async def extract_car_details(url):
    # Browser configuration for crawling
    browser_config = BrowserConfig(
        headless=True,
        browser_type="firefox",
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
            title_elem = soup.find("p", class_="car-name")
            if title_elem:
                # Extract title, excluding MSRP part
                title = title_elem.get_text(strip=True).split("MSRP")[0].strip()
        except Exception as e:
            print(f"Title error: {e}")
        
        # Clean the title
        title = re.sub(r'<[^>]+>', '', title)
        
        # FIXED: Correct carousel + high resolution images
        images = []
        image_set = set()

        try:
            # 1️⃣ Try the small-images carousel (the real one)
            small_carousel = soup.find("div", class_="small-img-carousel")
            if small_carousel:
                print("Using small-img-carousel...")
                thumbs = small_carousel.find_all("img")
                for img in thumbs:
                    img_url = img.get("src") or img.get("data-src", "")
                    if img_url:
                        base_url = img_url.split("?")[0]      # remove low-res params
                        high_res = get_high_quality_image_url(base_url)

                        if base_url not in image_set:
                            images.append(high_res)
                            image_set.add(base_url)
                            print(f"Added thumbnail image: {high_res[:100]}...")

            # 2️⃣ Fallback: el-carousel
            if not images:
                main_carousel = soup.find("div", class_="el-carousel")
                if main_carousel:
                    print("Fallback to el-carousel...")
                    main_imgs = main_carousel.find_all("img")
                    for img in main_imgs:
                        img_url = img.get("src") or img.get("data-src", "")
                        if img_url:
                            base_url = img_url.split("?")[0]
                            high_res = get_high_quality_image_url(base_url)
                            if base_url not in image_set:
                                images.append(high_res)
                                image_set.add(base_url)

            print(f"Total images extracted: {len(images)}")

        except Exception as e:
            print(f"Image extraction error: {e}")

        
        # Vehicle data extraction from base-info and description table
        vehicle_data = {}
        try:
            # Extract from base-info (e.g., mileage)
            base_info = soup.find("div", class_="base-info")
            if base_info:
                items = base_info.find_all("div", class_="item")
                for item in items:
                    label = item.find("p", class_="label")
                    value = item.find("p", class_="value")
                    if label and value:
                        key = label.get_text(strip=True).lower()
                        key = re.sub(r'\W+', '_', key)
                        vehicle_data[key] = value.get_text(strip=True)
                        # Debug: Print key-value pair to verify mileage extraction
                        print(f"Vehicle data extracted: {key} = {vehicle_data[key]}")
            
            # Extract from description table (e.g., engine, transmission, color, fuel)
            desc_table = soup.find("table", class_="el-descriptions__table")
            if desc_table:
                rows = desc_table.find_all("tr")
                for row in rows:
                    cells = row.find_all("td")
                    for i in range(0, len(cells), 2):
                        label = cells[i].get_text(strip=True).lower()
                        value = cells[i + 1].get_text(strip=True) if i + 1 < len(cells) else ""
                        if label and value:
                            key = re.sub(r'\W+', '_', label)
                            vehicle_data[key] = value
                            # Debug: Print key-value pair
                            print(f"Description table extracted: {key} = {vehicle_data[key]}")
        except Exception as e:
            print(f"Vehicle data error: {e}")
        
        # Options extraction
        options = []
        try:
            accessories_section = soup.find("ul", class_="accessories")
            if accessories_section:
                option_items = accessories_section.find_all("li", class_="ellipsis")
                for item in option_items:
                    option_text = item.get_text(strip=True)
                    if option_text:
                        options.append(option_text)
            # If no accessories section is found, options remains empty
        except Exception as e:
            print(f"Options error: {e}")
        
        # Numero extraction from URL
        numero = ""
        try:
            url_match = re.search(r'sku/usedcar-[^/]+-(\w+)', url)
            if url_match:
                numero = url_match.group(1)
        except Exception as e:
            print(f"Numero error: {e}")
        
        # Extract detailed information
        description = title  # Use title as description, as no detailed section provided
        annee = vehicle_data.get("reg_year", "").split("-")[0] if vehicle_data.get("reg_year", "") else ""
        kilometrage = vehicle_data.get("mlg_km_", "")  # Updated to use correct key
        cylindree = vehicle_data.get("engine", "").split()[0] if vehicle_data.get("engine", "") else ""  # e.g., "1.6T" from "1.6T 197HP L4"
        puissance = ""
        if vehicle_data.get("engine", ""):
            power_match = re.search(r'(\d+)HP', vehicle_data.get("engine", ""), re.IGNORECASE)
            if power_match:
                puissance = power_match.group(1) + " CV"
        couleur = vehicle_data.get("exterior_color", "")
        energy_type = vehicle_data.get("fuel", "")
        transmission = vehicle_data.get("transmission", "")
        
        # Extract brand (marque) from title
        marque = ""
        if title:
            brand_match = re.match(r'^\d{4}\s+(\w+)', title)
            if brand_match:
                marque = brand_match.group(1).strip()
        
        # Extract model using the improved function
        model = extract_model(title, marque)
        puissance_val = ""
        if puissance:
            match = re.search(r'\d+', puissance)
            if match:
                puissance_val = int(match.group())
                
        price = ""
        price_value = 0
        try:
            price_elem = soup.find("p", class_="fob")
            if price_elem:
                price = price_elem.get_text(strip=True)
                price = re.sub(r'^Price:\s*\$?', '', price, flags=re.IGNORECASE).strip()
                price_value = str_to_float(price)
        except Exception as e:
            print(f"Price error: {e}")
        
        # Mapping to final structure
        vehicle_info = {
            "titre": title,
            "description": description,
            "numero": numero,
            "date_depot": datetime.now().isoformat(),
            "site_origine": "AutoCango.com",
            "categorie": "Automobiles & Vehicules",
            "category": "voiture",

            "images": images,
            "url": url,
            "annee": annee,
            "marque": marque,
            "model": model,
            "km": kilometrage,
            "km_unit": "KM",
            "moteur": cylindree,
            "couleur": couleur,
            "options": options,
            "energie": normalize_energie(energy_type) if energy_type else "",
            "transmission": normalize_transmission(transmission),
            # "puissance": puissance_val,
            "prix": price,
            "prix_value": price_value,
            "prix_dec": price_value,
            "prix_unit": "$",
            "etat": "Occasion" if kilometrage else "Neuf",
            "date_crawl": datetime.now().isoformat(),
            "status": "200",
            "as_photo": "Avec photo" if images else "Sans photo",
            "as_prix": "Avec prix" if price else "Sans prix",
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
        
        print(f"Extracted data for {json.dumps(vehicle_info, indent=2)}")
        insert_data_to_es(vehicle_info, "voiture")
        return vehicle_info