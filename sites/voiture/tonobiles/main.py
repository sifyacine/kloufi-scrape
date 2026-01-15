import json
import asyncio
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
from math import ceil
from scrape_details import scrape_car_details
import sys
sys.setrecursionlimit(10000)

async def scrape_main_page(url, etat):
    global total_pages  # Use global variable to store total pages

    # 1. Define the extraction schema with corrected selectors
    schema = {
        "name": "Car Listings",
        "baseSelector": "div.vehica-car-card__inner",  # Container for each listing
        "fields": [
            {
                "name": "title",
                "selector": "a.vehica-car-card__name",
                "type": "text"
            },
            {
                "name": "url",
                "selector": "a.vehica-car-card__name",
                "type": "attribute",
                "attribute": "href"
            },
            {
                "name": "price",
                "selector": "div.vehica-car-card__price",
                "type": "text"
            },
            {
                "name": "brand",
                "selector": "div.vehica-car-card__info__single:nth-of-type(1)",  
                "type": "text"
            },
            {
                "name": "model",
                "selector": "div.vehica-car-card__info__single:nth-of-type(2)",  
                "type": "text"
            },
            {
                "name": "mileage",
                "selector": "div.vehica-car-card__info__single:nth-of-type(3)",  
                "type": "text"
            },
            {
                "name": "phone_number",
                "selector": "div.vehica-car-card__info__single:nth-of-type(4)",  
                "type": "text"
            },
            {
                "name": "image_url",
                "selector": "div.vehica-car-card__image-bg img",
                "type": "attribute",
                "attribute": "data-srcset"
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
        delay_before_return_html=10
    )

    async with AsyncWebCrawler(verbose=True, config=browser_config) as crawler:
        all_data = []
        base_url = url

        # First page request to determine total pages
        result = await crawler.arun(url=base_url, config=config)

        if not result.success:
            print(f"❌ Failed to scrape first page: {result.error_message}")
            return

        # Extract JSON data
        data = json.loads(result.extracted_content)
        print(f"✅ Extracted {len(data)} car listings from the first page")

        all_data.extend(data)

        # Parse HTML to get total pages
        soup = BeautifulSoup(result.html, 'html.parser')
        total_results = soup.find("div", class_="vehica-inventory-v1__title").text if soup.find("div", class_="vehica-inventory-v1__title") else ""

        # Check if we have a valid numeric result
        total_pages = 0
        if total_results:
            results_match = re.search(r"\d+", total_results.replace("\n", " "))
            try:
                results = int(results_match.group(0))
                total_pages = ceil(results / 12)
            except ValueError:
                print(f"❌ Could not convert total_results to an integer: '{total_results}'")

        # Loop through remaining pages
        for page_number in range(1, total_pages + 1):
            url = f"{base_url}&page={page_number}"
            print(f"🔍 Scraping page {page_number}: {base_url}")

            result = await crawler.arun(url=url, config=config)

            if not result.success:
                print(f"❌ Failed to scrape page {page_number}: {result.error_message}")
                continue

            # Extract JSON data
            data = json.loads(result.extracted_content)
            print(f"✅ Extracted {len(data)} car listings from page {page_number}")

            for item in data:
                try:
                    # Fix image URL extraction
                    await scrape_car_details(item["url"], item, etat)
                    all_data.append(item)  
                except Exception as e:
                    print(f"⚠️ Error processing item: {e}")
                    continue

        # 5. Print and save final collected data
        print(f"🚗 Total cars extracted: {len(all_data)}")
        # print(json.dumps(all_data, indent=2) if all_data else "No data found")

async def scrape_all_categories():
    urls = ["https://tonobiles.com/annonces?etat=neuf", "https://tonobiles.com/annonces?etat=occasion"]
    for url in urls:
        etat = "neuf" if url == urls[0] else "occasion"
        await scrape_main_page(url, etat)
        
# Run the scraper
asyncio.run(scrape_all_categories())