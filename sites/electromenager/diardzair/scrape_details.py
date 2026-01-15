from datetime import datetime, timedelta
from threading import Thread
import re
import locale
import json
import asyncio
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from datetime import datetime
from urllib.parse import unquote, urljoin
import sys
sys.path.insert(1, '../../global')
#from insert_scrape import insert_data_to_es
# locale.setlocale(locale.LC_TIME, "fr_FR")

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
    cleaned_price = price_string.replace("DZD", "").replace(" DA", "").replace("\xa0", "").strip()
    cleaned_price = cleaned_price.replace(" ", "").replace(",", ".")
    try:
        price_float = float(cleaned_price)
    except ValueError:
        price_float = 0.0
    return price_float

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
    print("Extracting product details from:", url)
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
        description = soup.find('div', class_='product-description').text.strip() if soup.find('div', class_='product-description') else ""
        ram = ""
        ram_unit = ""
        ram_match = re.search(r"RAM\s*(\d+)\s*(GO|GB)\s*([A-Za-z0-9]+)\s*(\d{4,6})", result.html)
        os = ""
        os_version = ""
        os_match = re.search(r"(windows\s*(\d{1,2}[\.\d+]*)?|macos\s*(\d{1,2}[\.\d+]*)?|linux|ubuntu|chrome\s*os)", result.html.lower())
        as_photo = "Sans photo"
        
        images_list = []
        images = soup.find_all('a', class_='thumb js-thumb')
        if len(images) == 0:
            images = soup.find('div', class_='product-cover sm-bottom').find_all('img') if soup.find('div', class_='product-cover sm-bottom') else []
            images_list = [image['src'] for image in images]
        else:
            for image in images:
                images_list.append(image['data-image'])
        if len(images_list) > 0:
            as_photo = "Avec photo"

        if os_match:
            os = os_match.group(1) if os_match.group(1) else ""
            os_version = os_match.group(2) if os_match.group(2) else ""
        else:
            os = ""
            os_version = ""

        if ram_match:
            ram = ram_match.group(1)
            ram_unit = ram_match.group(2)            
        else:
            ram = ""
            ram_unit = ""
            
        garantie = ""
        garantie_unit = ""
        garantie_match = re.search(r"(\d+)\s(Mois|Ans)", result.html)
        if garantie_match:
            garantie = garantie_match.group(1)
            garantie_unit = garantie_match.group(2)

        # Extract marque
        marque_match = re.search(r"Marque\s*:\s*([^\n]+)", result.html)
        marque = marque_match.group(1).strip() if marque_match else "Maxwell"

        # Extract modele
        modele_match = re.search(r"Référence\s*:\s*([^\n]+)", result.html)
        modele = modele_match.group(1).strip() if modele_match else "MAX-32MV50"

        # Extract livraison
        livraison_match = re.search(r"Livraison\s*:\s*([^\n]+)", result.html)
        livraison = livraison_match.group(1).strip() if livraison_match else "48 Wilayas"

        # Extract par_facilite and prix_facilite
        par_facilite = "True"
        prix_facilite = {}
        facilite_matches = re.findall(r"(\d+\s*DA)\s*/\s*mois\s*jusqu'à\s*(\d+)\s*mois", result.html)
        if facilite_matches:
            for price, months in facilite_matches:
                cleaned_price = process_price(price)
                prix_facilite[months] = cleaned_price
        else:
            par_facilite = "False"
            prix_facilite = False

        # Extract prix_dec (only if par_facilite is False)
        prix_dec = ""
        if par_facilite == "False":
            price_match = re.search(r"(\d+\s*DA)", result.html)
            prix_dec = process_price(price_match.group(1)) if price_match else ""

        item_details = {
            'titre': "",
            'url': url,
            'etat': "true",
            'livraison': livraison,
            'site_origine': "Websoog.com",
            'transaction': "Vente",
            'category': "electromenager",
            'description': description,
            'date_depot': datetime.now().isoformat(),
            'marque': marque,
            'modele': modele,
            'garantie': garantie if garantie else "",
            'garantie_unit': garantie_unit if garantie_unit else "",
            'dimension': "",
            'type_ecran': "",
            'taille_ecran': "",
            'os': os.capitalize() if os else "",
            'os_version': os_version if os_version else "",
            'poid': re.search(r"Poids\s*\(g\)\s*[:\-]?\s*(\d+)", result.html).group(1) if re.search(r"Poids\s*\(g\)\s*[:\-]?\s*(\d+)", result.html) else "",
            'couleur': re.search(r"Couleur\s*[:\-]?\s*(\w+)", result.html).group(1) if re.search(r"Couleur\s*[:\-]?\s*(\w+)", result.html) else "",
            'poid_unit': re.search(r"Poids\s*\(g\)\s*[:\-]?\s*(\d+)", result.html).group(1) if re.search(r"Poids\s*\(g\)\s*[:\-]?\s*(\d+)", result.html) else "",
            'processor_cores': re.search(r"(Quad-Core|Octa-Core)", result.html).group(1) if re.search(r"(Quad-Core|Octa-Core)", result.html) else "",
            'processor_hz': re.search(r"Vitesse\s*CPU\s*\(GHz\)\s*[:\-]?\s*(\S+)", result.html).group(1) if re.search(r"Vitesse\s*CPU\s*\(GHz\)\s*[:\-]?\s*(\S+)", result.html) else "",
            'm_interne': re.search(r"Capacit\.\s*\(\w+\)\s*[:\-]?\s*(\d+)", result.html).group(1) if re.search(r"Capacit\.\s*\(\w+\)\s*[:\-]?\s*(\d+)", result.html) else "",
            'm_interne_unit': re.search(r"Capacit. \((\w+)", result.html).group(1) if re.search(r"Capacit. \((\w+)", result.html) else "",
            'ram': ram if ram else "",
            'ram_unit': ram_unit if ram_unit else "",
            'camera_ar': re.search(r"(\d+\s*M\.?P\.?)\s*pixels?", result.html).group(1) if re.search(r"(\d+\s*M\.?P\.?)\s*pixels?", result.html) else "",
            'camera_av': re.search(r"(\d+.\d+)\sM.gapixels", result.html).group(1) if re.search(r"(\d+.\d+)\sM.gapixels", result.html) else "",
            'batterie': re.search(r"(\d+) mAh", result.html).group(1) if re.search(r"(\d+) mAh", result.html) else "",
            'prix_dec': prix_dec,
            'prix_unit': "DA",
            'images': images_list,
            'adresse': "Toute l'Algérie",
            'status': 200,
            'date_crawl': datetime.now().isoformat(),
            'date_verif': datetime.now().isoformat(),
            'as_photo': as_photo,
            'as_prix': avec_sans_prix(prix_dec, "DA"),
            'par_facilite': par_facilite,
            'prix_facilite': prix_facilite
        }

        print(json.dumps(item_details, indent=4))
        #insert_data_to_es(item_details, "electromenager")
        return item_details