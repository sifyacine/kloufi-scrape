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

# Convertir le prix vers le DA


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

# Vérifier l existence d une valeur pour la transformer en float


def str_to_float(valeur):

    if not valeur:
        valeur = ""
        return valeur
    else:
        valeur = valeur.replace(",", ".")
        valeur = float(valeur)
        return valeur

# Vérifier l existence d une valeur pour la transformer en float


def str_to_int(valeur):

    if not valeur:
        valeur = ""
        return valeur
    else:
        valeur = int(valeur)
        return valeur


# Vérifier l existence d une valeur pour la transformer en date  ---------  (non utilise ) ----------

def str_to_date(valeur):

    if not valeur:
        valeur = ""
        return valeur
    else:
        # valeur = datetime.strptime(''.join(response.css('h1#Title::text').re("[A-Z].+(\d+\d+\d+\d+)")),'%Y')
        return valeur

# Vérifier l existence d une valeur pour la transformer en float


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
        images_list = []
        description = soup.find("div", class_='markup -mhm -pvl -oxa -sc').text if soup.find("div", class_='markup -mhm -pvl -oxa -sc') else ""
        descriptif_technique_section = soup.find("h2", string="Descriptif technique").find_next("ul") if soup.find("h2", string="Descriptif technique") else None
        as_photo = "Sans photo"
        title = soup.find("div", class_="product-info").find("h2").text if soup.find("div", class_="product-info").find("h2") else ""
        if item['image'] and item['image'] != "/static/images/pas-images.png":
            images_list.append(f"https://www.starmania.dz{item['image']}")
            
        if len(images_list) > 0:
            as_photo = "Avec photo"

        poids_element = soup.find("th", string="Poids Net:")
        poids = poids_element.find_next("td").text.strip() if poids_element else ""

        # Extract numeric weight value
        poids_value_match = re.search(r"(\d+[,.]?\d*)", poids)
        poids_value = poids_value_match.group(1).replace(",", ".") if poids_value_match else ""

        # Extract weight unit (Kg, g, mg, lb)
        poids_unit_match = re.search(r"(\bKg\b|\bg\b|\bmg\b|\blb\b)", poids, re.IGNORECASE)
        poids_unit = poids_unit_match.group(1) if poids_unit_match else ""

        dimensions_element = soup.find("th", string="Dimensions (H / L / P) (mm):")
        dimensions = dimensions_element.find_next("td").text if dimensions_element else ""
        color_element = soup.find("th", string="Couleur:")
        color = color_element.find_next("td").text if color_element else ""
        
        modele = soup.find("span", class_="product-details-ref").text if soup.find("span", class_="product-details-ref") else ""

        item_details = {
            'titre': title if title else "",
            'url': url,
            'etat': "true",
            'livraison': "48 Wilayas",
            'site_origine': "Starmania.dz",
            'transaction': "Vente",
            'category':"electromenager",
            'categorie' : categorie(item['category']) if item['category'] else "",
            'description' : description,
            'date_depot': datetime.now().isoformat(),
            'marque': item['brand'] if item['brand'] else "",
            'modele': modele if modele else "",
            # 'garantie': garantie if garantie else "",
            # 'garantie_unit': garantie_unit if garantie_unit else [],
            'dimension': dimensions,
            # 'type_ecran': re.search(r"(HD|Super AMOLED|OLED|LCD|TFT)", result.html).group(1) if re.search(r"(HD|Super AMOLED|OLED|LCD|TFT)", result.html) else "",
            # 'taille_ecran': str_to_float(item_details_technique.get("Taille de l'écran (pouces)", "")) if item_details_technique.get("Taille de l'écran (pouces)") else "",
            # 'os': os.capitalize() if os else "",
            # 'os_version': os_version if os_version else "",
            'poid': poids_value if poids_value else "",
            'poid_unit': poids_unit if poids_unit else "",
            'couleur' : color,
            # 'processor_cores': re.search(r"(Quad-Core|Octa-Core)", result.html).group(1) if re.search(r"(Quad-Core|Octa-Core)", result.html) else "",
            # 'processor_hz': re.search(r"Vitesse CPU \(GHz\)</div><div class=\"osh-col \">(\S+)</div></div>", result.html).group(1) if re.search(r"Vitesse CPU \(GHz\)</div><div class=\"osh-col \">(\S+)</div></div>", result.html) else "",
            # 'm_interne': re.search(r"Capacit. \(\w+\)</div><div class=\"osh-col \">(\d+)", result.html).group(1) if re.search(r"Capacit. \(\w+\)</div><div class=\"osh-col \">(\d+)", result.html) else "",
            # 'm_interne_unit': re.search(r"Capacit. \((\w+)", result.html).group(1) if re.search(r"Capacit. \((\w+)", result.html) else "",
            # 'ram': ram if ram else "",
            # 'ram_unit': ram_unit if ram_unit else "",
            # 'camera_ar': re.search(r"pixels</div><div class=\"osh-col \">(.*?\S+)</div></div>", result.html).group(1) if re.search(r"pixels</div><div class=\"osh-col \">(.*?\S+)</div></div>", result.html) else [],
            # 'camera_av': re.search(r"(\d+.\d+)\sM.gapixels", result.html).group(1) if re.search(r"(\d+.\d+)\sM.gapixels", result.html) else "",
            'batterie': re.search(r"(\d+) mAh", result.html).group(1) if re.search(r"(\d+) mAh", result.html) else "",
            "prix": item['price'] if item['price'] else "",
            'prix_dec': float(item['price'].replace(" DA", "").replace(",", "").replace("\xa0", "")),
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
# asyncio.run(extract_multimedia_details("https://www.jumia.com.dz/samsung-galaxybook2-750xe-i5-1235u-8256go-ssd-15.6-w11-570099.html",
#                                      {
#                                          "title": "Tefal Appareil \u00e0 cr\u00eapes 6 empreintes, Antiadh\u00e9sif, Thermo-Spot",
#                                          "url": "https://www.jumia.com.dz/tefal-appareil-a-crepes-6-empreintes-antiadhesif-thermo-spot-595765.html",
#                                          "price": "14,500 DA",
#                                          "image": "https://dz.jumia.is/unsafe/fit-in/300x300/filters:fill(white)/product/56/7595/1.jpg?4785"
#                                      }
#                                      ))
