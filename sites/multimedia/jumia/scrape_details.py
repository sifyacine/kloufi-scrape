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


async def extract_multimedia_details(url, item):
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
        images_element = soup.find("div", class_='-ptxs -pbs')
        images_list = []
        description = soup.find("div", class_='markup -mhm -pvl -oxa -sc').text if soup.find("div", class_='markup -mhm -pvl -oxa -sc') else ""
        descriptif_technique_section = soup.find("h2", string="Descriptif technique").find_next("ul") if soup.find("h2", string="Descriptif technique") else None
        as_photo = "Sans photo"
        categorie_element = soup.find("div", class_="brcbs col16 -pts -pbm")

        # Extract the category text
        categorie_text = categorie_element.find_all("a")[2].text if categorie_element and len(categorie_element.find_all("a")) > 2 else ""
        item_details_technique = {}
        
        if images_element:
            images = images_element.find_all('img')
            for image in images:
                src = image.get('src')
                src_start = src.split("/filters")[0]
                if src_start == "https://dz.jumia.is/unsafe/fit-in/500x500" and src not in images_list:
                    images_list.append(src)
            
            if len(images_list) > 0:
                as_photo = "Avec photo"
        
        if descriptif_technique_section:
            li_elements = descriptif_technique_section.find_all("li", class_="-pvxs")
            for li in li_elements:
                span = li.find("span", class_="-b")
                if span:
                    key = span.text.strip()
                    value = li.text.split(":")[-1].strip()
                    item_details_technique[key] = value
            
            print(json.dumps(item_details_technique, indent=4))
            
        product_characteristics_section = soup.find("div", class_="card-b -fh")
        characteristics = {}
        os = ""
        os_version = ""
        os_match = re.search(r"(windows\s*(\d{1,2}[\.\d+]*)?|macos\s*(\d{1,2}[\.\d+]*)?|linux|ubuntu|chrome\s*os)", result.html.lower())
        if os_match:
            os = os_match.group(1) if os_match.group(1) else ""
            os_version = os_match.group(2) if os_match.group(2) else ""
        else:
            os = ""
            os_version = ""

        ram = ""
        ram_unit = ""
        ram_match = re.search(r"RAM\s*(\d+)\s*(GO|GB)\s*([A-Za-z0-9]+)\s*(\d{4,6})", result.html)

        if ram_match:
            ram = ram_match.group(1)
            ram_unit = ram_match.group(2)            
        else:
            ram = ""
            ram_unit = ""
            
        garantie = ""
        garantie_unit = ""
        # meses ou anos
        garantie_match = re.search(r"(\d+)\s(Mois|Ans)", result.html)
        if garantie_match:
            garantie = garantie_match.group(1)
            garantie_unit = garantie_match.group(2)

        if product_characteristics_section:
            table_rows = product_characteristics_section.find_all("tr")
            for row in table_rows:
                columns = row.find_all("td")
                if len(columns) == 2:
                    key = columns[0].text.strip()
                    value = columns[1].text.strip()
                    characteristics[key] = value
        print(json.dumps(characteristics, indent=4))
        
        dimensions_taille_match = re.search(r"Dimensions \(.*?\S+\)(.*?\S+)", result.html)
        dimensions_from_item = item_details_technique.get("Taille (Longueur x Largeur x Hauteur cm)") if item_details_technique.get("Taille (Longueur x Largeur x Hauteur cm)") else ""
        dimensions = ""
                                                                                
        if dimensions_from_item != "" and dimensions_from_item:
            dimensions = dimensions_from_item
            if not dimensions or dimensions == "":
                dimensions = dimensions_taille_match.group(1) if dimensions_taille_match else ""

        type_ecran_match = re.search(r"(HD|Super AMOLED|OLED|LCD|TFT)", item["title"] if item["title"] else "")
        processor_cores_match = re.search(r"(Quad-Core|Octa-Core)", result.html)
        processor_hz_match = re.search(r"Vitesse CPU \(GHz\)\s*([\d\.]+)", result.html)
        m_interne_match = re.search(r"Capacité \(\w+\):?\s*(\d+)", result.html)
        m_interne_unit_match = re.search(r"Capacité \((\w+)\)", result.html)
        camera_ar_match = re.search(r"(\d+)\s?(MP|Mégapixels)", result.html)
        camera_av_match = re.search(r"(\d+\.\d+)\sM.gapixels", result.html)
        batterie_match = re.search(r"(\d+)\s*mAh", result.html)
        
        if item["price"] != "" and item["price"].split("-") and len(item["price"].split("-")) > 1:
            item["price"] = item["price"].split("-")[0].strip()

        item_details = {
            'titre': item['title'] if item['title'] else "",
            'url': url,
            'etat': "true",
            'livraison': "48 Wilayas",
            'site_origine': "Jumia.dz",
            'transaction': "Vente",
            'category':"multimedia",
            'categorie' : categorie(categorie_text) if categorie_text else "",
            'description' : description,
            'date_depot': datetime.now().isoformat(),
            'marque': re.search(r'Produits similaires par (\w+\s?\w+?)</', result.html).group(1) if re.search(r'Produits similaires par (\w+\s?\w+?)</', result.html) else "",
            'modele': re.search(r'<span class="-b">Modèle</span>:?\s?(\w+\s?\w+?)</li>', result.html).group(1) if re.search(r'<span class="-b">Modèle</span>:?\s?(\w+\s?\w+?)</li>', result.html) else "",
            'garantie': garantie if garantie else "",
            'garantie_unit': garantie_unit if garantie_unit else [],
            'dimension': dimensions,
            'taille_ecran': str_to_float(item_details_technique.get("Taille de l'écran (pouces)", "")) if item_details_technique.get("Taille de l'écran (pouces)") else "",
            'os': os.capitalize() if os else "",
            'os_version': os_version if os_version else "",
            'poid': item_details_technique.get("Poids (kg)", "") if item_details_technique.get("Poids (kg)") else "",
            'couleur' : item_details_technique.get("Couleur", "") if item_details_technique.get("Couleur") else "",
            'poid_unit': "kg" if item_details_technique.get("Poids (kg)") else "",
            'ram': ram if ram else "",
            'ram_unit': ram_unit if ram_unit else "",
            'prix_dec': float(item['price'].replace(" DA", "").replace(",", "")),
            'prix_unit': "DA",
            'images': images_list,
            'adresse': "Toute l'Algérie",
            'status': 200,
            'date_crawl': datetime.now().isoformat(),
            'date_verif': datetime.now().isoformat(),
            'as_photo': as_photo,
            'as_prix': "Avec prix" if item['price'] and item['price'] != "" else "Sans prix",
            'type_ecran': type_ecran_match.group(1) if type_ecran_match else "",
            'processor_cores': processor_cores_match.group(1) if processor_cores_match else "",
            'processor_hz': processor_hz_match.group(1) if processor_hz_match else "",
            'm_interne': m_interne_match.group(1) if m_interne_match else "",
            'm_interne_unit': m_interne_unit_match.group(1) if m_interne_unit_match else "",
            'camera_ar': camera_ar_match.group(1) if camera_ar_match else "",
            'camera_av': camera_av_match.group(1) if camera_av_match else [],
            'batterie': batterie_match.group(1) if batterie_match else "",
            # 'email': re.search(r'[\w\.-]+@[\w\.-]+', result.html).group()
        }

        # Output the results
        print(json.dumps(item_details, indent=4))
        insert_data_to_es(item_details, "multimedia")

# Example of how you might call this function
# asyncio.run(extract_multimedia_details("https://www.jumia.com.dz/jbl-casque-sans-fil-supra-auriculaire-593734.html",
#                                      {
#                                          "title": "Tefal Appareil \u00e0 cr\u00eapes 6 empreintes, Antiadh\u00e9sif, Thermo-Spot",
#                                          "url": "https://www.jumia.com.dz/tefal-appareil-a-crepes-6-empreintes-antiadhesif-thermo-spot-595765.html",
#                                          "price": "1,000 DA - 1,500 DA",
#                                          "image": "https://dz.jumia.is/unsafe/fit-in/300x300/filters:fill(white)/product/56/7595/1.jpg?4785"
#                                      }
#                                      ))
