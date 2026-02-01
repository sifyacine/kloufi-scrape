from datetime import datetime, timedelta
from threading import Thread
import re
import locale
import json
import asyncio
import sys
import os
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from urllib.parse import unquote, urljoin

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from utils.multimedia import MultimediaUtils

try:
    sys.path.insert(1, '../../../insert2db')
    from insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] Inserting data to ES index '{index}'")


def extract_dimensions(text):
    """Extracts dimensions from text format"""
    pattern = r"(\d{2,4})\s*[×xX]\s*(\d{2,4})\s*[×xX]\s*(\d{2,4})"
    match = re.search(pattern, text)
    if match:
        largeur, hauteur, profondeur = match.groups()
        return f"{largeur} x {hauteur} x {profondeur} cm"
    return ""


async def scrape_product_details(url, item):
    """Extract product details from Homecenterdz page"""
    print("Extracting product details from:", url)
    browser_config = BrowserConfig(
        headless=True,
        verbose=True,
        browser_type="chromium",
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=url,
            javascript_enabled=True,
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                delay_before_return_html=5
            ),
        )

        if not result.success:
            raise Exception("Failed to crawl the page")

        soup = BeautifulSoup(result.html, 'html.parser')
        
        # Extract description
        description = soup.find('div', class_='product-description').text.strip() if soup.find('div', class_='product-description') else ""
        
        # Extract specs using MultimediaUtils
        os_name, os_version = MultimediaUtils.extract_os(result.html)
        ram, ram_unit = MultimediaUtils.extract_ram(result.html)
        garantie, garantie_unit = MultimediaUtils.extract_warranty(result.html)
        
        # Extract images
        images_list = []
        if item.get('image'):
            images_list.append(item['image'])
        
        # Extract brand
        marque = re.search(r'<div class="marque">.*?<img[^>]+alt="([^"]+)"', result.html, re.DOTALL)
        brand = marque.group(1).capitalize() if marque and marque.group(1) else MultimediaUtils.extract_brand(item.get('title', ''))
        
        # Extract screen size
        screen_size_match = re.search(r"(\d{2,3})''", result.html)
        screen_size = screen_size_match.group(1) if screen_size_match else ""
        
        # Extract price
        price_match = re.search(r"Prix:\s*([\d.,]+)\s*DA", result.html)
        price = price_match.group(1) if price_match else ""
        prix_dec = MultimediaUtils.str_to_float(item.get('price', '')) if item.get('price') else 0.0
        
        # Extract dimensions
        dimensions_match = re.search(r"(\d{2,4})\s*[×xX]\s*(\d{2,4})\s*[×xX]\s*(\d{2,4})", result.html)
        dimensions = extract_dimensions(dimensions_match.group(0)) if dimensions_match else ""
        
        # Extract model reference
        modele_match = re.search(r"Reference:\s*([A-Z0-9-]+)", result.html)
        modele = modele_match.group(1) if modele_match else MultimediaUtils.extract_model(item.get('title', ''))
        
        # Extract color
        color_match = re.search(r"Couleur\s*[:\-]?\s*(\w+)", result.html)
        couleur = color_match.group(1) if color_match else ""

        item_details = {
            'titre': item.get('title', ''),
            'url': url,
            'etat': MultimediaUtils.normalize_etat(item.get('title', ''), description),
            'livraison': "48 Wilayas",
            'site_origine': "Homecenterdz.com",
            'transaction': "Vente",
            'category': "multimedia",
            'categorie': MultimediaUtils.normalize_categorie(item.get('category', '')),
            'description': description,
            'date_depot': datetime.now().isoformat(),
            'marque': brand,
            'modele': modele,
            'garantie': garantie,
            'garantie_unit': garantie_unit,
            'dimension': dimensions,
            'taille_ecran': MultimediaUtils.str_to_float(screen_size),
            'os': os_name,
            'os_version': os_version,
            'poid': "",
            'couleur': couleur,
            'poid_unit': "",
            'ram': ram,
            'ram_unit': ram_unit,
            'prix_dec': prix_dec,
            'prix_unit': "DA",
            'images': images_list,
            'adresse': "Toute l'Algérie",
            'status': 200,
            'date_crawl': datetime.now().isoformat(),
            'date_verif': datetime.now().isoformat(),
            'as_photo': MultimediaUtils.avec_sans_photo(images_list),
            'as_prix': MultimediaUtils.avec_sans_prix(str(prix_dec), "DA"),
            'type_ecran': "",
            'processor_cores': MultimediaUtils.extract_processor(result.html),
            'processor_hz': "",
            'm_interne': "",
            'm_interne_unit': "",
            'camera_ar': "",
            'camera_av': "",
            'batterie': MultimediaUtils.extract_battery(result.html),
        }

        print(json.dumps(item_details, indent=4))
        insert_data_to_es(item_details, "multimedia")
