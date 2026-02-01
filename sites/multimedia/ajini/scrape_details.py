# scrape_details.py - Ajini TV detail scraper
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


async def scrape_product_details(url):
    """Scrape detailed product information from Ajini product page"""
    print(f"Scraping product details from: {url}")
    
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        text_mode=False,
        verbose=True
    )
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=url,
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                delay_before_return_html=5
            )
        )
        
        if not result.success:
            print(f"Failed to scrape product page: {result.error_message}")
            return
        
        soup = BeautifulSoup(result.html, 'html.parser')
        
        # Extract title
        title_elem = soup.select_one('h1.product_title') or soup.select_one('h1')
        titre = title_elem.text.strip() if title_elem else ""
        
        # Extract price
        price_elem = soup.select_one('span.woocommerce-Price-amount.amount') or soup.select_one('.price')
        prix_text = price_elem.text.strip() if price_elem else ""
        prix_dec = MultimediaUtils.str_to_float(prix_text.replace("DA", "").replace("DZD", ""))
        
        # Extract description
        desc_elem = soup.select_one('div.woocommerce-product-details__short-description') or soup.select_one('div.product-description')
        description = desc_elem.text.strip() if desc_elem else ""
        
        # Extract images
        images_list = []
        image_gallery = soup.select('div.woocommerce-product-gallery__image img')
        for img in image_gallery:
            src = img.get('src') or img.get('data-src')
            if src and 'placeholder' not in src.lower():
                images_list.append(src)
        
        # If no gallery images, try main product image
        if not images_list:
            main_img = soup.select_one('img.wp-post-image')
            if main_img:
                src = main_img.get('src') or main_img.get('data-src')
                if src:
                    images_list.append(src)
        
        # Extract brand and model
        brand = MultimediaUtils.extract_brand(titre) or MultimediaUtils.extract_brand(description)
        model = MultimediaUtils.extract_model(titre) or MultimediaUtils.extract_model(description)
        
        # Extract technical specifications
        spec_table = soup.select_one('table.woocommerce-product-attributes') or soup.select_one('table.shop_attributes')
        
        screen_size = ""
        screen_type = ""
        garantie = ""
        garantie_unit = ""
        dimensions = ""
        poid = ""
        poid_unit = ""
        
        if spec_table:
            rows = spec_table.select('tr')
            for row in rows:
                label = row.select_one('th')
                value = row.select_one('td')
                
                if label and value:
                    label_text = label.text.strip().lower()
                    value_text = value.text.strip()
                    
                    if 'taille' in label_text or 'écran' in label_text or 'screen' in label_text:
                        screen_size = MultimediaUtils.extract_screen_size(value_text)
                        # Also extract screen type if mentioned
                        if any(t in value_text.upper() for t in ['QLED', 'OLED', 'LED', 'LCD', 'HD', 'UHD', '4K']):
                            screen_type = value_text
                    
                    if 'garantie' in label_text or 'warranty' in label_text:
                        garantie, garantie_unit = MultimediaUtils.extract_warranty(value_text)
                    
                    if 'dimension' in label_text:
                        dimensions = value_text
                    
                    if 'poids' in label_text or 'weight' in label_text:
                        poid_match = re.search(r'([\d\.]+)\s*(kg|g)', value_text, re.IGNORECASE)
                        if poid_match:
                            poid = poid_match.group(1)
                            poid_unit = poid_match.group(2)
        
        # Fallback: extract from description
        if not screen_size:
            screen_size = MultimediaUtils.extract_screen_size(description)
        if not garantie:
            garantie, garantie_unit = MultimediaUtils.extract_warranty(description)
        
        # Build product data
        product_data = {
            'titre': titre,
            'url': url,
            'etat': MultimediaUtils.normalize_etat(titre, description),
            'livraison': "48 Wilayas",
            'site_origine': "Ajini.com",
            'transaction': "Vente",
            'category': "multimedia",
            'categorie': "Téléviseurs",
            'description': description,
            'date_depot': datetime.now().isoformat(),
            'marque': brand,
            'modele': model,
            'garantie': garantie,
            'garantie_unit': garantie_unit,
            'dimension': dimensions,
            'taille_ecran': screen_size,
            'type_ecran': screen_type,
            'os': "",
            'os_version': "",
            'poid': poid,
            'poid_unit': poid_unit,
            'couleur': "",
            'ram': "",
            'ram_unit': "",
            'processor_cores': "",
            'processor_hz': "",
            'm_interne': "",
            'm_interne_unit': "",
            'camera_ar': "",
            'camera_av': "",
            'batterie': "",
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
        
        print(json.dumps(product_data, indent=2, ensure_ascii=False))
        insert_data_to_es(product_data, "multimedia")
        
        return product_data
