# scrape_details.py - Jumia electromenager scraper with ElectromenagerUtils
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


async def extract_multimedia_details(url, item):
    """Extract electromenager details from Jumia page"""
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
        
        # Extract images
        images_list = []
        images_element = soup.find("div", class_='-ptxs -pbs')
        if images_element:
            images = images_element.find_all('img')
            for image in images:
                src = image.get('src')
                if src:
                    src_start = src.split("/filters")[0]
                    if src_start == "https://dz.jumia.is/unsafe/fit-in/500x500" and src not in images_list:
                        images_list.append(src)
        
        # Extract description
        description_elem = soup.find("div", class_='markup -mhm -pvl -oxa -sc')
        description = description_elem.text if description_elem else ""
        
        # Extract category
        categorie_element = soup.select_one('#jm > main > div:nth-child(2) > div:nth-child(1) > a:nth-child(3)')
        categorie_text = categorie_element.text.strip() if categorie_element else ""
        categorie = ElectromenagerUtils.normalize_categorie(categorie_text)
        
        # Extract technical details
        descriptif_technique_section = soup.find("h2", string="Descriptif technique")
        item_details_technique = {}
        if descriptif_technique_section:
            descriptif_ul = descriptif_technique_section.find_next("ul")
            if descriptif_ul:
                li_elements = descriptif_ul.find_all("li", class_="-pvxs")
                for li in li_elements:
                    span = li.find("span", class_="-b")
                    if span:
                        key = span.text.strip()
                        value = li.text.split(":")[-1].strip()
                        item_details_technique[key] = value
        
        # Extract brand and model
        brand = ElectromenagerUtils.extract_brand(item.get('title', ''))
        if not brand:
            brand_match = re.search(r'Produits similaires par (\w+\s?\w+?)</', result.html)
            brand = brand_match.group(1) if brand_match else ""
        
        model = ElectromenagerUtils.extract_model(item.get('title', ''))
        if not model:
            model_match = re.search(r'<span class="-b">Modèle</span>:?\s?(\w+\s?\w+?)</li>', result.html)
            model = model_match.group(1) if model_match else ""
        
        # Extract specifications using ElectromenagerUtils
        garantie, garantie_unit = ElectromenagerUtils.extract_warranty(result.html)
        capacite, capacite_unit = ElectromenagerUtils.extract_capacity(result.html)
        classe_energie = ElectromenagerUtils.extract_energy_class(result.html)
        puissance, puissance_unit = ElectromenagerUtils.extract_power(result.html)
        dimensions = ElectromenagerUtils.extract_dimensions(result.html)
        poid, poid_unit = ElectromenagerUtils.extract_weight(result.html)
        couleur = ElectromenagerUtils.extract_color(result.html)
        
        # Fallback for specific fields
        if not dimensions and item_details_technique.get("Taille (Longueur x Largeur x Hauteur cm)"):
            dimensions = item_details_technique["Taille (Longueur x Largeur x Hauteur cm)"]
        
        if not poid and item_details_technique.get("Poids (kg)"):
            poid = item_details_technique["Poids (kg)"]
            poid_unit = "kg"
        
        if not couleur and item_details_technique.get("Couleur"):
            couleur = item_details_technique["Couleur"]
        
        # Process price
        price_text = item.get('price', '')
        prix_dec = ElectromenagerUtils.str_to_float(price_text.replace(" DA", "").replace(",", ""))

        item_details = {
            'titre': item.get('title', ''),
            'url': url,
            'etat': ElectromenagerUtils.normalize_etat(item.get('title', ''), description),
            'livraison': "48 Wilayas",
            'site_origine': "Jumia.dz",
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