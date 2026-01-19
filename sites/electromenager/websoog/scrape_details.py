# scrape_details.py - Websoog electromenager scraper with ElectromenagerUtils
import asyncio
import json
import re
import sys
import os
from datetime import datetime
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from utils.electromenager import ElectromenagerUtils

try:
    sys.path.insert(1, '../../global')
    from insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] Inserting data to ES index '{index}'")


async def extract_multimedia_details(url, item):
    """Extract electromenager details from Websoog page"""
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
        images = soup.find_all('a', class_='thumb js-thumb')
        if len(images) == 0:
            cover = soup.find('div', class_='product-cover sm-bottom')
            if cover:
                imgs = cover.find_all('img')
                images_list = [img['src'] for img in imgs if img.get('src')]
        else:
            for image in images:
                if image.get('data-image'):
                    images_list.append(image['data-image'])
        
        # Extract brand and model
        brand = ElectromenagerUtils.extract_brand(item.get('title', ''))
        model = ElectromenagerUtils.extract_model(item.get('title', ''))
        
        # Extract specifications using ElectromenagerUtils
        garantie, garantie_unit = ElectromenagerUtils.extract_warranty(result.html)
        capacite, capacite_unit = ElectromenagerUtils.extract_capacity(result.html)
        classe_energie = ElectromenagerUtils.extract_energy_class(result.html)
        puissance, puissance_unit = ElectromenagerUtils.extract_power(result.html)
        poid, poid_unit = ElectromenagerUtils.extract_weight(result.html)
        couleur = ElectromenagerUtils.extract_color(result.html)
        dimensions = ElectromenagerUtils.extract_dimensions(result.html)
        
        # Process price
        prix_dec = ElectromenagerUtils.process_price(item.get('price', '')) if item.get('price') else 0.0
        
        # Determine category
        categorie = ElectromenagerUtils.normalize_categorie(item.get('category', ''))

        item_details = {
            'titre': item.get('title', ''),
            'url': url,
            'etat': ElectromenagerUtils.normalize_etat(item.get('title', ''), description),
            'livraison': "48 Wilayas",
            'site_origine': "Websoog.com",
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