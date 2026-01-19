import re
import sys
import os
import asyncio
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../')))
from utils.immobilier import ImmobilierUtils

try:
    sys.path.insert(1, '../../../global')
    from insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] Inserting data to ES index '{index}'")

def parse_address(address_text):
    # Expected format: "Hydra, Alger, Algeria"
    parts = address_text.split(",")
    if len(parts) >= 2:
        return parts[0].strip(), parts[1].strip()
    return address_text.strip(), ""

def convert_relative_date(rel_date_str):
    now = datetime.now()
    m = re.search(r"il y a\s+(\d+)\s+(\w+)", rel_date_str, re.IGNORECASE)
    if m:
        value = int(m.group(1))
        unit = m.group(2).lower()
        if "jour" in unit:
            new_date = now - timedelta(days=value)
        elif "mois" in unit:
            new_date = now - timedelta(days=value * 30)
        elif "an" in unit:
            new_date = now - timedelta(days=value * 365)
        else:
            new_date = now
        return new_date.strftime("%Y-%m-%d")
    return ""

async def extract_property_details(url):
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        text_mode=False
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
        raise Exception(f"Failed to load detail page: {result.error_message}")
    
    soup = BeautifulSoup(result.html, "html.parser")
    
    # --- Extract Title ---
    titre = ImmobilierUtils.extract_text_or_default(soup, "h1.title.title_code")
    
    # --- Extract Price and Published Date ---
    price_text = ""
    date_depot = ""
    ul_header = soup.find("ul", class_="item-header")
    if ul_header:
        li_tags = ul_header.find_all("li")
        if li_tags:
            # Assuming first <li> contains price info (remove icon text)
            price_text = li_tags[0].get_text(strip=True)
        if len(li_tags) >= 2:
            # Second <li> holds published date info; remove the label if needed
            date_depot = li_tags[1].get_text(strip=True).replace("Published date:", "").strip()
    
    # --- Extract Address ---
    adresse = ""
    commune = ""
    wilaya = ""
    item_location = soup.find("ul", id="item_location")
    if item_location:
        li_addr = item_location.find("li")
        if li_addr:
            adresse = li_addr.get_text(strip=True)
            commune, wilaya = parse_address(adresse)
    
    # --- Extract Description ---
    description_content = ""
    description_div = soup.find("div", id="description")
    if description_div:
        p_desc = description_div.find("p")
        if p_desc:
            description_content = p_desc.get_text(strip=True)
    
    # --- Extract Images ---
    images_list = []
    photos_div = soup.find("div", class_="item-photos")
    if photos_div:
        img_tags = photos_div.find_all("img")
        for img in img_tags:
            src = img.get("src", "")
            if src:
                images_list.append(src)
        images_list = list(dict.fromkeys(images_list))  # Remove duplicates
    
    # --- Parse Numerical Values ---
    prix_dec = ImmobilierUtils.parse_float_or_none(price_text)
    
    # --- Add nb_pieces field (rooms) ---
    nb_pieces = ""  # Replace with actual extraction logic if room info is present
    
    # --- Extract Property ID ---
    numero = url.rstrip("/").split("/")[-1]
    now_iso = datetime.now().isoformat()
    
    # --- Build Final Result ---
    property_details = {
        "titre": titre,
        "url": url,
        "site_origine": "algeriahome.com",
        "date_crawl": now_iso,
        "numero": numero,
        "date_depot": date_depot,
        "transaction": ImmobilierUtils.detect_transaction_from_title(titre) or "Vente",
        "category": "immobilier",
        "bien": ImmobilierUtils.convert_property_type(titre),
        "superficie": "",  # Not available in snippet
        "superficie_unit": "m²",
        "nb_pieces": nb_pieces,  # New field for rooms
        "description": description_content,
        "prix": price_text,
        "prix_dec": prix_dec,
        "prix_unit": "DA" if price_text else "",
        "images": images_list,
        "adresse": f"{commune}, {wilaya}" if commune and wilaya else "",
        "wilaya": wilaya,
        "commune": commune,
        "etage": "",  # Not available in snippet
        "status": 200,
        "date_verif": now_iso,
        "as_photo": "Avec photo" if images_list else "Sans photo",
        "as_prix": "Avec prix" if price_text else "Sans prix"
    }
    
    print("Extracted property details:", property_details)
    insert_data_to_es(property_details, "immobilier")
    return property_details


