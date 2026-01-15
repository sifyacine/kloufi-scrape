from datetime import datetime
import re
import json
import asyncio
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from urllib.parse import urljoin, parse_qs, urlparse

def avec_sans_photo(image):
    if len(str(image)):
        as_photo = "Avec photo"
        return as_photo
    else:
        as_photo = "Sans photo"
        return as_photo

def avec_sans_prix(Prix_dec, Prix_unit):
    if len(Prix_dec) and len(Prix_unit) and float(Prix_dec) != 0:
        as_prix = "Avec prix"
        return as_prix
    else:
        as_prix = "Sans prix"
        return as_prix

def process_price(price_string):
    print(f"Processing price: {price_string}")  # Debugging
    cleaned_price = price_string.replace("DZD", "").replace("Da", "").replace("\xa0", "").strip()
    print(f"After initial clean: {cleaned_price}")  # Debugging
    cleaned_price = cleaned_price.replace(" ", "")
    print(f"After whitespace removal: {cleaned_price}")  # Debugging
    try:
        price_float = float(cleaned_price)
        print(f"Converted to float: {price_float}")  # Debugging
        return price_float
    except ValueError as e:
        print(f"ValueError in process_price: {e}, setting to 0.0")  # Debugging
        return 0.0

def traitement_prix(prix_dec, prix_unit):
    if len(prix_dec) and len(prix_unit):
        if prix_unit == "Millions":
            return float(prix_dec) * 10000
        elif prix_unit == "Milliards":
            return float(prix_dec) * 10000000
        else:
            return float(prix_dec)
    else:
        prix_dec = 0
        return prix_dec

def str_to_float(valeur):
    if not valeur:
        return ""
    valeur = valeur.replace(",", ".")
    try:
        return float(valeur)
    except ValueError:
        return ""

def str_to_int(valeur):
    if not valeur:
        return ""
    try:
        return int(valeur)
    except ValueError:
        return ""

def categorie(valeur):
    if not valeur:
        return ""
    elif valeur == "Téléphone portable":
        return "Smartphones"
    elif valeur == "Accessoires & Smartwatches":
        return "Accessoires"
    else:
        return valeur

