import json
import asyncio
import sys
import os
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from datetime import datetime
from urllib.parse import unquote, urljoin
import locale
import re

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from utils.immobilier import ImmobilierUtils

try:
    sys.path.insert(1, '../../../insert2db')
    from insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] Inserting data to ES index '{index}'")

        
def extract_superficie(page_text):
    match = re.search(r"(\d+(\.\d+)?)\s*(m²|m2)", page_text)
    if match:
        superficie_value = match.group(1)  # Extract numerical value (e.g., 930, 120.5)
        superficie_unit = match.group(3)   # Extract unit (e.g., "m²" or "m2")
        if superficie_unit == "m2":
            superficie_unit = "m²"
        return superficie_value, superficie_unit
    return "", ""

def extract_rooms_number(page_text):
    match = re.search(r"F\d+", page_text)
    if match:
        return match.group(0).replace("F", "")
    return ""

def extract_etage_number(page_text):
    """
    Extracts the TOTAL number of floors in a building.
    Supports formats like:
    - "R+2" → 3 floors
    - "rez de chaussée + 3 étages" → 4 floors
    - "Immeuble de 5 étages" → 5 floors
    """
    # Standard format: "R+X" or "RDC+X"
    match = re.search(r"(?:RDC|R)\s*\+?\s*(\d+)", page_text)
    if match:
        return str(int(match.group(1)) + 1)  # Convert "R+X" to total floors (X+1)

    # Alternative format: "X étages" (e.g., "5 étages")
    match = re.search(r"(\d+)\s*(?:étages|étage)", page_text)
    if match:
        return match.group(1)

    return ""

def str_to_float(valeur):

    if not valeur:
        valeur = ""
        return valeur
    else:
        valeur = valeur.replace(",", ".")
        valeur = float(valeur)
        return valeur

def convert_french_date_to_iso(french_date_str):
    try:
        # Remove the prefix "Mis à jour le"
        clean_date_str = re.sub(r"Mis à jour le ", "", french_date_str).strip()

        # Ensure correct mapping for French months to English (for parsing)
        month_mapping = {
            "janvier": "January", "février": "February", "mars": "March",
            "avril": "April", "mai": "May", "juin": "June",
            "juillet": "July", "août": "August", "septembre": "September",
            "octobre": "October", "novembre": "November", "décembre": "December"
        }

        # Replace French month with English equivalent
        for fr_month, en_month in month_mapping.items():
            if fr_month in clean_date_str:
                clean_date_str = clean_date_str.replace(fr_month, en_month)
                break  # Replace once and exit loop

        # Convert to datetime object
        date_obj = datetime.strptime(clean_date_str, "%B %d, %Y : %I:%M %p")

        # Return only the date in ISO format
        return date_obj.date().isoformat()

    except Exception as e:
        print(f"Error parsing date: {e} \n Input: {french_date_str}")
        return None

    except Exception as e:
        print(f"Error parsing date: {e} \n Input: {french_date_str}")
        return None

async def extract_property_details(url, item):
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
                delay_before_return_html=3
            ),
        )

        # Ensure the page rendered successfully
        if not result.success:
            raise Exception("Failed to crawl the page")
        
        soup = BeautifulSoup(result.html, 'html.parser')
        description_title = soup.find("h2", string="Description")
        description_content = description_title.find_next("div").text if description_title else ""
        numero_element = soup.find("strong", string="Identifiant de l'annonce:")
        numero = numero_element.find_next("span").text if numero_element else ""
        date_depot_element = soup.find("span", class_="small-text grey").text if soup.find("span", class_="small-text grey") else ""
        date_depot_iso = convert_french_date_to_iso(date_depot_element) if date_depot_element else ""
        city = soup.find("li", class_="detail-city").find("span").text if soup.find("li", class_="detail-city") else ""
        wilaya = soup.find("li", class_="detail-state").find("span").text if soup.find("li", class_="detail-city") else ""
        rooms = ""
        images_element = soup.find("div", class_="top-gallery-section")
        images_list = []
        as_photo = "Sans photo"
        price = item['price'] if item['price'] else ""
        price_dec = 0
        as_price = "Sans prix"
        etage = ""
        
        if price:
            price_unit = re.search(r"(Millions|Milliards)", price)
            if price_unit != None and price_unit != "":
                price_unit = price_unit.group(0)
                price_num_str = re.sub(r"[^\d.,]", "", price.replace(price_unit, "").replace("DA", ""))
                price_dec = ImmobilierUtils.traitement_prix(price_num_str, price_unit)
                as_price = "Avec prix"
            else:
                price_cleaned = price.replace("DA", "").replace(" ", "").replace(".", "")
                price_dec = ImmobilierUtils.traitement_prix(price_cleaned, "")
                if price_dec > 0:
                    as_price = "Avec prix"
                else:
                    as_price = "Sans prix"

        if images_element:
            images = images_element.find_all("img")
            images_list = [image["src"] for image in images if "src" in image.attrs]
            as_photo = "Avec photo"

        if description_content:
            surface_value, surface_unit = extract_superficie(description_content)
            rooms = extract_rooms_number(description_content)
            etage = extract_etage_number(description_content)
            if etage == "":
                etage = extract_etage_number(item['title'])
        
        if item['status'].lower() == "cherche achat" or item['status'].lower() == "cherche-achat":
            item['status'] = "Cherche-achat"
        elif item['status'].lower() == "cherche location" or item['status'].lower() == "cherche-location":
            item['status'] = "Cherche-location"

        property_details = {
            "titre": item['title'] if item['title'] else "",
            'url': url,
            'site_origine': "Hebdoimmobilier-dz.com",
            'date_crawl': datetime.now().isoformat(),
            'numero': numero.split("-")[1].strip() if numero else "",
            "date_depot": date_depot_iso,
            'transaction': item['status'] if item['status'] else "",
            'category': "immobilier",
            'bien': ImmobilierUtils.convert_property_type(item['property_type']) if item['property_type'] else "",
            'superficie': ImmobilierUtils.parse_float_or_none(surface_value) if surface_value else "",
            'superficie_unit': surface_unit if surface_unit else "",
            'nb_pieces': rooms if rooms else "",
            'description': description_content if description_content else "",
            'prix': price,
            'prix_dec': price_dec,
            'prix_unit': "DA" if price != "" else "",
            'images': images_list,
            'adresse': f"{city}, {wilaya}" if city and wilaya else "",
            'wilaya': wilaya,
            "commune": city,
            "etage": etage if etage else "",
            'status': 200,
            'date_verif': datetime.now().isoformat(),
            'as_photo': as_photo,
            "as_prix": as_price
        }

        # Output the results
        print(json.dumps(property_details, indent=4))

        insert_data_to_es(property_details, "immobilier")

# Example of how you might call this function
# asyncio.run(extract_property_details("https://www.hebdoimmobilier-dz.com/property/vend-villa-3/", {
#     "title": "locaux de 600m2 situé a el mouradia alger",
#     "status": "Vente",
#     "property_type": "Terrain",
#     'price': "14.000.000 DA",
# }))
