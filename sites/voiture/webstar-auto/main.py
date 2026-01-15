import json
import asyncio
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
from bs4 import BeautifulSoup
from datetime import datetime
import sys
sys.setrecursionlimit(10000)

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
                
        
        all_data = format_data(all_data)
        print(f"🚗 Total cars extracted: {len(all_data)}")

def traitement_prix(prix_dec, prix_unit):
    """
    Convert price based on unit (Millions, Milliards).
    """
    try:
        prix_dec = float(prix_dec)
        if prix_unit == "Millions":
            return prix_dec * 1_000_000
        elif prix_unit == "Milliards":
            return prix_dec * 1_000_000_000
        return prix_dec
    except (ValueError, TypeError):
        return 0  # Default to 0 if conversion fails

        
def format_data(cars):
    cleaned_cars = []
    for car in cars:
        if 'prix' in car and 'titre' in car:
            car['images'] = [f"http://webstar-auto.com/fr{car['images'].replace(".", "")}"]
            as_photo = "Sans photo"
            if len(car['images']) > 0:
                as_photo = "Avec photo"
                
            print("car", car)
            car_data = {
                'images': car['images'] if car['images'] else [],
                'titre': car['titre'] if car['titre'] else "",
                'prix': car['prix'] if car['prix'] else "",
                "site_origine": "Tonobiles.com",
                "url": car['url'],
                "prix": car['prix'] if car['prix'] else "",
                "prix_unit": "DA" if car['prix'] else "",
                "prix_value": car['prix'],
                "prix_dec": float(car['prix'].replace(" ", "")) if car['prix'] else 0,
                "etat": "neuf",
                "date_crawl": datetime.now().isoformat(),
                "status": "200",
                "as_photo": as_photo,
                "date_depot": datetime.now().isoformat(),
                "category": "voiture",
            }
            cleaned_cars.append(car_data)
            print(json.dumps(car, indent=2))
    
    print(f"🚗 Total cars extracted: {len(cleaned_cars)}")
    return cleaned_cars
    

# Run the extraction asynchronously
asyncio.run(scrape_main_page())
