import re
import sys
import os
import asyncio
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from utils.immobilier import ImmobilierUtils

try:
    from insert2db.insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] Inserting data to ES index '{index}'")

def parse_address(address_text):
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
    
    # Initialize fields
    titre = ""
    date_depot = ""
    transaction = ""
    superficie_text = ""
    no_pieces = ""
    etage = ""
    description_content = ""
    price_text = ""
    images_list = []
    adresse = ""
    commune = ""
    wilaya = ""
    
    # --- Extract Header ---
    header = soup.find("div", class_="heading-properties")
    if header:
        pull_left = header.find("div", class_="pull-left")
        if pull_left:
            h3_title = pull_left.find("h3")
            if h3_title:
                titre = h3_title.get_text(strip=True)
            p_tags = pull_left.find_all("p")
            if p_tags and len(p_tags) >= 1:
                address_raw = p_tags[0].get_text(strip=True)
                adresse = address_raw
                commune, wilaya = parse_address(address_raw)
            if p_tags and len(p_tags) >= 2:
                small_tag = p_tags[1].find("small")
                if small_tag:
                    cal_icon = small_tag.find("i")
                    if cal_icon:
                        cal_icon.decompose()
                    rel_date_str = small_tag.get_text(strip=True)
                    date_depot = convert_relative_date(rel_date_str)
        pull_right = header.find("div", class_="pull-right")
        if pull_right:
            h3_price = pull_right.find("h3")
            if h3_price:
                span_price = h3_price.find("span")
                if span_price:
                    price_text = span_price.get_text(strip=True)
            h4_info = pull_right.find("h4")
            if h4_info:
                info_text = h4_info.get_text(strip=True)
                m = re.search(r"(\d+(?:[\.,]\d+)?)\s*m²", info_text)
                if m:
                    superficie_text = m.group(1)
    
    # --- Extract Details Table ---
    details_table = soup.select_one("div.details.table-responsive")
    if details_table:
        table = details_table.find("table")
        if table:
            tbody = table.find("tbody")
            if tbody:
                row = tbody.find("tr")
                if row:
                    cells = row.find_all("td")
                    if len(cells) >= 4:
                        transaction = cells[0].get_text(strip=True).lower()
                        if not superficie_text:
                            superficie_text = cells[1].get_text(strip=True)
                        etage = cells[2].get_text(strip=True)
                        no_pieces = cells[3].get_text(strip=True)
    
    # --- Extract Description ---
    desc_div = soup.find("div", class_="properties-description")
    if desc_div:
        p_desc = desc_div.find("p")
        if p_desc:
            description_content = p_desc.get_text(strip=True)
    
    # --- Extract Images ---
    slider = soup.find("div", class_="properties-detail-slider")
    if slider:
        img_tags = slider.find_all("img")
        for img in img_tags:
            src = img.get("src", "")
            if src:
                if src.startswith("/"):
                    src = "https://www.essekna.com" + src
                images_list.append(src)
        images_list = list(dict.fromkeys(images_list))
    
    superficie_val = ImmobilierUtils.parse_float_or_none(superficie_text)
    prix_dec = ImmobilierUtils.parse_float_or_none(re.sub(r"[^\d.,]", "", price_text)) if price_text else 0
    
    numero_full = url.rstrip("/").split("/")[-1]
    numero = numero_full
    
    now_iso = datetime.now().isoformat()
    
    property_details = {
        "titre": titre,
        "url": url,
        "site_origine": "Essekna.com",
        "date_crawl": now_iso,
        "numero": numero,
        "date_depot": date_depot,
        "transaction": transaction,
        "category": "immobilier",
        "bien": ImmobilierUtils.convert_property_type(titre) if titre else "",
        "superficie": superficie_val,
        "superficie_unit": "m²",
        "no_pieces": no_pieces,
        "description": description_content,
        "prix": price_text,
        "prix_dec": prix_dec,
        "prix_unit": "DA" if price_text else "",
        "images": images_list,
        "adresse": f"{commune}, {wilaya}" if commune and wilaya else "",
        "wilaya": wilaya,
        "commune": commune,
        "etage": etage,
        "status": 200,
        "date_verif": now_iso,
        "as_photo": "Avec photo" if images_list else "Sans photo",
        "as_prix": "Avec prix" if price_text else "Sans prix"
    }
    
    print("Extracted property details:", property_details)
    insert_data_to_es(property_details, "immobilier")
    return property_details
