# scrape_details.py - Webstar-electro scraper with MultimediaUtils
import asyncio
import json
import re
import sys
import os
from datetime import datetime
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from urllib.parse import urljoin, parse_qs, urlparse

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from utils.multimedia import MultimediaUtils

try:
    from insert2db.insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] Inserting data to ES index '{index}'")


async def extract_product_details(url):
    """
    Extracts product details from a seller's offer page on Webstar Electro.
    Returns a dictionary with all specified fields.
    """
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
            print(f"Failed to crawl the page: {url}")
            return {}

        soup = BeautifulSoup(result.html, 'html.parser')

        # Extract title
        titre_elem = soup.select_one('h1.structure_content_titre')
        titre = titre_elem.text.strip() if titre_elem else ""
        
        # Extract description
        description_elem = soup.select_one('h3.text-muted')
        description = description_elem.text.strip() if description_elem else ""
        
        # Extract images
        images_list = []
        images = soup.select('div.galerie_photo_2 img.item_image_responsive_')
        images_list = [urljoin("https://webstar-electro.com", img['src']) for img in images if img.get('src')]
        
        # Extract date
        date_elem = soup.select_one('div.text-muted.small i.fa-calendar')
        date_depot = ""
        if date_elem:
            date_text = date_elem.parent.text.strip()
            date_match = re.search(r"\d{4}-\d{2}-\d{2}", date_text)
            date_depot = date_match.group(0) if date_match else ""
        
        # Extract category from URL
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        categorie_value = ""
        
        if 'page' in query_params:
            categorie_value = query_params['page'][0].capitalize()
        else:
            path = parsed_url.path.lower()
            category_map = {
                "appareils-photos": "Appareils Photos",
                "consoles-de-jeux": "Consoles de Jeux",
                "demodulateur": "Demodulateurs",
                "manettes-de-jeux": "Manettes de Jeux",
                "smartwatch": "Smartwatch",
                "tablettes-tactiles": "Tablettes Tactiles",
                "telephones-mobiles": "Smartphones",
                "tv": "Téléviseurs",
                "audio": "Audio",
                "chargeurs": "Chargeurs",
                "memoires": "Memoires",
                "power-bank": "Power Bank"
            }
            for key, value in category_map.items():
                if key in path:
                    categorie_value = value
                    break
        
        categorie_value = MultimediaUtils.normalize_categorie(categorie_value)
        
        # Extract brand and model
        brand = MultimediaUtils.extract_brand(titre) or MultimediaUtils.extract_brand(description)
        model = MultimediaUtils.extract_model(titre) or MultimediaUtils.extract_model(description)
        
        # Extract specs using MultimediaUtils
        os_name, os_version = MultimediaUtils.extract_os(result.html)
        ram, ram_unit = MultimediaUtils.extract_ram(result.html)
        storage, storage_unit = MultimediaUtils.extract_storage(result.html)
        processor = MultimediaUtils.extract_processor(result.html)
        screen_size = MultimediaUtils.extract_screen_size(result.html)
        garantie, garantie_unit = MultimediaUtils.extract_warranty(result.html)
        camera_rear, camera_front = MultimediaUtils.extract_camera(result.html)
        battery = MultimediaUtils.extract_battery(result.html)
        
        # Extract from specification table
        table = soup.select_one('table.table-bordered.table-striped.fiche-technique')
        dimensions = ""
        poid = ""
        poid_unit = ""
        couleur = ""
        screen_type = ""
        
        if table:
            rows = table.select('tr')
            for row in rows:
                header = row.select_one('td.libelle.item_header')
                value = row.select_one('td.champs')
                
                if header and value:
                    header_text = header.text.strip()
                    value_text = value.text.strip()
                    
                    if header_text == "Marque" and not brand:
                        brand = re.sub(r"^(Télévision|Téléphone)\s*", "", value_text.strip())
                    
                    elif header_text in ["Télévision", "Téléphone"] and not model:
                        model = value_text.strip().split()[-1] if value_text else ""
                    
                    elif header_text == "Poids":
                        poid_match = re.search(r"([\d\.]+)\s*([A-Za-z]+)", value_text)
                        if poid_match:
                            poid = poid_match.group(1)
                            poid_unit = poid_match.group(2)
                    
                    elif header_text == "Taille Ecran" and not screen_size:
                        screen_size = MultimediaUtils.extract_screen_size(value_text)
                    
                    elif header_text in ["Catégorie", "Qualité Ecran"]:
                        screen_type = value_text.strip()
                    
                    elif header_text == "Couleur":
                        couleur = value_text.strip()
                    
                    elif header_text == "Processeur" and not processor:
                        processor = MultimediaUtils.extract_processor(value_text)
                    
                    elif header_text == "Mémoire" and not ram:
                        ram, ram_unit = MultimediaUtils.extract_ram(value_text)
                    
                    elif header_text == "Disque" and not storage:
                        storage, storage_unit = MultimediaUtils.extract_storage(value_text)
        
        # Extract additional info from listing table
        livraison_elem = soup.select_one('table.table-annonce tr:-soup-contains("Livraison") td.properties_value')
        livraison = livraison_elem.text.strip().replace("Livraison (", "").replace(")", "") if livraison_elem else "48 Wilayas"
        
        # Extract color fallback
        if not couleur:
            couleur_elem = soup.select_one('table.table-annonce tr:-soup-contains("Couleur") td.properties_value')
            couleur = couleur_elem.text.strip() if couleur_elem else ""
        
        # Extract etat
        etat_elem = soup.select_one('table.table-annonce tr:-soup-contains("Etat") td.properties_value')
        etat = etat_elem.text.strip() if etat_elem else "New"
        etat = MultimediaUtils.normalize_etat(etat, description)
        
        # Extract address
        adresse_elem = soup.select_one('div.mb-2.text-muted.small i.fa-map-marker')
        adresse = adresse_elem.parent.text.strip() if adresse_elem else "Toute l'Algérie"
        
        # Extract price
        prix_dec = 0.0
        prix_unit = ""
        par_facilite = "False"
        prix_facilite = {}
        premier_versement = "False"
        premier_versement_value = ""
        
        # Check for premier versement
        premier_elem = soup.select_one('h4.libelle-prix')
        if premier_elem and "Premier Versement" in premier_elem.text:
            premier_versement = "True"
            price_match = re.search(r"Premier Versement\s*([\d\s]+)", premier_elem.text.replace("\xa0", " ").strip(), re.IGNORECASE)
            if price_match:
                price_text = price_match.group(1).strip()
                premier_versement_value = str(MultimediaUtils.str_to_float(price_text))
        
        # Check for facilité payment
        facilite_elem = soup.select_one('h6.text-success span.badge')
        if facilite_elem and "Vente par Facilité" in facilite_elem.text:
            par_facilite = "True"
            cleaned_text = facilite_elem.text.replace("\xa0", " ").strip()
            facilite_match = re.search(r"Vente par Facilité\s*:\s*([\d\s]+)", cleaned_text, re.IGNORECASE)
            if facilite_match:
                price = facilite_match.group(1).strip()
                cleaned_price = MultimediaUtils.str_to_float(price)
                months_match = re.search(r"/\s*(\d+)\s*mois", cleaned_text, re.IGNORECASE)
                if months_match:
                    months = months_match.group(1)
                    prix_facilite[months] = cleaned_price
                    prix_dec = cleaned_price * int(months)
                else:
                    prix_dec = cleaned_price
        else:
            # Regular price
            price_elem = soup.select_one('table.table-annonce tr:-soup-contains("Prix") td.properties_value') or \
                        soup.select_one('h4.libelle-prix')
            if price_elem and "Premier Versement" not in price_elem.text:
                price_text = price_elem.text.replace("\xa0", " ").strip()
                price_match = re.search(r"(?:Prix Neuf\s*)?([\d\s]+)", price_text, re.IGNORECASE)
                if price_match:
                    prix_dec = MultimediaUtils.str_to_float(price_match.group(1).strip())
        
        prix_unit = "DA" if prix_dec else ""

        item_details = {
            'titre': titre,
            'url': url,
            'etat': etat,
            'livraison': livraison,
            'site_origine': "Webstar-electro.com",
            'transaction': "Vente",
            'category': "multimedia",
            'categorie': categorie_value,
            'description': description,
            'date_depot': date_depot or datetime.now().isoformat()[:10],
            'marque': brand,
            'modele': model,
            'garantie': garantie,
            'garantie_unit': garantie_unit,
            'dimension': dimensions,
            'type_ecran': screen_type,
            'taille_ecran': screen_size,
            'os': os_name,
            'os_version': os_version,
            'poid': poid,
            'poid_unit': poid_unit,
            'couleur': couleur,
            'processor_cores': processor,
            'processor_hz': "",
            'm_interne': storage,
            'm_interne_unit': storage_unit,
            'ram': ram,
            'ram_unit': ram_unit,
            'camera_ar': camera_rear,
            'camera_av': camera_front,
            'batterie': battery,
            'prix_dec': str(prix_dec),
            'prix_unit': prix_unit,
            'images': images_list,
            'adresse': adresse,
            'status': 200,
            'date_crawl': datetime.now().isoformat(),
            'date_verif': datetime.now().isoformat(),
            'as_photo': MultimediaUtils.avec_sans_photo(images_list),
            'as_prix': MultimediaUtils.avec_sans_prix(str(prix_dec), prix_unit),
            'par_facilite': par_facilite,
            'prix_facilite': prix_facilite,
            'premier_versement': premier_versement,
            'premier_versement_value': premier_versement_value
        }

        print(json.dumps(item_details, indent=4, ensure_ascii=False))
        insert_data_to_es(item_details, "multimedia")
        
        return item_details