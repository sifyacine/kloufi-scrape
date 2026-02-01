# scrape_details.py - Homecenterdz electromenager scraper with ElectromenagerUtils
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
from utils.electromenager import ElectromenagerUtils

try:
    from insert2db.insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] Inserting data to ES index '{index}'")


async def scrape_product_details(url, item):
    """Extract electromenager details from Homecenterdz page"""
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
        
        # Extract description
        description_elem = soup.find('div', class_='product-description')
        description = description_elem.text.strip() if description_elem else ""
        
        # Extract images
        images_list = []
        if item.get('image'):
            images_list.append(item['image'])
        
        # Extract brand using ElectromenagerUtils
        brand = ElectromenagerUtils.extract_brand(item.get('title', ''))
        
        # Fallback brand extraction from HTML
        if not brand:
            marque_match = re.search(r'<div class="marque"><div class="img_container"><img src="images/marques/\d+-[\w\s\(\)]+\.png" alt="([\w\s\(\)]+)">', result.html)
            if marque_match:
                brand = marque_match.group(1)
        
        # Extract model
        model = ElectromenagerUtils.extract_model(item.get('title', ''))
        
        # Extract specifications using ElectromenagerUtils
        garantie, garantie_unit = ElectromenagerUtils.extract_warranty(result.html)
        capacite, capacite_unit = ElectromenagerUtils.extract_capacity(result.html)
        classe_energie = ElectromenagerUtils.extract_energy_class(result.html)
        puissance, puissance_unit = ElectromenagerUtils.extract_power(result.html)
        dimensions = ElectromenagerUtils.extract_dimensions(result.html)
        poid, poid_unit = ElectromenagerUtils.extract_weight(result.html)
        couleur = ElectromenagerUtils.extract_color(result.html)
        
        # Fallback color extraction
        if not couleur:
            couleur_match = re.search(r"Couleur\s*[:\-]?\s*(\w+)", result.html)
            couleur = couleur_match.group(1) if couleur_match else ""
        
        # Process price
        prix_dec = ElectromenagerUtils.process_price(item.get('price', '')) if item.get('price') else 0.0
        
        # Determine category
        categorie = ElectromenagerUtils.normalize_categorie(item.get('category', ''))

        item_details = {
            'titre': item.get('title', ''),
            'url': url,
            'etat': ElectromenagerUtils.normalize_etat(item.get('title', ''), description),
            'livraison': "48 Wilayas",
            'site_origine': "Homecenterdz.com",
            'transaction': "Vente",
            'category': "electromenager",
            'categorie': categorie,
            'description': description,
            'date_depot': datetime.now().isoformat(),
            'marque': brand,
            'modele': model,
            'garantie': garantie,
            'garantie_unit': garantie_unit,
            'dimension': dimensions,
            'poid': poid,
            'poid_unit': poid_unit,
            'couleur': couleur,
            'capacite': capacite,
            'capacite_unit': capacite_unit,
            'classe_energie': classe_energie,
            'puissance': puissance,
            'puissance_unit': puissance_unit,
            'prix_dec': prix_dec,
            'prix_unit': "DA",
            'images': images_list,
            'adresse': "Toute l'Algérie",
            'status': 200,
            'date_crawl': datetime.now().isoformat(),
            'date_verif': datetime.now().isoformat(),
            'as_photo': ElectromenagerUtils.avec_sans_photo(images_list),
            'as_prix': ElectromenagerUtils.avec_sans_prix(str(prix_dec), "DA"),
        }

        print(json.dumps(item_details, indent=4, ensure_ascii=False))
        insert_data_to_es(item_details, "electromenager")
        
        return item_details