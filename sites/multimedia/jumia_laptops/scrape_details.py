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


async def extract_multimedia_details(url, item):
    """Extract laptop details from Jumia page"""
    print("Extracting laptop details from:", url)
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
                delay_before_return_html=3
            ),
        )

        if not result.success:
            raise Exception("Failed to crawl the page")

        soup = BeautifulSoup(result.html, 'html.parser')
        
        # Extract images
        images_element = soup.find("div", class_='-ptxs -pbs')
        images_list = []
        if images_element:
            images = images_element.find_all('img')
            for image in images:
                src = image.get('src')
                if src:
                    src_start = src.split("/filters")[0]
                    if src_start == "https://dz.jumia.is/unsafe/fit-in/500x500" and src not in images_list:
                        images_list.append(src)
        
        # Extract description
        description = soup.find("div", class_='markup -mhm -pvl -oxa -sc').text if soup.find("div", class_='markup -mhm -pvl -oxa -sc') else ""
        
        # Extract technical details
        descriptif_technique_section = soup.find("h2", string="Descriptif technique").find_next("ul") if soup.find("h2", string="Descriptif technique") else None
        item_details_technique = {}
        
        if descriptif_technique_section:
            li_elements = descriptif_technique_section.find_all("li", class_="-pvxs")
            for li in li_elements:
                span = li.find("span", class_="-b")
                if span:
                    key = span.text.strip()
                    value = li.text.split(":")[-1].strip()
                    item_details_technique[key] = value
        
        # Extract category
        categorie_element = soup.find("div", class_="brcbs col16 -pts -pbm")
        categorie_text = categorie_element.find_all("a")[2].text if categorie_element and len(categorie_element.find_all("a")) > 2 else ""
        
        # Extract specs using MultimediaUtils
        os_name, os_version = MultimediaUtils.extract_os(result.html)
        ram, ram_unit = MultimediaUtils.extract_ram(result.html)
        m_interne, m_interne_unit = MultimediaUtils.extract_storage(result.html)
        garantie, garantie_unit = MultimediaUtils.extract_warranty(result.html)
        processor = MultimediaUtils.extract_processor(result.html)
        
        # Extract brand and model
        brand = MultimediaUtils.extract_brand(item.get('title', '')) or \
                (re.search(r'Produits similaires par (\w+\s?\w+?)</', result.html).group(1) if re.search(r'Produits similaires par (\w+\s?\w+?)</', result.html) else "")
        
        model = MultimediaUtils.extract_model(item.get('title', '')) or \
                (re.search(r'<span class="-b">Modèle</span>:?\s?(\w+\s?\w+?)</li>', result.html).group(1) if re.search(r'<span class="-b">Modèle</span>:?\s?(\w+\s?\w+?)</li>', result.html) else "")
        
        # Process dimensions
        dimensions_from_item = item_details_technique.get("Taille (Longueur x Largeur x Hauteur cm)", "")
        dimensions = dimensions_from_item if dimensions_from_item else ""
        
        # Process price
        price_text = item.get("price", "")
        if price_text and "-" in price_text:
            price_text = price_text.split("-")[0].strip()
        prix_dec = MultimediaUtils.str_to_float(price_text.replace(" DA", "")) if price_text else 0.0

        item_details = {
            'titre': item.get('title', ''),
            'url': url,
            'etat': MultimediaUtils.normalize_etat(item.get('title', ''), description),
            'livraison': "48 Wilayas",
            'site_origine': "Jumia.dz",
            'transaction': "Vente",
            'category': "multimedia",
            'categorie': "Laptops",
            'description': description,
            'date_depot': datetime.now().isoformat(),
            'marque': brand,
            'modele': model,
            'garantie': garantie,
            'garantie_unit': garantie_unit,
            'dimension': dimensions,
            'taille_ecran': MultimediaUtils.str_to_float(item_details_technique.get("Taille de l'écran (pouces)", "")),
            'os': os_name,
            'os_version': os_version,
            'poid': item_details_technique.get("Poids (kg)", ""),
            'couleur': item_details_technique.get("Couleur", ""),
            'poid_unit': "kg" if item_details_technique.get("Poids (kg)") else "",
            'ram': ram,
            'ram_unit': ram_unit,
            'processor_cores': processor,
            'processor_hz': "",
            'm_interne': m_interne,
            'm_interne_unit': m_interne_unit,
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
            'camera_ar': "",
            'camera_av': "",
            'batterie': MultimediaUtils.extract_battery(result.html),
        }

        print(json.dumps(item_details, indent=4))
        insert_data_to_es(item_details, "multimedia")
