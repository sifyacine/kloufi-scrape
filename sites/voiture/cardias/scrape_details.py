import re
import json
from datetime import datetime
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from tenacity import retry, stop_after_attempt, wait_exponential
import sys
sys.path.insert(1, '../../global')
from insert_scrape import insert_data_to_es

def str_to_float(text):
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

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1))
async def extract_car_details(url):
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        text_mode=False,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
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
    
    # --- Title extraction ---
    title = ""
    try:
        # Preferably the title is in a <div> with class "field--name-title"
        title_div = soup.find("div", class_="field--name-title")
        if title_div:
            title = title_div.get_text(strip=True)
    except Exception as e:
        print(f"Title error: {e}")
    
    # --- Price extraction ---
    price = ""
    price_value = 0
    try:
        # Look for a container whose class contains the updated price marker
        price_container = soup.find("div", class_=lambda x: x and "product--variation-field--variation_price__" in x)
        if price_container:
            price_item = price_container.find("div", class_="field__item")
            if price_item:
                price = price_item.get_text(strip=True)
                price_value = str_to_float(price)
    except Exception as e:
        print(f"Price error: {e}")
    
    # --- Images extraction ---
    images = []
    try:
        image_section = soup.find("div", class_="field--name-field-media-image")
        if image_section:
            a_tags = image_section.find_all("a", class_="colorbox")
            for a in a_tags:
                img_url = a.get("href")
                if img_url:
                    images.append(img_url)
    except Exception as e:
        print(f"Image error: {e}")
    
    # --- Brand & Model extraction ---
    marque = ""
    model = ""
    try:
        brand_section = soup.find("div", class_="field--name-field-brand")
        if brand_section:
            ul = brand_section.find("ul")
            if ul:
                brand_items = [li.get_text(strip=True) for li in ul.find_all("li")]
                if brand_items:
                    marque = brand_items[0]
                    if len(brand_items) > 1:
                        model = brand_items[1]
    except Exception as e:
        print(f"Brand/Model error: {e}")
    
    # --- Transmission extraction from select element ---
    transmission = ""
    try:
        select_trans = soup.find("select", id="edit-purchased-entity-0-attributes-attribute-transmission")
        if select_trans:
            option_trans = select_trans.find("option", selected=True)
            if option_trans:
                transmission = option_trans.get_text(strip=True)
    except Exception as e:
        print(f"Transmission extraction error: {e}")

    # --- Energy extraction from select element ---
    energie = ""
    try:
        select_energy = soup.find("select", id="edit-purchased-entity-0-attributes-attribute-energy")
        if select_energy:
            option_energy = select_energy.find("option", selected=True)
            if option_energy:
                energie = option_energy.get_text(strip=True)
    except Exception as e:
        print(f"Energy extraction error: {e}")
    
    # --- Exterior Color extraction ---
    couleur = ""
    try:
        couleur_select = soup.find("select", id="edit-purchased-entity-0-attributes-attribute-exterior-color")
        if couleur_select:
            selected_option = couleur_select.find("option", selected=True)
            if selected_option:
                couleur = selected_option.get_text(strip=True)
    except Exception as e:
        print(f"Color extraction error: {e}")
    
    # --- Updated Description & Details Extraction from Card Body ---
    description = ""
    annee = ""
    km = ""
    moteur = ""
    transmission_from_desc = ""  # May override the select extraction if available
    energie_from_desc = ""
    try:
        card_body = soup.find("div", class_="card-body")
        if card_body:
            body_content = card_body.find("div", class_="clearfix")
            if body_content:
                # If there is a strong tag with title information, use it if title is still empty.
                strong = body_content.find("strong")
                if strong and not title:
                    title = strong.get_text(strip=True)
                li_elements = body_content.find_all("li")
                bullet_texts = [li.get_text(" ", strip=True).replace('\xa0', ' ').strip() 
                                for li in li_elements if li.get_text(strip=True)]
                
                # Process each bullet
                for item in bullet_texts:
                    # For mileage, look for patterns with "KM"
                    if "KM" in item.upper():
                        km = re.sub(r"[^\d]", "", item)
                    # For year, if item is a 4-digit number.
                    elif re.match(r'^\d{4}$', item):
                        annee = item
                    # For transmission, look for patterns like "BVM"
                    elif "BVM" in item.upper():
                        transmission_from_desc = item
                    # For energy, match exactly known values like "ESSENCE" or "DIESEL"
                    elif item.upper() in ["ESSENCE", "DIESEL"]:
                        energie_from_desc = item
                    # For engine details, look for items containing "THP"
                    elif "THP" in item.upper():
                        moteur = item
                # Optionally, join all bullets for a full description.
                description = " ".join(bullet_texts)
    except Exception as e:
        print(f"Description/Details error: {e}")
    
    # If the detailed card body provided transmission or energy, use those values.
    if transmission_from_desc:
        transmission = transmission_from_desc
    if energie_from_desc:
        energie = energie_from_desc
    
    # --- Mapping to final structure ---
    vehicle_info = {
        "titre": title,
        "description": description,
        "numero": (model or marque).replace(" ", "_") + "_" + str(price_value),
        "date_depot": datetime.now().isoformat(),
        "site_origine": "Cardias.fr",
        "category": "Automobiles & Vehicules",
        "images": images,
        "url": url,
        "papers": "",
        "annee": annee if annee else datetime.now().year - 3,
        "marque": marque,
        "model": model,
        "km": km,
        "km_unit": "KM",
        "moteur": moteur,
        "couleur": couleur,
        "options": [],  # Since details are now separated, you may leave options empty or adjust as needed.
        "energie": convert_essence(energie),
        "transmission": convert_transmission(transmission),
        "prix": price,
        "prix_value": price_value,
        "prix_dec": price_value,
        "prix_unit": "€",
        "etat": "Neuf" if "neuf" in url.lower() else "Occasion",
        "date_crawl": datetime.now().isoformat(),
        "status": "200",
        "as_photo": "Avec photo" if images else "Sans photo",
        "as_prix": "Avec prix" if price_value else "Sans prix",
        "wilaya": "",
        "commune": "",
    }
    
    # Ensure no field is None; set to empty string or list if appropriate.
    for key in vehicle_info:
        if vehicle_info[key] is None:
            vehicle_info[key] = ""
        elif isinstance(vehicle_info[key], list) and not vehicle_info[key]:
            vehicle_info[key] = []
    
    print(f"Extracted data for {vehicle_info['numero']}")
    insert_data_to_es(vehicle_info, "voiture")
    return vehicle_info
