# scrape_details.py - Starmania scraper with MultimediaUtils
import asyncio
import json
import re
import sys
import os
from datetime import datetime
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from utils.multimedia import MultimediaUtils

try:
    from insert2db.insert_scrape import insert_data_to_es
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
    """Extract product details from Starmania page"""
    print(f"Extracting product details from: {url}")
    
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
        
        # Extract title
        title_elem = soup.select_one('div.product-info h2') or soup.select_one('h1')
        titre = title_elem.text.strip() if title_elem else item.get('title', '')
        
        # Extract description
        description_elem = soup.select_one('div.markup -mhm -pvl -oxa -sc') or soup.select_one('div.product-description')
        description = description_elem.text.strip() if description_elem else ""
        
        # Extract images
        images_list = []
        if item.get('image') and item['image'] != "/static/images/pas-images.png":
            image_url = f"https://www.starmania.dz{item['image']}" if not item['image'].startswith('http') else item['image']
            images_list.append(image_url)
        
        # Extract technical specifications
        poids_elem = soup.find("th", string="Poids Net:")
        poid = ""
        poid_unit = ""
        if poids_elem:
            poids_text = poids_elem.find_next("td").text.strip()
            poid_match = re.search(r"([\d\.]+)\s*(Kg|g|mg|lb)", poids_text, re.IGNORECASE)
            if poid_match:
                poid = poid_match.group(1).replace(",", ".")
                poid_unit = poid_match.group(2)
        
        # Extract dimensions
        dimensions_elem = soup.find("th", string="Dimensions (H / L / P) (mm):")
        dimensions = ""
        if dimensions_elem:
            dimensions_text = dimensions_elem.find_next("td").text.strip()
            dimensions = extract_dimensions(dimensions_text)
        
        # Fallback dimensions extraction
        if not dimensions:
            dimensions_match = re.search(r"(\d{2,4})\s*[×xX]\s*(\d{2,4})\s*[×xX]\s*(\d{2,4})", result.html)
            dimensions = extract_dimensions(dimensions_match.group(0)) if dimensions_match else ""
        
        # Extract color
        color_elem = soup.find("th", string="Couleur:")
        couleur = color_elem.find_next("td").text.strip() if color_elem else ""
        
        # Extract screen size
        screen_size = MultimediaUtils.extract_screen_size(result.html)
        
        # Extract model reference
        modele_elem = soup.select_one('span.product-details-ref')
        modele = modele_elem.text.strip() if modele_elem else MultimediaUtils.extract_model(titre)
        
        # Extract brand
        brand = item.get('brand', '') or MultimediaUtils.extract_brand(titre)
        
        # Extract battery
        battery = MultimediaUtils.extract_battery(result.html)
        
        # Process price
        price_text = item.get('price', '')
        prix_dec = MultimediaUtils.str_to_float(price_text.replace(" DA", "").replace(",", "").replace("\xa0", ""))
        
        # Determine category
        categorie = MultimediaUtils.normalize_categorie(item.get('category', ''))

        item_details = {
            'titre': titre,
            'url': url,
            'etat': MultimediaUtils.normalize_etat(titre, description),
            'livraison': "48 Wilayas",
            'site_origine': "Starmania.dz",
            'transaction': "Vente",
            'category': "multimedia",
            'categorie': categorie,
            'description': description,
            'date_depot': datetime.now().isoformat(),
            'marque': brand,
            'modele': modele,
            'garantie': "",
            'garantie_unit': "",
            'dimension': dimensions,
            'type_ecran': "",
            'taille_ecran': screen_size,
            'os': "",
            'os_version': "",
            'poid': poid,
            'poid_unit': poid_unit,
            'couleur': couleur,
            'processor_cores': "",
            'processor_hz': "",
            'm_interne': "",
            'm_interne_unit': "",
            'ram': "",
            'ram_unit': "",
            'camera_ar': "",
            'camera_av': "",
            'batterie': battery,
            'prix': price_text,
            'prix_dec': prix_dec,
            'prix_unit': "DA",
            'images': images_list,
            'adresse': "Toute l'Algérie",
            'status': 200,
            'date_crawl': datetime.now().isoformat(),
            'date_verif': datetime.now().isoformat(),
            'as_photo': MultimediaUtils.avec_sans_photo(images_list),
            'as_prix': MultimediaUtils.avec_sans_prix(str(prix_dec), "DA"),
        }

        print(json.dumps(item_details, indent=4, ensure_ascii=False))
        insert_data_to_es(item_details, "multimedia")
        
        return item_details
