import json
import asyncio
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from datetime import datetime
from urllib.parse import unquote, urljoin
import sys
sys.path.insert(1, '../../../global')
from insert_scrape import insert_data_to_es

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
        prix = ""

def convert_property_type(raw_key):
    valid_types = {
        "Appartement", "Villa", "Local", "Terrain", "Studio", "Hangar",
        "Niveau de villa", "Immeuble", "Duplex", "Carcasse", "Autre",
        "Bungalow", "Terrain agricole", "Usine", "Chalet", "Commerce",
        "Locaux", "Bureau", "Autres", "Salle", "Hostel", "Dortoir",
        "Ferme", "Hotel", "Triplex", "Maison", "Pavillon", "Auberge", "Résidence"
    }

    normalization_map = {
        "bungalow": "Bungalow",
        "bungalows": "Bungalow",
        "niveau": "Niveau-de-villa",
        "niveau de villa": "Niveau-de-villa",
        "terrain-agricole": "Terrain agricole",
        "terrain agricole": "Terrain agricole",
        "appartements": "Appartement",
        "immeubles": "Immeuble",
        "commerce, local": "Commerce",
        "bureaux": "Bureau",
        "ferme, terrain": "Ferme",
        "residence": "Résidence",
        "résidence": "Résidence",
        "Niveau": "Niveau-de-villa",
        "Usine": "Industriel",
        "Commerce": "Local",
        "Locaux": "Local",
        "Bureau": "Local",
        "Autres": "Autre",
        "Hostel": "Hotel",
        "Pavillon": "Villa",
        "Appartements": "Appartement",
        "Dortoir": "Hotel",
        "Ferme": "Terrain-agricole",
        "Triplex": "Duplex",
        "Auberge": "Hotel",
        "Commerce, Local": "Local",
        "Maison": "Villa",
        "Safari": "Hotel",
        "Hangar": "Industriel"
    }

    if not raw_key or not isinstance(raw_key, str):
        return ""

    cleaned = raw_key.strip().lower()

    normalized = normalization_map.get(cleaned, cleaned).capitalize()
    if normalized in valid_types:
        return normalized

    lowered = raw_key.lower()
    for key, value in normalization_map.items():
        if key in lowered:
            normalized_candidate = value
            if normalized_candidate in valid_types:
                return normalized_candidate

    for valid in valid_types:
        if valid.lower() in lowered:
            return valid

    return ""

async def extract_property_details(url, transaction, bien):
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
            javascript_enabled=True,  # Enable JS for dynamic content
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,  # Skip cache to get fresh content
                delay_before_return_html=3  # Allow time for JS to render
            ),
        )

        # Ensure the page rendered successfully
        if not result.success:
            raise Exception("Failed to crawl the page")

        # Use BeautifulSoup to parse the HTML
        soup = BeautifulSoup(result.html, "html.parser")

        # Extract details with escaped selectors
        title = soup.find("h1", class_="elementor-heading-title elementor-size-xl")
        description = soup.find("section", class_="elementor-section elementor-inner-section elementor-element elementor-element-8a6891f elementor-section-boxed elementor-section-height-default elementor-section-height-default")
        images_container = soup.find("div", class_="swiper-with-thumbs")
        images = images_container.find_all("img") if images_container else None
        images_list = []
        with_price = "Sans prix"
        price_dec = 0
        price = ""
        price_element = soup.find("div", class_="elementor-heading-title elementor-size-xl")
        surface_value = soup.find("div", class_="elementor-element elementor-element-140ec08e elementor-widget elementor-widget-heading")
        rooms = soup.find("div", class_="elementor-element elementor-element-dd60191 elementor-widget elementor-widget-heading")
        surface_unit = "M²"
        date_depot  = soup.find("span", class_="elementor-divider__text elementor-divider__element")
        address = ""
        address_element = soup.find("svg", class_="e-font-icon-svg e-fas-map-marker-alt")
        wilaya = ""
        as_photo = "Sans photo"
        numero = url.split("/")[-1].split("-")[0]
        
        if images is not None and len(images) > 0:
            images_list = [image["src"] for image in images if "src" in image.attrs]
            as_photo = "Avec photo"
        
        if price_element:
            price = price_element.text.strip()
            try:
                price_dec, price_unit = price.replace("/M²", "").split(" ")
                price_dec = traitement_prix(price_dec, price_unit)
                with_price = "Avec prix"
            except ValueError as e:
                print(f"Error: Unable to convert price to integer")
                price = ""
                price_dec = 0
                with_price = "Sans prix"
        
        if address_element:
            address_parent = address_element.find_parent("span")
            address = address_parent.find_next("span").text.strip()
            if address:
                wilaya = address.split("-")[1].strip()
        
        if date_depot:
            date_depot = date_depot.text.strip().replace("Publié le", "").strip()
            date_depot_obj = datetime.strptime(date_depot, "%d/%m/%Y")
            date_depot_formatted = date_depot_obj.strftime("%Y-%m-%d")
        
        property_details = {
            "titre": title.text.strip() if title else "",
            'url': url,
            'site_origine': "Beytic.com",
            'date_crawl': datetime.now().isoformat(),
            'numero': numero,
            "date_depot": date_depot_formatted if date_depot else "",
            'transaction': transaction,
            'category': "immobilier",
            'bien': bien if bien else "",
            'superficie': surface_value.text.strip() if surface_value else "",
            'superficie_unit': surface_unit,
            'nb_pieces': rooms.text.strip().lower().replace("f", "") if rooms else "",
            'description': description.text.strip() if description else "",
            'prix': price,
            'prix_dec': price_dec,
            'prix_unit': "DA" if price != "" else "",
            'images': list(set(images_list)),
            'adresse': address,
            'wilaya': wilaya,
            'status': 200,
            'date_verif': datetime.now().isoformat(),
            'as_photo': as_photo,
            "as_prix": with_price
        }

        # Output the results
        print(json.dumps(property_details, indent=4))
        insert_data_to_es(property_details, "immobilier")

# Run the asynchronous function
# asyncio.run(extract_property_details("https://www.beytic.com/annonces-immobilieres/79465-vente-terrain-sidi-merouane-mila", transaction="Location", bien="Appartement"))
