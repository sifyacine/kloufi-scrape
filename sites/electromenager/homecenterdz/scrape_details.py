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
from insert_scrape import insert_data_to_es
# locale.setlocale(locale.LC_TIME, "fr_FR")

def avec_sans_photo(image):
    if len(str(image)):
        as_photo = "Avec photo"
        return as_photo
    else:
        as_photo = "Sans photo"
        return as_photo

# Avec ou sans prix
def avec_sans_prix(Prix_dec, Prix_unit):
    if len(Prix_dec) and len(Prix_unit) and float(Prix_dec) != 0:
        as_prix = "Avec prix"
        return as_prix
    else:
        as_prix = "Sans prix"
        return as_prix

def process_price(price_string):
    cleaned_price = price_string.replace("DZD", "").replace(" DA", "").replace("\xa0", "").strip()
    print("Cleaned price:", cleaned_price)
    
    cleaned_price = cleaned_price.replace(" ", "")
    cleaned_price = cleaned_price.replace(",", ".")

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
        prix = "Annonce sans prix"

def str_to_float(valeur):

    if not valeur:
        valeur = ""
        return valeur
    else:
        valeur = valeur.replace(",", ".")
        valeur = float(valeur)
        return valeur

def str_to_int(valeur):
    if not valeur:
        valeur = ""
        return valeur
    else:
        valeur = int(valeur)
        return valeur

def str_to_date(valeur):

    if not valeur:
        valeur = ""
        return valeur
    else:
        return valeur

def categorie(valeur):

    if not valeur:
        valeur = ""
        return valeur
    elif valeur == "Téléphone portable":
        return "Smartphones"
    elif valeur == "Accessoires & Smartwatches":
        return "Accessoires"
    else:
        return valeur

async def scrape_product_details(url, item):
    # Configure the browser
    print("Extracting property details from:", url)
    browser_config = BrowserConfig(
        headless=True,  # Set to True if you do not need to see the browser
        verbose=True,
        browser_type="chromium",
    )

    # Start the crawling process
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=url,
            javascript_enabled=True,
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                delay_before_return_html=5
            ),
        )

        # Ensure the page rendered successfully
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
        if item['image']:
            images_list.append(item['image'])
        
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
            
        # <div class="marque"><div class="img_container"><img src="images/marques/1589457275-téléchargement (2).png" alt="MOULINEX"></div></div>
        marque = re.search(r'<div class="marque"><div class="img_container"><img src="images/marques/\d+-[\w\s\(\)]+\.png" alt="([\w\s\(\)]+)">', result.html)

        item_details = {
            'titre': item['title'] if item['title'] else "",
            'url': url,
            'etat': "true",
            'livraison': "48 Wilayas",
            'site_origine': "Homecenterdz.com",
            'transaction': "Vente",
            'category':"electromenager",
            # 'categorie' : categorie_text,
            'description' : description,
            'date_depot': datetime.now().isoformat(),
            'marque': marque.group(1) if marque else "",
            'modele': "",
            'garantie': garantie if garantie else "",
            'garantie_unit': garantie_unit if garantie_unit else [],
            'dimension': re.search(r"Dimensions\s*[:\-]?\s*(\d+\s*x\s*\d+\s*x\s*\d+\s*cm)", result.html).group(1) if re.search(r"Dimensions\s*[:\-]?\s*(\d+\s*x\s*\d+\s*x\s*\d+\s*cm)", result.html) else "",
            'type_ecran': "",
            'taille_ecran': "",
            'os': os.capitalize() if os else "",
            'os_version': os_version if os_version else "",
            'poid': re.search(r"Poid\s*\(g\)\s*[:\-]?\s*(\d+)", result.html).group(1) if re.search(r"Poids\s*\(g\)\s*[:\-]?\s*(\d+)", result.html) else "",
            'couleur': re.search(r"Couleur\s*[:\-]?\s*(\w+)", result.html).group(1) if re.search(r"Couleur\s*[:\-]?\s*(\w+)", result.html) else "",
            'poid_unit': re.search(r"Poid\s*\(g\)\s*[:\-]?\s*(\d+)", result.html).group(1) if re.search(r"Poids\s*\(g\)\s*[:\-]?\s*(\d+)", result.html) else "",
            'processor_cores': re.search(r"(Quad-Core|Octa-Core)", result.html).group(1) if re.search(r"(Quad-Core|Octa-Core)", result.html) else "",
            'processor_hz': re.search(r"Vitesse\s*CPU\s*\(GHz\)\s*[:\-]?\s*(\S+)", result.html).group(1) if re.search(r"Vitesse\s*CPU\s*\(GHz\)\s*[:\-]?\s*(\S+)", result.html) else "",
            'm_interne': re.search(r"Capacit\.\s*\(\w+\)\s*[:\-]?\s*(\d+)", result.html).group(1) if re.search(r"Capacit\.\s*\(\w+\)\s*[:\-]?\s*(\d+)", result.html) else "",
            'm_interne_unit': re.search(r"Capacit. \((\w+)", result.html).group(1) if re.search(r"Capacit. \((\w+)", result.html) else "",
            'ram': ram if ram else "",
            'ram_unit': ram_unit if ram_unit else "",
            'camera_ar': re.search(r"(\d+\s*M\.?P\.?)\s*pixels?", result.html).group(1) if re.search(r"(\d+\s*M\.?P\.?)\s*pixels?", result.html) else [],
            'camera_av': re.search(r"(\d+.\d+)\sM.gapixels", result.html).group(1) if re.search(r"(\d+.\d+)\sM.gapixels", result.html) else "",
            'batterie': re.search(r"(\d+) mAh", result.html).group(1) if re.search(r"(\d+) mAh", result.html) else "",
            'prix': item['price'] if item['price'] else "",
            'prix_dec': process_price(item['price']) if item['price'] and item['price'] != "" else "",
            'prix_unit': "DA",
            'images': images_list,
            'adresse': "Toute l'Algérie",
            'status': 200,
            'date_crawl': datetime.now().isoformat(),
            'date_verif': datetime.now().isoformat(),
            'as_photo': as_photo,
            'as_prix': "Avec prix" if item['price'] and item['price'] != "" else "Sans prix",
            # 'email': re.search(r'[\w\.-]+@[\w\.-]+', result.html).group()
        }

        # Output the results
        print(json.dumps(item_details, indent=4))
        insert_data_to_es(item_details, "electromenager")

# Example of how you might call this function
# asyncio.run(extract_multimedia_details("https://www.websoog.com/fr/electromenager/380-bouilloire-eau-noir.html",
#                                      {
#                                          "title": "Tefal Appareil \u00e0 cr\u00eapes 6 empreintes, Antiadh\u00e9sif, Thermo-Spot",
#                                          "url": "https://www.jumia.com.dz/tefal-appareil-a-crepes-6-empreintes-antiadhesif-thermo-spot-595765.html",
#                                          "price": "14,500 DA",
#                                          "image": "https://dz.jumia.is/unsafe/fit-in/300x300/filters:fill(white)/product/56/7595/1.jpg?4785"
#                                      }
#                                      ))