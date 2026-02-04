import json
import asyncio
import sys
import os
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from datetime import datetime
from urllib.parse import unquote, urljoin

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../')))
from utils.immobilier import ImmobilierUtils

try:
    from insert2db.insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] Inserting data to ES index '{index}'")

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
                price_str, price_unit = price.replace("/M²", "").split(" ")
                price_dec = ImmobilierUtils.traitement_prix(price_str, price_unit)
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
            'bien': ImmobilierUtils.convert_property_type(bien) if bien else "",
            'superficie': ImmobilierUtils.parse_float_or_none(surface_value.text.strip()) if surface_value else "",
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
