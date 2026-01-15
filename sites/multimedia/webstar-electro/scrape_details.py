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
        print(f"Extracted titre: {titre}")

        # Extract description (from h3 with class text-muted)
        description_elem = soup.select_one('h3.text-muted')
        description = description_elem.text.strip() if description_elem else ""
        print(f"Extracted description: {description}")

        # Extract images and as_photo
        images_list = []
        images = soup.select('div.galerie_photo_2 img.item_image_responsive_')
        images_list = [urljoin("https://webstar-electro.com", img['src']) for img in images if img.get('src')]
        as_photo = avec_sans_photo(images_list)
        print(f"Extracted images: {images_list}")

        # Extract date_depot (announcement date)
        date_elem = soup.select_one('div.text-muted.small i.fa-calendar')
        date_depot = ""
        if date_elem:
            date_text = date_elem.parent.text.strip()
            date_match = re.search(r"\d{4}-\d{2}-\d{2}", date_text)
            date_depot = date_match.group(0) if date_match else ""
        print(f"Extracted date_depot: {date_depot}")

        # Extract categorie from URL's 'page' parameter or path
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        categorie_value = ""
        if 'page' in query_params:
            page_value = query_params['page'][0]
            categorie_value = page_value.capitalize()
        else:
            path = parsed_url.path.lower()
            category_map = {
                "appareils-photos": "Appareils Photos",
                "consoles-de-jeux": "Consoles de Jeux",
                "demodulateur": "Demodulateurs",
                "manettes-de-jeux": "Manettes de Jeux",
                "smartwatch": "Smartwatch",
                "tablettes-tactiles": "Tablettes Tactiles",
                "telephones-mobiles": "Telephones Mobiles",
                "tv": "Televiseurs",
                "audio": "Audio",
                "chargeurs": "Chargeurs",
                "memoires": "Memoires",
                "power-bank": "Power Bank"
            }
            for key, value in category_map.items():
                if key in path:
                    categorie_value = value
                    break
        print(f"Extracted categorie from URL: {categorie_value}")

        # Extract details from the table
        table = soup.select_one('table.table-bordered.table-striped.fiche-technique')
        item_details = {
            'titre': titre,
            'url': url,
            'etat': "",
            'livraison': "",
            'site_origine': "Webstar-electro.com",
            'transaction': "Vente",
            'category': "electromenager",
            'categorie': categorie_value,
            'description': description,
            'date_depot': date_depot,
            'marque': "",
            'modele': "",
            'garantie': "",
            'garantie_unit': "",
            'dimension': "",
            'dimension_unit': "",
            'type_ecran': "",
            'taille_ecran': "",
            'taille_ecran_unit': "",
            'os': "",
            'os_version': "",
            'poid': "",
            'poid_unit': "",
            'couleur': "",
            'processor_cores': "",
            'processor_hz': "",
            'm_interne': "",
            'm_interne_unit': "",
            'ram': "",
            'ram_unit': "",
            'camera_ar': "",
            'camera_av': "",
            'batterie': "",
            'prix_dec': "",
            'prix_unit': "",
            'images': images_list,
            'adresse': "",
            'status': 200,
            'date_crawl': datetime.now().isoformat(),
            'date_verif': datetime.now().isoformat(),
            'as_photo': as_photo,
            'as_prix': "",
            'par_facilite': "False",
            'prix_facilite': {},
            'premier_versement': "False",
            'premier_versement_value': ""
        }

        if table:
            print("table found")
            # Dictionary of fields to extract with regex patterns
            field_map = {
                "Marque": lambda x: re.sub(r"^(Télévision|Téléphone)\s*", "", x.strip()),
                "Télévision": lambda x: x.strip().split()[-1] if "Télévision" in x else "",
                "Téléphone": lambda x: x.strip().split()[-1] if "Téléphone" in x else "",
                "Largeur": lambda x: re.search(r"(\d+\.?\d*)", x.strip()),
                "Hauteur": lambda x: re.search(r"(\d+\.?\d*)", x.strip()),
                "Profondeur": lambda x: re.search(r"(\d+\.?\d*)", x.strip()),
                "Poids": lambda x: re.search(r"(\d+\.?\d*)", x.strip()),
                "Catégorie": lambda x: x.strip().split()[0],
                "Qualité Ecran": lambda x: x.strip(),
                "Taille Ecran": lambda x: re.search(r"(\d+\.?\d*)", x.strip()),
                "Système": lambda x: x.strip().split()[0] if any(k in x for k in ["Smart", "Android"]) else x.strip(),
                "Processeur": lambda x: re.search(r"\((.*?)\)", x.strip()) or x.strip(),
                "Mémoire": lambda x: re.search(r"(\d+\.?\d*)\s*([A-Za-z]+)", x.strip()),
                "Disque": lambda x: re.search(r"(\d+\.?\d*)\s*([A-Za-z]+)", x.strip()),
                "Couleur": lambda x: x.strip(),
                "Capteurs": lambda x: re.search(r"(\d+)\s*MP", x.strip()),
                "Capteurs Selfie": lambda x: re.search(r"(\d+)\s*MP", x.strip())
            }

            # Extract all rows
            for row in table.select('tr'):
                header = row.select_one('td.libelle.item_header')
                value = row.select_one('td.champs')
                if header and value:
                    header_text = header.text.strip()
                    value_text = value.text.strip()
                    if header_text in field_map:
                        result = field_map[header_text](value_text)
                        if result:
                            if header_text in ["Largeur", "Hauteur", "Profondeur"]:
                                if not item_details['dimension']:
                                    item_details['dimension'] = []
                                    item_details['dimension_unit'] = []
                                match = re.match(r"(\d+\.?\d*)\s*([A-Za-z]+)", value_text)
                                if match:
                                    item_details['dimension'].append(match.group(1))
                                    item_details['dimension_unit'].append(match.group(2))
                            elif header_text == "Poids":
                                match = re.match(r"(\d+\.?\d*)\s*([A-Za-z]+)", value_text)
                                if match:
                                    item_details['poid'] = match.group(1)
                                    item_details['poid_unit'] = match.group(2)
                            elif header_text == "Taille Ecran":
                                match = re.match(r"(\d+\.?\d*)\s*([A-Za-z]+)", value_text)
                                if match:
                                    item_details['taille_ecran'] = match.group(1)
                                    item_details['taille_ecran_unit'] = match.group(2)
                            elif header_text == "Marque":
                                item_details['marque'] = result
                            elif header_text in ["Télévision", "Téléphone"]:
                                item_details['modele'] = result
                            elif header_text == "Catégorie":
                                item_details['type_ecran'] = result
                            elif header_text == "Qualité Ecran":
                                item_details['type_ecran'] = result
                            elif header_text == "Système":
                                item_details['os'] = result
                            elif header_text == "Processeur":
                                item_details['processor_cores'] = result.group(1) if isinstance(result, re.Match) and result.group(1) else result
                            elif header_text == "Mémoire":
                                if isinstance(result, re.Match):
                                    item_details['ram'] = result.group(1)
                                    item_details['ram_unit'] = result.group(2)
                            elif header_text == "Disque":
                                if isinstance(result, re.Match):
                                    item_details['m_interne'] = result.group(1)
                                    item_details['m_interne_unit'] = result.group(2)
                            elif header_text == "Couleur":
                                item_details['couleur'] = result
                            elif header_text == "Capteurs":
                                item_details['camera_ar'] = result.group(1) if isinstance(result, re.Match) and result.group(1) else ""
                            elif header_text == "Capteurs Selfie":
                                item_details['camera_av'] = result.group(1) if isinstance(result, re.Match) and result.group(1) else ""

            # Combine dimension if all parts are found
            if len(item_details['dimension']) == 3:
                item_details['dimension'] = ", ".join(item_details['dimension'])
                item_details['dimension_unit'] = item_details['dimension_unit'][0]  # Assume same unit for all

        # Extract livraison
        livraison_elem = soup.select_one('table.table-annonce tr:-soup-contains("Livraison") td.properties_value')
        item_details['livraison'] = livraison_elem.text.strip().replace("Livraison (", "").replace(")", "") if livraison_elem else ""
        print(f"Extracted livraison: {item_details['livraison']}")

        # Extract garantie and garantie_unit
        garantie_elem = soup.select_one('table.table-annonce tr:-soup-contains("Garantie") td.properties_value')
        if garantie_elem and garantie_elem.text.strip():
            garantie_text = re.search(r"(\d+)\s*(Mois|Ans)", garantie_elem.text.strip())
            if garantie_text:
                item_details['garantie'] = garantie_text.group(1)
                item_details['garantie_unit'] = garantie_text.group(2)
        print(f"Extracted garantie: {item_details['garantie']}, garantie_unit: {item_details['garantie_unit']}")

        # Extract couleur (fallback if not in table)
        if not item_details['couleur']:
            couleur_elem = soup.select_one('table.table-annonce tr:-soup-contains("Couleur") td.properties_value')
            item_details['couleur'] = couleur_elem.text.strip() if couleur_elem else ""
            print(f"Extracted couleur (fallback): {item_details['couleur']}")

        # Extract etat
        etat_elem = soup.select_one('table.table-annonce tr:-soup-contains("Etat") td.properties_value')
        item_details['etat'] = etat_elem.text.strip() if etat_elem else "true"
        print(f"Extracted etat: {item_details['etat']}")

        # Extract adresse
        adresse_elem = soup.select_one('div.mb-2.text-muted.small i.fa-map-marker')
        item_details['adresse'] = adresse_elem.parent.text.strip() if adresse_elem else ""
        print(f"Extracted adresse: {item_details['adresse']}")

        # Extract premier_versement and premier_versement_value
        premier_elem = soup.select_one('h4.libelle-prix')
        if premier_elem and "Premier Versement" in premier_elem.text:
            item_details['premier_versement'] = "True"
            price_match = re.search(r"Premier Versement\s*([\d\s]+)", premier_elem.text.replace("\xa0", " ").strip(), re.IGNORECASE)
            if price_match:
                price_text = price_match.group(1).strip() + " Da"
                item_details['premier_versement_value'] = str(process_price(price_text))
        print(f"Extracted premier_versement: {item_details['premier_versement']}, value: {item_details['premier_versement_value']}")

        # Extract par_facilite, prix_facilite, and prix_dec
        facilite_elem = soup.select_one('h6.text-success span.badge')
        if facilite_elem and "Vente par Facilité" in facilite_elem.text:
            item_details['par_facilite'] = "True"
            cleaned_text = facilite_elem.text.replace("\xa0", " ").strip()
            facilite_match = re.search(r"Vente par Facilité\s*:\s*([\d\s]+)", cleaned_text, re.IGNORECASE)
            if facilite_match:
                price = facilite_match.group(1).strip() + " Da"
                cleaned_price = process_price(price)
                months_match = re.search(r"/\s*(\d+)\s*mois", cleaned_text, re.IGNORECASE)
                if months_match:
                    months = months_match.group(1)
                    item_details['prix_facilite'][months] = cleaned_price
                    item_details['prix_dec'] = str(cleaned_price * int(months))
                else:
                    item_details['prix_dec'] = str(cleaned_price)
        else:
            price_elem = soup.select_one('table.table-annonce tr:-soup-contains("Prix") td.properties_value') or soup.select_one('h4.libelle-prix')
            if price_elem and "Premier Versement" not in price_elem.text:
                price_text = price_elem.text.replace("\xa0", " ").strip()
                price_match = re.search(r"(?:Prix Neuf\s*)?([\d\s]+)", price_text, re.IGNORECASE)
                if price_match:
                    price_text = price_match.group(1).strip() + " Da"
                    item_details['prix_dec'] = str(process_price(price_text))
        item_details['prix_unit'] = "DA" if item_details['prix_dec'] else ""
        item_details['as_prix'] = avec_sans_prix(item_details['prix_dec'], item_details['prix_unit'])

        print(json.dumps(item_details, indent=4, ensure_ascii=False))
        return item_details