async def extract_product_details(url):
    """
    Extracts product details from a seller's offer page on Webstar Electro.
    Returns a dictionary with all specified fields, using provided HTML structure.
    Missing values are returned as empty strings.
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

        # Extract titre (from h1 with class structure_content_titre)
        titre_elem = soup.select_one('h1.structure_content_titre')
        titre = titre_elem.text.strip() if titre_elem else ""
        print(f"Extracted titre: {titre}")  # Debugging

        # Extract description (from h3 with class text-muted)
        description_elem = soup.select_one('h3.text-muted')
        description = description_elem.text.strip() if description_elem else ""
        print(f"Extracted description: {description}")  # Debugging

        # Extract images and as_photo
        images_list = []
        images = soup.select('div.galerie_photo_2 img.item_image_responsive_')
        images_list = [urljoin("https://webstar-electro.com", img['src']) for img in images if img.get('src')]
        as_photo = avec_sans_photo(images_list)
        print(f"Extracted images: {images_list}")  # Debugging

        # Extract date_depot (announcement date)
        date_elem = soup.select_one('div.text-muted.small i.fa-calendar')
        date_depot = ""
        if date_elem:
            date_text = date_elem.parent.text.strip()
            date_match = re.search(r"\d{4}-\d{2}-\d{2}", date_text)
            date_depot = date_match.group(0) if date_match else ""
        print(f"Extracted date_depot: {date_depot}")  # Debugging

        # Extract categorie from URL's 'page' parameter
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        categorie_value = ""
        if 'page' in query_params:
            page_value = query_params['page'][0]  # e.g., "aspirateurs"
            # Capitalize first letter to match expected format (e.g., "Aspirateurs")
            categorie_value = page_value.capitalize()
            print(f"Extracted categorie from URL: {categorie_value}")
        else:
            print("No 'page' parameter found in URL for categorie.")

        # Extract marque and modele from the table
        table = soup.select_one('div.col-md-12.col-xl-10 table.table-bordered')
        marque = ""
        modele = ""

        if table:
            print("table found")
            # Extract marque and modele from "Produit" row
            produit_row = table.select_one('tr:-soup-contains("Produit")')
            if produit_row:
                produit_td = produit_row.find('td', class_='properties_value text-muted')
                if produit_td:
                    produit_text = produit_td.text.strip()
                    words = produit_text.split()
                    if len(words) >= 2:
                        marque = words[0]  # e.g., "BISSELL"
                        modele = words[1]  # e.g., "1713"
                        print(f"Extracted marque: {marque}")
                        print(f"Extracted modele: {modele}")
                    else:
                        marque = produit_text  # Fallback if only one word
                        print(f"Extracted marque (single word): {marque}")
                else:
                    print("No properties_value td found in Produit row.")
            else:
                print("No Produit row found.")

        # Extract livraison
        livraison_elem = soup.select_one('table.table-annonce tr:-soup-contains("Livraison") td.properties_value')
        livraison = livraison_elem.text.strip().replace("Livraison (", "").replace(")", "") if livraison_elem else ""
        print(f"Extracted livraison: {livraison}")  # Debugging

        # Extract garantie and garantie_unit
        garantie_elem = soup.select_one('table.table-annonce tr:-soup-contains("Garantie") td.properties_value')
        garantie = ""
        garantie_unit = ""
        if garantie_elem and garantie_elem.text.strip():
            garantie_text = re.search(r"(\d+)\s*(Mois|Ans)", garantie_elem.text.strip())
            if garantie_text:
                garantie = garantie_text.group(1)
                garantie_unit = garantie_text.group(2)
        print(f"Extracted garantie: {garantie}, garantie_unit: {garantie_unit}")  # Debugging

        # Extract couleur
        couleur_elem = soup.select_one('table.table-annonce tr:-soup-contains("Couleur") td.properties_value')
        couleur = couleur_elem.text.strip() if couleur_elem else ""
        print(f"Extracted couleur: {couleur}")  # Debugging

        # Extract etat
        etat_elem = soup.select_one('table.table-annonce tr:-soup-contains("Etat") td.properties_value')
        etat = etat_elem.text.strip() if etat_elem else "true"
        print(f"Extracted etat: {etat}")  # Debugging

        # Extract adresse
        adresse_elem = soup.select_one('div.mb-2.text-muted.small i.fa-map-marker')
        adresse = ""
        if adresse_elem:
            adresse_text = adresse_elem.parent.text.strip()
            adresse = re.sub(r'\s+', ' ', adresse_text).strip()
        print(f"Extracted adresse: {adresse}")  # Debugging

        # Extract premier_versement and premier_versement_value
        premier_versement = "False"
        premier_versement_value = ""
        premier_elem = soup.select_one('h4.libelle-prix')
        if premier_elem:
            cleaned_text = premier_elem.text.replace("\xa0", " ").strip()
            print(f"Premier versement text: {cleaned_text}")  # Debugging
            if "Premier Versement" in cleaned_text:
                premier_versement = "True"
                price_match = re.search(r"Premier Versement\s*([\d\s]+)", cleaned_text, re.IGNORECASE)
                print(f"Premier match: {price_match}")  # Debugging
                if price_match:
                    price_text = price_match.group(1).strip() + " Da"
                    print(f"Price text before process: {price_text}")  # Debugging
                    premier_versement_value = str(process_price(price_text))
                    print(f"Processed premier value: {premier_versement_value}")  # Debugging
                else:
                    premier_versement_value = "0"
        else:
            print("No premier versement element found.")  # Debugging
            premier_versement_value = ""

        # Extract par_facilite, prix_facilite, and prix_dec
        par_facilite = "False"
        prix_facilite = {}
        prix_dec = ""
        facilite_elem = soup.select_one('h6.text-success span.badge')
        if facilite_elem:
            cleaned_text = facilite_elem.text.replace("\xa0", " ").strip()
            print(f"Vente par facilite text: {cleaned_text}")  # Debugging
            if "Vente par Facilité" in cleaned_text:
                par_facilite = "True"
                facilite_match = re.search(r"Vente par Facilité\s*:\s*([\d\s]+)", cleaned_text, re.IGNORECASE)
                print(f"Facilite match: {facilite_match}")  # Debugging
                if facilite_match:
                    price = facilite_match.group(1).strip() + " Da"
                    print(f"Price text before process: {price}")  # Debugging
                    cleaned_price = process_price(price)
                    print(f"Processed facilite price: {cleaned_price}")  # Debugging
                    months_match = re.search(r"/\s*(\d+)\s*mois", cleaned_text, re.IGNORECASE)
                    if months_match:
                        months = months_match.group(1)
                        prix_facilite[months] = cleaned_price
                        # Calculate total price: monthly price * number of months
                        total_price = cleaned_price * int(months)
                        prix_dec = total_price
                        print(f"Calculated total price (par_facilite): {prix_dec} (monthly price {cleaned_price} x {months} months)")
                    else:
                        # If months not found, set prix_dec to the monthly price as before
                        prix_dec = cleaned_price
                        print(f"No months found, setting prix_dec to monthly price: {prix_dec}")
        else:
            print("No vente par facilite element found.")  # Debugging

        # Try regular price if vente par facilite is not found
        if not prix_dec:
            price_elem = soup.select_one('table.table-annonce tr:-soup-contains("Prix") td.properties_value')
            if price_elem:
                price_text = price_elem.text.strip()
                print(f"Regular price from table: {price_text}")  # Debugging
                prix_dec = process_price(price_text)
            else:
                price_elem = soup.select_one('h4.libelle-prix')
                if price_elem and "Premier Versement" not in price_elem.text:
                    cleaned_text = price_elem.text.replace("\xa0", " ").strip()
                    print(f"Regular price text from h4: {cleaned_text}")  # Debugging
                    price_match = re.search(r"(?:Prix Neuf\s*)?([\d\s]+)", cleaned_text, re.IGNORECASE)
                    print(f"Regular price match: {price_match}")  # Debugging
                    if price_match:
                        price_text = price_match.group(1).strip() + " Da"
                        print(f"Price text before process: {price_text}")  # Debugging
                        prix_dec = process_price(price_text)

        item_details = {
            'titre': titre,
            'url': url,
            'etat': etat,
            'livraison': livraison,
            'site_origine': "Webstar-electro.com",
            'transaction': "Vente",
            'category': "electromenager",
            'categorie': categorie_value,
            'description': description,
            'date_depot': date_depot,
            'marque': marque,
            'modele': modele,
            'garantie': garantie,
            'garantie_unit': garantie_unit,
            'poid': "",
            'couleur': couleur,
            'poid_unit': "",
            'batterie': "",
            'prix_dec': str(prix_dec) if prix_dec else "",
            'prix_unit': "DA" if prix_dec else "",
            'images': images_list,
            'adresse': adresse,
            'status': 200,
            'date_crawl': datetime.now().isoformat(),
            'date_verif': datetime.now().isoformat(),
            'as_photo': as_photo,
            'as_prix': avec_sans_prix(str(prix_dec), "DA"),
            #'par_facilite': par_facilite,
            #'prix_facilite': prix_facilite,
            #'premier_versement': premier_versement,
            #'premier_versement_value': premier_versement_value
        }

        print(json.dumps(item_details, indent=4, ensure_ascii=False))
        return item_details