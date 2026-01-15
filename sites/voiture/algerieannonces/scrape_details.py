import re
import json
from datetime import datetime
from time import sleep
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from tenacity import retry, stop_after_attempt, wait_exponential
import sys
sys.path.insert(1, '../../global')
from insert_scrape import insert_data_to_es

BASE_URL = "https://www.algerieannonces.com/"

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

def save_to_json_file(data, filename=fr"voiture\algerieannonces\data\scraped_vehicles.json"):
    """Append data to a JSON file."""
    try:
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        except FileNotFoundError:
            existing = []
        existing.append(data)
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        print(f"Data saved to {filename}.")
    except Exception as e:
        print(f"Error saving data: {e}")

def extract_model(title, brand):
    """Extract the model from the title based on the brand."""
    if not brand:
        return ""
    words = title.split()
    try:
        idx = words.index(brand)
        return words[idx+1] if idx+1 < len(words) else ""
    except ValueError:
        return ""

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1))
async def extract_car_details(url):
    # --- crawl page ---
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

    # --- title & price ---
    title_el = soup.select_one("div.description h1")
    title = title_el.get_text(strip=True) if title_el else ""

    price_el = soup.select_one("div.description strong.price span")
    price = price_el.get_text(strip=True) if price_el else ""
    price_value = str_to_float(price)

    # --- images gallery (full URLs) ---
    images = []
    for a in soup.select(".ad-nav .ad-thumbs ul.ad-thumb-list li a"):
        href = a.get("href")
        if href:
            images.append(urljoin(BASE_URL, href))

    # --- vehicle properties: marque & modèle ---
    vehicle_data = {}
    for li in soup.select(".parameter ul.info li.label"):
        txt = li.get_text(strip=True)
        if ":" in txt:
            key, val = txt.split(":", 1)
            vehicle_data[key.strip().lower()] = val.strip()

    # --- extra details: année, kilométrage, carburant, puissance ---
    for li in soup.select("#extraQuestionName li"):
        txt = li.get_text(" ", strip=True)
        if ":" in txt:
            key, val = txt.split(":", 1)
            vehicle_data[key.strip().lower()] = val.strip()

    # --- info-holder: wilaya, commune, date_depot ---
    wilaya = commune = date_depot = ""
    info_lis = soup.select("ul.info-holder li")
    if info_lis:
        # 1st <li>: "Oum El Bouaghi / Ain babouche"
        first = info_lis[0].get_text(strip=True)
        if "/" in first:
            w, c = first.split("/", 1)
            wilaya, commune = w.strip(), c.strip()

        # 2nd <li>: "Publiée le: 2 Apr-10:30"
        if len(info_lis) > 1:
            second = info_lis[1].get_text(" ", strip=True)
            m = re.search(r"Publiée le[:\s]+([\d]{1,2}\s+\w+)", second)
            if m:
                date_depot = m.group(1)

    # --- annonce number ---
    numero = ""
    num_li = soup.find("li", string=re.compile(r"Annonce N°"))
    if num_li:
        m = re.search(r"Annonce N°:?\s*(\d+)", num_li.get_text())
        if m:
            numero = m.group(1)

    # --- description ---
    desc_blk = soup.find("div", class_="block")
    if desc_blk and (hdr := desc_blk.find("strong", class_="titledetail")):
        hdr.extract()
    description = desc_blk.get_text(" ", strip=True) if desc_blk else ""

    # --- derive model from title & marque ---
    marque = vehicle_data.get("marque", "")
    model = extract_model(title, marque) or vehicle_data.get("modèle", "")

    # --- assemble final dict ---
    vehicle_info = {
        "titre": title,
        "description": description,
        "numero": numero,
        "date_depot": datetime.now().isoformat() if date_depot == "" else date_depot,
        "date_crawl": datetime.now().isoformat(),
        "site_origine": "Algerieannonces.com",
        "categorie": "Automobiles & Vehicules",
        "category": "voiture",
        "images": images,
        "url": url,
        "papers": "",
        "annee": vehicle_data.get("année", ""),
        "marque": marque,
        "model": model,
        "km": vehicle_data.get("kilométrage", ""),
        "km_unit": "KM",
        "moteur": vehicle_data.get("puissance", ""),
        "couleur": vehicle_data.get("couleur", ""),
        "options": [],  # no explicit options list
        "energie": convert_essence(vehicle_data.get("carburant", "")),
        "transmission": "",
        "prix": price,
        "prix_value": price_value,
        "prix_dec": price_value,
        "prix_unit": "DA",
        "etat": "Inconnu",
        "status": "200",
        "as_photo": "Avec photo" if images else "Sans photo",
        "as_prix": "Avec prix" if price_value else "Sans prix",
        "wilaya": wilaya,
        "commune": commune,
    }

    # Normalize nulls/lists
    for k, v in vehicle_info.items():
        if v is None:
            vehicle_info[k] = ""
        elif isinstance(v, list) and not v:
            vehicle_info[k] = []

    print(f"Extracted data for annonce #{vehicle_info['numero']}")
    insert_data_to_es(vehicle_info, index_name="voiture")
    return vehicle_info
