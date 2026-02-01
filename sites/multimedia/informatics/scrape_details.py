# scrape_details.py - Unified Informatics detail scraper (Desktop PCs & Laptops)
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
from utils.multimedia import MultimediaUtils

try:
    sys.path.insert(1, '../../../insert2db')
    from insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] Inserting data to ES index '{index}'")


async def scrape_product_details(url, category_name="laptops"):
    """
    Scrape detailed product information from Informatics product page.
    Works for both Desktop PCs and Laptops.
    """
    print(f"Scraping product details from: {url} (Category: {category_name})")
    
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
        title_elem = soup.select_one('h1.product_title') or soup.select_one('h1.product-title') or soup.select_one('h1')
        titre = title_elem.text.strip() if title_elem else ""
        
        # Extract price
        price_elem = soup.select_one('span.woocommerce-Price-amount.amount') or \
                     soup.select_one('p.price span.amount') or \
                     soup.select_one('.price')
        prix_text = price_elem.text.strip() if price_elem else ""
        prix_dec = MultimediaUtils.str_to_float(prix_text.replace("DA", "").replace("DZD", "").replace("د.ج", ""))
        
        # Extract description
        desc_elem = soup.select_one('div.woocommerce-product-details__short-description') or \
                    soup.select_one('div.product-short-description') or \
                    soup.select_one('div.product-description')
        description = desc_elem.text.strip() if desc_elem else ""
        
        # Extract full description if short description is empty
        if not description:
            full_desc = soup.select_one('div#tab-description') or soup.select_one('div.description')
            description = full_desc.text.strip() if full_desc else ""
        
        # Extract images
        images_list = []
        
        # Try product gallery
        image_gallery = soup.select('div.woocommerce-product-gallery__image img') or \
                       soup.select('div.product-images img')
        for img in image_gallery:
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if src and 'placeholder' not in src.lower():
                images_list.append(src)
        
        # Fallback to main product image
        if not images_list:
            main_img = soup.select_one('img.wp-post-image') or soup.select_one('img.product-image')
            if main_img:
                src = main_img.get('src') or main_img.get('data-src')
                if src:
                    images_list.append(src)
        
        # Extract brand and model using MultimediaUtils
        brand = MultimediaUtils.extract_brand(titre) or MultimediaUtils.extract_brand(description)
        model = MultimediaUtils.extract_model(titre) or MultimediaUtils.extract_model(description)
        
        # Extract technical specifications
        os_name, os_version = MultimediaUtils.extract_os(description)
        ram, ram_unit = MultimediaUtils.extract_ram(description)
        storage, storage_unit = MultimediaUtils.extract_storage(description)
        processor = MultimediaUtils.extract_processor(description)
        screen_size = MultimediaUtils.extract_screen_size(description)
        garantie, garantie_unit = MultimediaUtils.extract_warranty(description)
        
        # Try to extract from specification table
        spec_table = soup.select_one('table.woocommerce-product-attributes') or \
                     soup.select_one('table.shop_attributes') or \
                     soup.select_one('table.additional-information')
        
        dimensions = ""
        poid = ""
        poid_unit = ""
        couleur = ""
        
        if spec_table:
            rows = spec_table.select('tr')
            for row in rows:
                label = row.select_one('th') or row.select_one('td.label')
                value = row.select_one('td') or row.select_one('td.value')
                
                if label and value:
                    label_text = label.text.strip().lower()
                    value_text = value.text.strip()
                    
                    # OS
                    if 'système' in label_text or 'os' in label_text or 'operating system' in label_text:
                        extracted_os, extracted_version = MultimediaUtils.extract_os(value_text)
                        if extracted_os:
                            os_name = extracted_os
                            os_version = extracted_version
                    
                    # RAM
                    if 'ram' in label_text or 'mémoire' in label_text:
                        extracted_ram, extracted_unit = MultimediaUtils.extract_ram(value_text)
                        if extracted_ram:
                            ram = extracted_ram
                            ram_unit = extracted_unit
                    
                    # Storage
                    if 'stockage' in label_text or 'disque' in label_text or 'storage' in label_text or 'ssd' in label_text or 'hdd' in label_text:
                        extracted_storage, extracted_unit = MultimediaUtils.extract_storage(value_text)
                        if extracted_storage:
                            storage = extracted_storage
                            storage_unit = extracted_unit
                    
                    # Processor
                    if 'processeur' in label_text or 'processor' in label_text or 'cpu' in label_text:
                        extracted_processor = MultimediaUtils.extract_processor(value_text)
                        if extracted_processor:
                            processor = extracted_processor
                    
                    # Screen
                    if 'écran' in label_text or 'screen' in label_text or 'taille' in label_text:
                        extracted_screen = MultimediaUtils.extract_screen_size(value_text)
                        if extracted_screen:
                            screen_size = extracted_screen
                    
                    # Dimensions
                    if 'dimension' in label_text:
                        dimensions = value_text
                    
                    # Weight
                    if 'poids' in label_text or 'weight' in label_text:
                        poid_match = re.search(r'([\d\.]+)\s*(kg|g)', value_text, re.IGNORECASE)
                        if poid_match:
                            poid = poid_match.group(1)
                            poid_unit = poid_match.group(2)
                    
                    # Color
                    if 'couleur' in label_text or 'color' in label_text:
                        couleur = value_text
                    
                    # Warranty
                    if 'garantie' in label_text or 'warranty' in label_text:
                        extracted_garantie, extracted_unit = MultimediaUtils.extract_warranty(value_text)
                        if extracted_garantie:
                            garantie = extracted_garantie
                            garantie_unit = extracted_unit
        
        # Determine category
        categorie = "Laptops" if "laptop" in category_name or "portable" in titre.lower() else "Desktop PCs"
        
        # Build product data
        product_data = {
            'titre': titre,
            'url': url,
            'etat': MultimediaUtils.normalize_etat(titre, description),
            'livraison': "48 Wilayas",
            'site_origine': "Informatics.dz",
            'transaction': "Vente",
            'category': "multimedia",
            'categorie': categorie,
            'description': description,
            'date_depot': datetime.now().isoformat(),
            'marque': brand,
            'modele': model,
            'garantie': garantie,
            'garantie_unit': garantie_unit,
            'dimension': dimensions,
            'taille_ecran': screen_size,
            'type_ecran': "",
            'os': os_name,
            'os_version': os_version,
            'poid': poid,
            'poid_unit': poid_unit,
            'couleur': couleur,
            'ram': ram,
            'ram_unit': ram_unit,
            'processor_cores': processor,
            'processor_hz': "",
            'm_interne': storage,
            'm_interne_unit': storage_unit,
            'camera_ar': "",
            'camera_av': "",
            'batterie': MultimediaUtils.extract_battery(description),
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
