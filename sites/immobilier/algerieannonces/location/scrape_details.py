from datetime import datetime, timedelta
import re
import json
import asyncio
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from urllib.parse import unquote, urljoin
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../')))
from utils.immobilier import ImmobilierUtils

try:
    sys.path.insert(1, '../../../../insert2db')
    from insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] Inserting data to ES index '{index}'")

def extract_superficie(page_text):
    match = re.search(r"(\d+(\.\d+)?)\s*(m²|m2)", page_text)
    if match:
        # Extract numerical value (e.g., 930, 120.5)
        superficie_value = match.group(1)
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
        # Convert "R+X" to total floors (X+1)
        return str(int(match.group(1)) + 1)

    # Alternative format: "X étages" (e.g., "5 étages")
    match = re.search(r"(\d+)\s*(?:étages|étage)", page_text)
    if match:
        return match.group(1)

    return ""


# Mapping French months to English months
month_translation = {
    "Jan": "Jan", "Fév": "Feb", "Mar": "Mar", "Avr": "Apr", "Mai": "May", "Juin": "Jun",
    "Juil": "Jul", "Août": "Aug", "Sept": "Sep", "Oct": "Oct", "Nov": "Nov", "Déc": "Dec"
}

# Function to convert the input string to "year-month-day" format
def format_date(date_str):
    now = datetime.now()
    
    if "Aujourd'hui" in date_str:  # If the string contains "Aujourd'hui"
        return now.strftime("%Y-%m-%d")
    
    if "Hier" in date_str:  # If the string contains "Hier"
        yesterday = now - timedelta(days=1)
        return yesterday.strftime("%Y-%m-%d")
    
    # Handle the case where the date is in "day month year hour:minute" format (e.g., "13 Jan 202511:02")
    try:
        # Try to parse the date and time if it's in this format
        date_time_obj = datetime.strptime(date_str, "%d %b %Y%H:%M")
        return date_time_obj.strftime("%Y-%m-%d")
    except ValueError:
        pass
    
    # Handle the case where the date is in "day month year hour:minute" in French (e.g., "18 Mai 202112:09")
    for french_month, english_month in month_translation.items():
        if french_month in date_str:
            try:
                # Replace the French month with English month
                date_str = date_str.replace(french_month, english_month)
                date_time_obj = datetime.strptime(date_str, "%d %b %Y%H:%M")
                return date_time_obj.strftime("%Y-%m-%d")
            except ValueError:
                pass

    # If no matching pattern is found, return None or raise an exception
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
        description_title = soup.find("strong", string="Detail de l'annonce :")
        description_content = description_title.find_parent().text.replace(
            "Detail de l'annonce :", "") if description_title else ""
        numero = ""
        city = item['location'].split(
            "/")[1].strip() if item['location'] and len(item['location'].split("/")) > 0 else ""
        wilaya = item['location'].split(
            "/")[0].strip() if item['location'] else ""
        rooms = ""
        images_element = soup.find("div", class_="ad-gallery")
        images = images_element.find(
            "div", class_="ad-nav") if images_element else None
        images_list = []
        as_photo = "Sans photo"
        price = item['price'] if item['price'] else ""
        price_dec = 0
        as_price = "Sans prix"
        info_holder = soup.find("ul", class_="info-holder")
        views = ""
        etage = ""
        surface_value = ""
        surface_unit = ""
        date_depot = ""
        property_type = ImmobilierUtils.convert_property_type(item['property_type']) if item['property_type'] else ""

        if item["date_posted"]:
            # 09 Déc 2024
            date_depot = format_date(item["date_posted"])
            print("Date depot", date_depot)

        if info_holder:
            views = re.search(r"Vue:\s*(\d+)", info_holder.text).group(
                1) if re.search(r"Vue:\s*(\d+)", info_holder.text) else ""
            numero = re.search(r"Annonce N°:\s*(\d+)", info_holder.text).group(
                1) if re.search(r"Annonce N°:\s*(\d+)", info_holder.text) else ""

        if price:
            price_unit = re.search(r"(Millions|Milliards)", price)
            if price_unit != None and price_unit != "":
                price_unit = price_unit.group(0)
                # Parse numeric part from price string to pass to utils
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

        if images:
            images = images.find_all("img")
            images_list = ["https://www.algerieannonces.com/" + image["src"]
                           for image in images if "src" in image.attrs]
            as_photo = "Avec photo"

        if description_content:
            surface_value, surface_unit = extract_superficie(
                description_content)
            rooms = extract_rooms_number(description_content)
            etage = extract_etage_number(description_content)
            if etage == "":
                etage = extract_etage_number(item['title'])

        property_details = {
            "titre": item['title'] if item['title'] else "",
            'url': url,
            'site_origine': "Algerieannonces.com",
            'date_crawl': datetime.now().isoformat(),
            'numero': numero if numero else "",
            "date_depot": date_depot if date_depot else "",
            'transaction': "Location",
            'category': "immobilier",
            'bien': property_type,
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
            "nb_vues": views if views else "",
            'status': 200,
            'date_verif': datetime.now().isoformat(),
            'as_photo': as_photo,
            "as_prix": as_price
        }

        # Output the results
        print(json.dumps(property_details, indent=4))

        insert_data_to_es(property_details, "immobilier")

# Example of how you might call this function
# asyncio.run(extract_property_details("https://www.algerieannonces.com/categorie/319/Villas-Maisons-Riads/annonce/58478/Vente-villa-Saint-Hubert.html", {
#     "title": "locaux de 600m2 situé a el mouradia alger",
#     "status": "Vente",
#     "property_type": "Terrain",
#     'price': "14.000.000 DA",
#     'location': "Alger / ",
#     'date_posted': "30 Déc 202409:14"
# }))
