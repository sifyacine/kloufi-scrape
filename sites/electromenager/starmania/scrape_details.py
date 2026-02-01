# scrape_details.py - Starmania electromenager scraper with ElectromenagerUtils
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
    """Extract electromenager details from Starmania page"""
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
        title_elem = soup.select_one('div.product-info h2')
        title = title_elem.text.strip() if title_elem else ""
        
        # Extract description
        description_elem = soup.select_one('div.markup -mhm -pvl -oxa -sc')
        description = description_elem.text.strip() if description_elem else ""
        
        # Extract images
        images_list = []
        if item.get('image') and item['image'] != "/static/images/pas-images.png":
            image_url = f"https://www.starmania.dz{item['image']}" if not item['image'].startswith('http') else item['image']
            images_list.append(image_url)
        
        # Extract weight
        poid = ""
        poid_unit = ""
        poids_elem = soup.find("th", string="Poids Net:")
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
            dimensions = ElectromenagerUtils.extract_dimensions(dimensions_text)
        
        # Extract color
        color_elem = soup.find("th", string="Couleur:")
        couleur = color_elem.find_next("td").text.strip() if color_elem else ""
        
        # Extract model
        modele_elem = soup.select_one('span.product-details-ref')
        modele = modele_elem.text.strip() if modele_elem else ""
        
        # Extract brand
        brand = item.get('brand', '') or ElectromenagerUtils.extract_brand(title)
        
        # Extract specifications using ElectromenagerUtils
        capacite, capacite_unit = ElectromenagerUtils.extract_capacity(result.html)
        classe_energie = ElectromenagerUtils.extract_energy_class(result.html)
        puissance, puissance_unit = ElectromenagerUtils.extract_power(result.html)
        garantie, garantie_unit = ElectromenagerUtils.extract_warranty(result.html)
        
        # Process price
        price_text = item.get('price', '')
        prix_dec = ElectromenagerUtils.str_to_float(price_text.replace(" DA", "").replace(",", "").replace("\xa0", ""))
        
        # Determine category
        categorie = ElectromenagerUtils.normalize_categorie(item.get('category', ''))

        item_details = {
            'titre': title,
            'url': url,
            'etat': ElectromenagerUtils.normalize_etat(title, description),
            'livraison': "48 Wilayas",
            'site_origine': "Starmania.dz",
            'transaction': "Vente",
            'category': "electromenager",
            'categorie': categorie,
            'description': description,
            'date_depot': datetime.now().isoformat(),
            'marque': brand,
            'modele': modele,
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
            'prix': price_text,
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
