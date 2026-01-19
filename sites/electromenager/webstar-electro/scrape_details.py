# scrape_details.py - Webstar-electro electromenager scraper with ElectromenagerUtils
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
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from utils.electromenager import ElectromenagerUtils

try:
    sys.path.insert(1, '../../global')
    from insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] Inserting data to ES index '{index}'")


async def extract_product_details(url):
    """Extract electromenager details from Webstar-electro page"""
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
        
        categorie = ElectromenagerUtils.normalize_categorie(categorie_value)
        
        # Extract brand and model
        brand = ElectromenagerUtils.extract_brand(titre)
        model = ElectromenagerUtils.extract_model(titre)
        
        # Fallback brand/model from table
        table = soup.select_one('div.col-md-12.col-xl-10 table.table-bordered')
        if table:
            produit_row = table.select_one('tr:-soup-contains("Produit")')
            if produit_row:
                produit_td = produit_row.find('td', class_='properties_value text-muted')
                if produit_td:
                    produit_text = produit_td.text.strip()
                    words = produit_text.split()
                    if len(words) >= 2 and not brand:
                        brand = words[0]
                        model = words[1]
                    elif not brand:
                        brand = produit_text
        
        # Extract livraison
        livraison_elem = soup.select_one('table.table-annonce tr:-soup-contains("Livraison") td.properties_value')
        livraison = livraison_elem.text.strip().replace("Livraison (", "").replace(")", "") if livraison_elem else "48 Wilayas"
        
        # Extract specifications using ElectromenagerUtils
        garantie, garantie_unit = ElectromenagerUtils.extract_warranty(result.html)
        capacite, capacite_unit = ElectromenagerUtils.extract_capacity(result.html)
        classe_energie = ElectromenagerUtils.extract_energy_class(result.html)
        puissance, puissance_unit = ElectromenagerUtils.extract_power(result.html)
        poid, poid_unit = ElectromenagerUtils.extract_weight(result.html)
        couleur = ElectromenagerUtils.extract_color(result.html)
        dimensions = ElectromenagerUtils.extract_dimensions(result.html)
        
        # Fallback color
        if not couleur:
            couleur_elem = soup.select_one('table.table-annonce tr:-soup-contains("Couleur") td.properties_value')
            couleur = couleur_elem.text.strip() if couleur_elem else ""
        
        # Extract etat
        etat_elem = soup.select_one('table.table-annonce tr:-soup-contains("Etat") td.properties_value')
        etat = etat_elem.text.strip() if etat_elem else "Neuf"
        
        # Extract address
        adresse_elem = soup.select_one('div.mb-2.text-muted.small i.fa-map-marker')
        adresse = re.sub(r'\s+', ' ', adresse_elem.parent.text.strip()).strip() if adresse_elem else "Toute l'Algérie"
        
        # Extract payment details
        premier_versement = "False"
        premier_versement_value = ""
        premier_elem = soup.select_one('h4.libelle-prix')
        
        if premier_elem:
            cleaned_text = premier_elem.text.replace("\xa0", " ").strip()
            if "Premier Versement" in cleaned_text:
                premier_versement = "True"
                price_match = re.search(r"Premier Versement\s*([\d\s]+)", cleaned_text, re.IGNORECASE)
                if price_match:
                    price_text = price_match.group(1).strip()
                    premier_versement_value = str(ElectromenagerUtils.process_price(price_text))
        
        # Extract facilite price
        par_facilite = "False"
        prix_facilite = {}
        prix_dec = 0.0
        
        facilite_elem = soup.select_one('h6.text-success span.badge')
        if facilite_elem:
            cleaned_text = facilite_elem.text.replace("\xa0", " ").strip()
            if "Vente par Facilité" in cleaned_text:
                par_facilite = "True"
                facilite_match = re.search(r"Vente par Facilité\s*:\s*([\d\s]+)", cleaned_text, re.IGNORECASE)
                if facilite_match:
                    price = facilite_match.group(1).strip()
                    cleaned_price = ElectromenagerUtils.process_price(price)
                    months_match = re.search(r"/\s*(\d+)\s*mois", cleaned_text, re.IGNORECASE)
                    if months_match:
                        months = months_match.group(1)
                        prix_facilite[months] = cleaned_price
                        prix_dec = cleaned_price * int(months)
                    else:
                        prix_dec = cleaned_price
        
        # Regular price fallback
        if not prix_dec:
            price_elem = soup.select_one('table.table-annonce tr:-soup-contains("Prix") td.properties_value') or \
                        soup.select_one('h4.libelle-prix')
            if price_elem and "Premier Versement" not in price_elem.text:
                price_text = price_elem.text.replace("\xa0", " ").strip()
                price_match = re.search(r"(?:Prix Neuf\s*)?([\d\s]+)", price_text, re.IGNORECASE)
                if price_match:
                    prix_dec = ElectromenagerUtils.process_price(price_match.group(1).strip())

        item_details = {
            'titre': titre,
            'url': url,
            'etat': etat,
            'livraison': livraison,
            'site_origine': "Webstar-electro.com",
            'transaction': "Vente",
            'category': "electromenager",
            'categorie': categorie,
            'description': description,
            'date_depot': date_depot or datetime.now().isoformat()[:10],
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
            'prix_dec': str(prix_dec),
            'prix_unit': "DA" if prix_dec else "",
            'images': images_list,
            'adresse': adresse,
            'status': 200,
            'date_crawl': datetime.now().isoformat(),
            'date_verif': datetime.now().isoformat(),
            'as_photo': ElectromenagerUtils.avec_sans_photo(images_list),
            'as_prix': ElectromenagerUtils.avec_sans_prix(str(prix_dec), "DA"),
            'par_facilite': par_facilite,
            'prix_facilite': prix_facilite,
            'premier_versement': premier_versement,
            'premier_versement_value': premier_versement_value
        }

        print(json.dumps(item_details, indent=4, ensure_ascii=False))
        insert_data_to_es(item_details, "electromenager")
        
        return item_details