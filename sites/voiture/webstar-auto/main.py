import json
import asyncio
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
from bs4 import BeautifulSoup
from datetime import datetime
import sys, os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from utils.voiture import VoitureUtils

try:
    from insert2db.insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] Inserting data to ES index '{index}'")

async def scrape_main_page():
    global total_pages  # Use global variable to store total pages

    # 1. Define the extraction schema with corrected selectors
    schema = {
        "name": "Car Listings",
        "baseSelector": "div.item_okaz_block",  # Container for each car listing
        "fields": [
            {
                "name": "titre",
                "selector": "a[title] h3",
                "type": "text"
            },
            {
                "name": "url",
                "selector": "a[title]",
                "type": "attribute",
                "attribute": "href"
            },
            {
                "name": "prix",
                "selector": "h4.prix span:last-child",  # Target the price inside <span> tag
                "type": "text"
            },
            {
                "name": "images",
                "selector": "li.item_image img",
                "type": "attribute",
                "attribute": "src"
            },
            {
                "name": "marque",
                "selector": "h4 a[title]",
                "type": "text"
            }
        ]
    }

    # 2. Create extraction strategy
    extraction_strategy = JsonCssExtractionStrategy(schema, verbose=True)

    browser_config = BrowserConfig(
        headless=True,  # Set to True if you do not need to see the browser
        verbose=True,
        browser_type="chromium",
    )

    # 3. Crawler configuration
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=extraction_strategy,
        delay_before_return_html=3
    )

    async with AsyncWebCrawler(verbose=True, config=browser_config) as crawler:
        all_data = []
        base_url = "https://www.webstar-auto.com/"

        # First page request to determine total pages
        result = await crawler.arun(url=base_url, config=config)

        if not result.success:
            print(f"❌ Failed to scrape first page: {result.error_message}")
            return

        # Extract JSON data from the first page
        data = json.loads(result.extracted_content)
        print(f"✅ Extracted {len(data)} car listings from the first page")

        all_data.extend(data)

        # Parse HTML to get total pages
        soup = BeautifulSoup(result.html, 'html.parser')
        total_pages_elem = soup.find_all("a", class_="vehica-pagination__page")  # Corrected pagination selector
        total_pages = int(total_pages_elem[-1].text) if total_pages_elem else 1
        print(f"📄 Total pages found: {total_pages}")

        # Loop through remaining pages
        for page_number in range(2, total_pages + 1):
            url = f"{base_url}?page={page_number}"
            print(f"🔍 Scraping page {page_number}: {url}")

            result = await crawler.arun(url=url, config=config)

            if not result.success:
                print(f"❌ Failed to scrape page {page_number}: {result.error_message}")
                continue

            # Extract JSON data from the page
            data = json.loads(result.extracted_content)
            print(f"✅ Extracted {len(data)} car listings from page {page_number}")

            for item in data:
                all_data.append(item)
                
        
        format_data(all_data)
        print(f"🚗 Total cars extracted: {len(all_data)}")

        
def format_data(cars):
    cleaned_cars = []
    for car in cars:
        if 'prix' in car and 'titre' in car:
            # Fix image URL logic - previously it was replacing . with empty which seems wrong for extensions
            # Assuming relative path needs domain prepended
            img_src = car.get('images', '')
            if img_src and not img_src.startswith('http'):
                 img_src = f"https://www.webstar-auto.com{img_src}" # Corrected domain scheme
            
            car['images'] = [img_src] if img_src else []
            
            as_photo = "Sans photo"
            if len(car['images']) > 0:
                as_photo = "Avec photo"
                
            price_raw = car.get('prix', '')
            _, price_value_str, price_decimal, price_unit = VoitureUtils.parse_price(price_raw)

            print("car", car)
            car_data = {
                'images': car['images'],
                'titre': car['titre'] if car['titre'] else "",
                'prix': price_raw,
                "site_origine": "Webstar-auto.com",
                "url": car['url'],
                "prix_unit": price_unit,
                "prix_value": price_value_str,
                "prix_dec": price_decimal,
                "etat": "neuf", # Assuming default based on original code, but could be occasion
                "date_crawl": datetime.now().isoformat(),
                "status": "200",
                "as_photo": as_photo,
                "date_depot": datetime.now().isoformat(),
                "category": "voiture",
                "marque": car.get('marque', '')
            }
            cleaned_cars.append(car_data)
            # print(json.dumps(car_data, indent=2))
            insert_data_to_es(car_data, "voiture")
    
    return cleaned_cars
    

# Run the extraction asynchronously
if __name__ == "__main__":
    asyncio.run(scrape_main_page())
