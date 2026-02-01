import re
import json
from datetime import datetime
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from tenacity import retry, stop_after_attempt, wait_exponential
import sys, os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from utils.voiture import VoitureUtils

try:
    from insert2db.insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] there is a problem in saving data'{index}'")

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
    
    # Title extraction: Look for a div with class "vehica-car-name"
    title = ""
    try:
        title_elem = soup.find("div", class_="vehica-car-name") or \
                     soup.find("h1", class_="title") or \
                     soup.find("meta", property="og:title")
        if title_elem:
            title = title_elem.get("content", "").strip() if title_elem.name == "meta" else title_elem.get_text(strip=True)
    except Exception as e:
        print(f"Title error: {e}")
    
    if not title:
        print(f"Title is empty for URL: {url}. Retrying extraction...")
        raise Exception("Empty title encountered")
    
    # Price extraction
    price_raw = VoitureUtils.extract_text(soup, "div.vehica-car-price")
    _, price_value_str, price_decimal, _ = VoitureUtils.parse_price(price_raw)

    # Image extraction: Extract images from the slider
    images = []
    try:
        gallery_wrapper = soup.find("div", class_="vehica-swiper-wrapper")
        if gallery_wrapper:
            slides = gallery_wrapper.find_all("div", class_=lambda x: x and "vehica-swiper-slide" in x)
            for slide in slides:
                img_url = slide.get("data-src")
                if img_url and img_url.startswith("http"):
                    images.append(img_url)
    except Exception as e:
        print(f"Image error: {e}")

    # Vehicle data extraction: Loop through all "vehica-grid" elements for key/value pairs
    vehicle_data = {}
    try:
        grid_elements = soup.find_all("div", class_="vehica-grid")
        for grid in grid_elements:
            name_elem = grid.find("div", class_=lambda x: x and "vehica-car-attributes__name" in x)
            value_elem = grid.find("div", class_=lambda x: x and "vehica-car-attributes__values" in x)
            if name_elem and value_elem:
                label = name_elem.get_text(strip=True).replace(":", "").lower()
                # Normalize characters
                label = label.replace('é', 'e').replace('è', 'e')
                value = value_elem.get_text(strip=True)
                key = re.sub(r'\W+', '_', label)
                vehicle_data[key] = value
    except Exception as e:
        print(f"Vehicle data error: {e}")

    # Extract Energie from the last <a class="vehica-car-feature"> element
    # Or fallback to vehicle-data
    energie = ""
    try:
        energie_elems = soup.find_all("a", class_="vehica-car-feature")
        if energie_elems:
            last_energie_elem = energie_elems[-1]
            energie = last_energie_elem.get("title", "").strip() or last_energie_elem.get_text(strip=True)
    except Exception as e:
        print(f"Energie extraction error: {e}")


    # Description extraction: Check for typical description containers
    description = ""
    try:
        desc_section = soup.find("div", class_="elementor-widget-text-editor") or \
                       soup.find("div", class_="vehicle-description")
        if desc_section:
            description = ' '.join(desc_section.stripped_strings)
    except Exception as e:
        print(f"Description error: {e}")

    # Options extraction: Use the "vehica-car-features-pills" container
    options = []
    try:
        options_container = soup.find("div", class_="vehica-car-features-pills")
        if options_container:
            options = [item.find("span").get_text(strip=True) 
                       for item in options_container.find_all("div", class_="vehica-car-features-pills__single")]
    except Exception as e:
        print(f"Options error: {e}")

    # Numero extraction: Get the Offer ID from the vehicle offer section
    numero = ""
    try:
        offer_elem = soup.find("div", class_="vehica-car-offer-id")
        if offer_elem:
            span_elem = offer_elem.find("span", class_="vehica-car-offer-id__label")
            if span_elem:
                text = span_elem.get_text(strip=True)
                # Example text: "Offer ID #32435"
                match = re.search(r"#(\d+)", text)
                if match:
                    numero = match.group(1)
    except Exception as e:
        print(f"Numero error: {e}")

    # Mapping vehicle data to final fields
    annee = vehicle_data.get("annee", "")
    
    kilometrage_raw = vehicle_data.get("kilometrage", "")
    km_val, km_unit = VoitureUtils.normalize_mileage(kilometrage_raw)

    couleur = vehicle_data.get("couleurs", vehicle_data.get("couleur", ""))
    transmission = vehicle_data.get("transmission", "")
    
    date_depot = datetime.now().isoformat()
    
    # Expedition is kept for legacy purposes if needed
    expedition = ""
    try:
        grid_elements = soup.find_all("div", class_="vehica-grid")
        for grid in grid_elements:
            name_elem = grid.find("div", class_=lambda x: x and "vehica-car-attributes__name" in x)
            if name_elem and "expédition algérie" in name_elem.get_text(strip=True).lower():
                value_elem = grid.find("div", class_=lambda x: x and "vehica-car-attributes__values" in x)
                if value_elem:
                    expedition_str = value_elem.get_text(strip=True)
                    expedition = expedition_str
                    break
    except Exception as e:
        print(f"expedition error: {e}")

    vehicle_info = {
        "titre": title,
        "description": description,
        "numero": numero,
        "date_depot": date_depot,
        "site_origine": "Autoexportmarseille.com",
        "categorie": "Automobiles & Vehicules",
        "category": "voiture",
        "images": images,
        "url": url,
        "annee": annee,
        "marque": vehicle_data.get("marque", title.split()[0] if title else ""),
        "model": vehicle_data.get("modele", vehicle_data.get("model", "")),
        "km": km_val,
        "km_unit": km_unit, 
        "moteur": vehicle_data.get("moteur", ""),
        "couleur": couleur,
        "options": options,
        "energie": VoitureUtils.normalize_fuel(energie),
        "transmission": VoitureUtils.normalize_transmission(transmission),
        "prix": expedition, # Mapped as requested in original file logic
        "prix_value": price_value_str,
        "prix_dec": price_decimal,
        "prix_unit": "€",
        "export": "true",
        "etat": vehicle_data.get("condition", "Occasion"),
        "date_crawl": datetime.now().isoformat(),
        "status": "200",
        "as_photo": "Avec photo" if images else "Sans photo",
        "as_prix": "Avec prix" if price_value_str else "Sans prix",
        "wilaya": "",
        "commune": "",
        "tax": "HT"
    }

    for key in vehicle_info:
        if vehicle_info[key] is None:
            vehicle_info[key] = ""
        elif isinstance(vehicle_info[key], list) and not vehicle_info[key]:
            vehicle_info[key] = []
    
    print(f"Extracted data for {vehicle_info['numero']}")
    insert_data_to_es(vehicle_info, index_name="voiture")
    return vehicle_info
