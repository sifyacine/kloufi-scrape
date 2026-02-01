import asyncio
from datetime import datetime
from urllib.parse import unquote
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
import sys
import os
import re

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from utils.immobilier import ImmobilierUtils

try:
    from insert2db.insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index_name):
        print(f"[Mock ES] Saved to '{index_name}' → {data.get('titre', 'No title')[:70]}...")

def convert_property_type(raw_key):
    valid_types = {
        "Appartement", "Villa", "Local", "Terrain", "Niveau-de-villa", "Duplex", "Terrain-agricole", 
        "Studio", "Immeuble", "Carcasse", "Autre", "Bungalow", "Chalet", "Salle", "Hotel"
    }

    if not raw_key or not isinstance(raw_key, str):
        return ""

    cleaned = raw_key.strip().lower()
    normalized = cleaned.capitalize()

    if normalized in valid_types:
        return normalized

    if normalized.startswith("F"):
        return "Appartement"

    return ""

async def extract_property_details(url):
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        text_mode=False,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=url,
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                delay_before_return_html=8
            )
        )

    if not result.success:
        raise Exception(f"Failed to load detail page: {result.error_message}")

    soup = BeautifulSoup(result.html, "html.parser")

    # Initialize
    titre = ""
    transaction = ""
    bien = ""
    description_content = ""
    price_text = ""
    price_dec = 0
    price_unit = "DA"
    superficie_val = ""
    superficie_unit = "m²"
    no_pieces = ""
    etage = ""
    images_list = []
    adresse = ""
    wilaya = ""
    commune = ""
    numero = ""
    as_photo = "Sans photo"
    as_prix = "Sans prix"

    now_iso = datetime.now().isoformat()

    # --- Title & Transaction ---
    title_h2 = soup.find("h2", class_="text-base")
    if title_h2:
        titre = title_h2.get_text(" ", strip=True)
        trans_span = title_h2.find("span", class_="text-neutral-400")
        if trans_span:
            trans_text = trans_span.get_text(strip=True)
            transaction = "Location" if trans_text == "À louer" else "Vente"
            bien_text = titre.replace(trans_text, "").strip()
            bien = ImmobilierUtils.convert_property_type(bien_text)

    # --- Address ---
    address_div = soup.find("div", class_="flex items-center gap-1 lg:text-base text-sm capitalize")
    if address_div:
        address_span = address_div.find("span")
        if address_span:
            adresse = address_span.get_text(strip=True)
            parts = [p.strip() for p in adresse.split(",")]
            if len(parts) >= 2:
                commune = parts[0]
                wilaya = parts[1]
            elif len(parts) == 1:
                wilaya = parts[0]

        price_text = ""
        price_dec = 0
        as_prix = "Sans prix"

        price_container = soup.find(
            "div",
            class_="flex justify-between font-semibold"
        )

        if price_container:
            price_div = price_container.select_one("div.font-medium")
            if price_div:
                price_text = price_div.get_text(strip=True)  # "10 000 DZD"

                # Remove ALL non-numeric characters safely
                numeric = re.sub(r"[^\d.]", "", price_text)

                if numeric:
                    price_dec = float(numeric)
                    as_prix = "Avec prix"

    # --- Details (surface, rooms, matricule, étage) ---
    # Target: divs with class "flex items-center justify-between space-x-4 rounded-lg p-4"
    detail_boxes = soup.find_all("div", class_=lambda x: x and "justify-between" in x and "rounded-lg" in x and "p-4" in x)
    
    for box in detail_boxes:
        # Get left side (label with image)
        left_span = box.find("span", class_="flex items-center gap-1")
        # Get right side (value)
        spans = box.find_all("span")
        right_span = spans[-1] if len(spans) > 1 else None
        
        if left_span and right_span:
            img = left_span.find("img")
            alt_text = img.get("alt", "").lower() if img else ""
            value = right_span.get_text(strip=True)
            
            # Match by alt text or label text
            if "chambre" in alt_text or "room" in alt_text:
                no_pieces = value.split()[0]
            elif "étage" in alt_text or "floor" in alt_text:
                etage = value.split()[0]
            elif "surface" in alt_text or "m²" in alt_text:
                superficie_val = value.replace("m²", "").strip()
            elif "matricule" in alt_text:
                numero = value
    
    # Fallback: search for details in other layouts
    if not no_pieces or not etage:
        details_section = soup.find("div", class_="flow-root")
        if details_section:
            detail_items = details_section.find_all("div", class_="flex items-center justify-between")
            for item in detail_items:
                label_span = item.find("span", class_="flex items-center gap-1")
                value_span = item.find_next("span")
                if not label_span or not value_span:
                    continue
                label = label_span.get_text(strip=True).lower()
                value = value_span.get_text(strip=True)

                if "surface" in label and not superficie_val:
                    superficie_val = value.replace("m²", "").strip()
                elif ("chambres" in label or "pièces" in label) and not no_pieces:
                    no_pieces = value.split()[0]
                elif "matricule" in label and not numero:
                    numero = value
                elif "étage" in label and not etage:
                    etage = value.replace("Étage", "").strip()

    # --- Description ---
    desc_h2 = soup.find("h2", string="Description")
    if desc_h2:
        desc_div = desc_h2.find_next("div", class_="text-sm")
        if desc_div:
            description_content = desc_div.get_text(strip=True, separator="\n")

    # --- Images: Improved extraction logic ---
    images_list = []
    seen = set()

    # Method 1: Look for srcset attributes in img tags (most reliable)
    all_imgs = soup.find_all("img")
    for img in all_imgs:
        srcset = img.get("srcset", "")
        src = img.get("src", "")
        
        # Extract from srcset (has multiple sizes)
        if srcset and "/_next/image?url=" in srcset:
            urls = srcset.split(",")
            for url_part in urls:
                if "/_next/image?url=" in url_part:
                    try:
                        encoded_url = url_part.split("url=", 1)[1].split("&", 1)[0].strip()
                        real_url = unquote(encoded_url)
                        if real_url and real_url not in seen and "firebase" in real_url:
                            images_list.append(real_url)
                            seen.add(real_url)
                            break  # Take first size only
                    except (IndexError, Exception):
                        pass
        
        # Fallback: Extract from src attribute
        elif src and "/_next/image?url=" in src:
            try:
                encoded_url = src.split("url=", 1)[1].split("&", 1)[0]
                real_url = unquote(encoded_url)
                if real_url and real_url not in seen and "firebase" in real_url:
                    images_list.append(real_url)
                    seen.add(real_url)
            except (IndexError, Exception):
                pass

    # Method 2: If no images found, search for any img tags in gallery area
    if not images_list:
        gallery = soup.find("div", class_=lambda x: x and "grid" in x and "gap" in x)
        if gallery:
            imgs = gallery.find_all("img")
            for img in imgs:
                srcset = img.get("srcset", "")
                src = img.get("src", "")
                
                if srcset and "firebase" in srcset:
                    try:
                        # Extract last URL from srcset (highest quality)
                        urls = srcset.split(",")
                        last_url = urls[-1].strip() if urls else ""
                        if "/_next/image?url=" in last_url:
                            encoded_url = last_url.split("url=", 1)[1].split("&", 1)[0].strip()
                            real_url = unquote(encoded_url)
                            if real_url not in seen:
                                images_list.append(real_url)
                                seen.add(real_url)
                    except (IndexError, Exception):
                        pass
                
                elif src and "firebase" in src:
                    try:
                        if "/_next/image?url=" in src:
                            encoded_url = src.split("url=", 1)[1].split("&", 1)[0]
                            real_url = unquote(encoded_url)
                            if real_url not in seen:
                                images_list.append(real_url)
                                seen.add(real_url)
                    except (IndexError, Exception):
                        pass

    if images_list:
        as_photo = "Avec photo"

    # --- Fallback numero from URL if not found ---
    if not numero:
        numero = url.rstrip("/").split("-")[-1]

    # Build final dict
    property_details = {
        "titre": titre,
        "url": url,
        "site_origine": "Krello.net",
        "date_crawl": now_iso,
        "numero": "",
        "date_depot": now_iso,
        "transaction": transaction,
        "category": "immobilier",
        "bien": bien,
        "superficie": float(superficie_val) if superficie_val else "",
        "superficie_unit": superficie_unit,
        "no_pieces": no_pieces,
        "description": description_content,
        "prix": price_text,
        "prix_dec": price_dec,
        "prix_unit": price_unit,
        "images": images_list,
        "adresse": adresse,
        "wilaya": wilaya,
        "commune": commune,
        "etage": etage,
        "status": 200,
        "date_verif": now_iso,
        "as_photo": as_photo,
        "as_prix": as_prix
    }

    
    try:
        insert_data_to_es(property_details, index_name="immobilier")
    except Exception as e:
        print(f"[ES] Failed to insert: {e}")

    return property_details