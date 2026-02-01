import re
import json
from datetime import datetime
from time import sleep
from urllib.parse import urljoin
import sys, os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from tenacity import retry, stop_after_attempt, wait_exponential
from utils.voiture import VoitureUtils

try:
    from insert2db.insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] there is a problem in saving data'{index}'")

BASE_URL = "https://www.algerieannonces.com/"

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
        idx = [w.lower() for w in words].index(brand.lower())
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
    title = VoitureUtils.extract_text(soup, "div.description h1")
    
    price_raw = VoitureUtils.extract_text(soup, "div.description strong.price span")
    # AlgerieAnnonces prices are usually "260 Millions" or just numbers.
    # parse_price handles "Millions" if present in the value string or separate unit.
    # Here the unit might be part of the string or missing.
    # VoitureUtils.parse_price splits alpha from numeric if unit arg is None.
    # But wait, my parse_price implementation expects unit locally or assumes DA.
    # Let's check AlgerieAnnonces price format. It's often "180 Millions offert" or "245 Millions negociable".
    # I should pass the whole string to parse_price logic?
    # My current `parse_price` splits numbers and cleans them. It takes `unit_raw`.
    # Let's just use `parse_price(price_raw)` and let it extract.
    # Actually `parse_price` as implemented expects `price_raw` to be the numeric part mostly, but it cleans non-numerics.
    # If I pass "240 Millions", `price_val_str` becomes "240". 
    # `unit_raw` is None, so it checks `DA`.
    # Wait, `VoitureUtils.parse_price` implementation logic:
    # if unit_raw is passed, it uses it. If not, it defaults to DA.
    # It does NOT extract unit from `price_raw` automatically in the current implementation.
    # I should verify `VoitureUtils.parse_price` again.
    # "if "million" in unit_clean: conversion = 10000".
    # It relies on `unit_raw`.
    # So for AlgerieAnnonces, I effectively need to split it if the text contains the unit.
    
    price_val_str = ""
    price_unit = ""
    price_decimal = 0
    
    if price_raw:
        # Simple heuristic for AlgerieAnnonces
        # "240 Millions" -> val=240, unit=Millions
        match = re.search(r'([\d.,]+)\s*([a-zA-Z]+)', price_raw)
        if match:
            raw_val = match.group(1)
            raw_unit = match.group(2)
            _, price_val_str, price_decimal, price_unit = VoitureUtils.parse_price(raw_val, raw_unit)
        else:
            _, price_val_str, price_decimal, price_unit = VoitureUtils.parse_price(price_raw)

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
        first = info_lis[0].get_text(strip=True)
        if "/" in first:
            w, c = first.split("/", 1)
            wilaya, commune = w.strip(), c.strip()

        if len(info_lis) > 1:
            second = info_lis[1].get_text(" ", strip=True)
            m = re.search(r"Publiée le[:\s]+([\d]{1,2}\s+\w+)", second)
            if m:
                # Need to convert this date format "2 Apr-10:30" to ISO?
                # VoitureUtils.parse_date handles standard patterns. This one is tricky.
                # "2 Apr-10:30" implies current year?
                # I'll force it to ISO if possible, or leave as is if not critical normalization yet.
                # Using `parse_date` might fail. 
                # Let's leave it as string for now if it fails, or try to init with current year.
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
    
    # Normalize Mileage
    km_raw = vehicle_data.get("kilométrage", "")
    km_val, km_unit = VoitureUtils.normalize_mileage(km_raw)

    vehicle_info = {
        "titre": title,
        "description": description,
        "numero": numero,
        "date_depot": datetime.now().isoformat() if not date_depot else date_depot, # TODO: improve date parsing for this specific format in Utils later
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
        "km": km_val,
        "km_unit": km_unit,
        "moteur": vehicle_data.get("puissance", ""),
        "couleur": vehicle_data.get("couleur", ""),
        "options": [],
        "energie": VoitureUtils.normalize_fuel(vehicle_data.get("carburant", "")),
        "transmission": VoitureUtils.normalize_transmission(vehicle_data.get("boite de vitesse", "")), # Assuming key might be 'boite de vitesse'
        "prix": price_raw,
        "prix_value": price_val_str,
        "prix_dec": price_decimal,
        "prix_unit": price_unit if price_unit else "DA",
        "etat": "Inconnu",
        "status": "200",
        "as_photo": "Avec photo" if images else "Sans photo",
        "as_prix": "Avec prix" if price_val_str else "Sans prix",
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
