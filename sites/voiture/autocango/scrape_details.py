import re
import json
from datetime import datetime
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
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

def get_high_quality_image_url(img_url):
    """
    Convert thumbnail URL to high-quality image URL.
    """
    if not img_url:
        return ""
    
    # Split by '?' to get base URL
    base_url = img_url.split('?')[0]
    high_quality_url = f"{base_url}?x-image-process=image/quality,q_90/resize,w_800,h_600"
    return high_quality_url


async def extract_car_details(url):
    # Browser configuration for crawling
    browser_config = BrowserConfig(
        headless=True,
        browser_type="firefox", # Kept as firefox as per original file
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
                # print("Using small-img-carousel...")
                thumbs = small_carousel.find_all("img")
                for img in thumbs:
                    img_url = img.get("src") or img.get("data-src", "")
                    if img_url:
                        base_url = img_url.split("?")[0]      # remove low-res params
                        high_res = get_high_quality_image_url(base_url)

                        if base_url not in image_set:
                            images.append(high_res)
                            image_set.add(base_url)
                            # print(f"Added thumbnail image: {high_res[:100]}...")

            # 2️⃣ Fallback: el-carousel
            if not images:
                main_carousel = soup.find("div", class_="el-carousel")
                if main_carousel:
                    # print("Fallback to el-carousel...")
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
        
        kilometrage_raw = vehicle_data.get("mlg_km_", "")
        km_val, km_unit = VoitureUtils.normalize_mileage(kilometrage_raw)

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
        
        # Price extraction
        price_raw = ""
        try:
            price_elem = soup.find("p", class_="fob")
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                # Clean up "Price: $..." prefix
                price_raw = re.sub(r'^Price:\s*\$?', '', price_text, flags=re.IGNORECASE).strip()
        except Exception as e:
             print(f"Price error: {e}")
             
        # Use VoitureUtils.parse_price
        # Note: price_raw might be "$14,500" or similar. parse_price handles basic cleanup.
        _, price_val_str, price_decimal, price_unit = VoitureUtils.parse_price(price_raw, "$")

        
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
            "km": km_val,
            "km_unit": km_unit, 
            "moteur": cylindree,
            "couleur": couleur,
            "options": options,
            "energie": VoitureUtils.normalize_fuel(energy_type) if energy_type else "",
            "transmission": VoitureUtils.normalize_transmission(transmission),
            # "puissance": puissance_val,
            "prix": price_raw,
            "prix_value": price_val_str,
            "prix_dec": price_decimal,
            "prix_unit": price_unit, # Should default to $ as passed 
            "etat": "Occasion" if km_val else "Neuf",
            "date_crawl": datetime.now().isoformat(),
            "status": "200",
            "as_photo": "Avec photo" if images else "Sans photo",
            "as_prix": "Avec prix" if price_val_str else "Sans prix",
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
        
        print(f"Extracted data for {vehicle_info.get('numero')}")
        insert_data_to_es(vehicle_info, index_name="voiture")
        return vehicle_info
