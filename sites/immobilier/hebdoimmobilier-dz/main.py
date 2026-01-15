import json
import asyncio
import requests
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
from scrape_details import extract_property_details
import sys
sys.setrecursionlimit(10000)

async def scrape_main_page():
    # 1. Define a simple extraction schema for property details
    schema = {
        "name": "Property Listings",
        "baseSelector": "div.d-flex.align-items-center.h-100",  # This is the repeating container for each listing
        "fields": [
            {
                "name": "title",
                "selector": "h2.item-title > a",  # Selector for the title of the property
                "type": "text"
            },
            {
                "name": "url",
                "selector": "h2.item-title > a",  # Selector for the URL of the property
                "type": "attribute",
                "attribute": "href"
            },
            {
                "name": "price",
                "selector": "ul.item-price-wrap > li.item-price",  # Selector for the price
                "type": "text"
            },
            {
                "name": "status",
                "selector": "a.label-status",  # Selector for the property status (e.g., for sale)
                "type": "text"
            },
            {
                "name": "property_type",
                "selector": "li.h-type",
                "type": "text"
            },
            {
                "name": "details_link",
                "selector": "a.btn-item",
                "type": "attribute",
                "attribute": "href"
            },
            {
                "name": "agent_name",
                "selector": "div.item-author > a",  # Selector for the agent name
                "type": "text"
            },
            {
                "name": "date_posted",
                "selector": "div.item-date",  # Selector for the date the listing was posted
                "type": "text"
            },
            {
                "name": "image_url",
                "selector": "img.wp-post-image",  # Selector for the image URL
                "type": "attribute",
                "attribute": "src"
            }
        ]
    }

    # 2. Create the extraction strategy using the defined schema
    extraction_strategy = JsonCssExtractionStrategy(schema)

    # 3. Set up your crawler config (adjust if needed)
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,  # Define cache behavior
        extraction_strategy=extraction_strategy,
    )
    
    browser_config = BrowserConfig(
        headless=False,  # Set to True if you do not need to see the browser
        verbose=True,
        browser_type="chromium",
    )
    async with AsyncWebCrawler(config=browser_config) as crawler:
        all_data = []  # Initialize a list to collect data from all pages
        url = "https://www.hebdoimmobilier-dz.com/search-results/?type%5B0%5D&status%5B0%5D&states%5B0%5D&location%5B0%5D&keyword="  # Starting URL

        # Scrape the first page to get total results
        first_page_result = await crawler.arun(
            url=url,
            config=config,
        )

        if not first_page_result.success:
            print(f"Crawl failed for {url}: {first_page_result.error_message}")
            return

        # 4. Parse the first page HTML to get the total number of results
        # soup = BeautifulSoup(first_page_result.html, 'html.parser')
        # total_results_text = soup.find("div", class_="d-flex align-items-center mb-3").find("strong").text
        # total_results = int(total_results_text.split(" ")[0])  # Extract the number from "5106 Résultats trouvés"
        # print(f"Total results found: {total_results}")

        # 5. Start scraping the listings page-by-page
        page_number = 1
        while True:
            print(f"Scraping page {page_number}: {url}")

            # Run the crawl and extraction for the current page
            result = await crawler.arun(
                url=url,
                config=config
            )

            if not result.success:
                print(f"Crawl failed for {url}: {result.error_message}")
                break

            # 6. Parse the extracted JSON and add to all_data
            data = json.loads(result.extracted_content)
            print(f"Extracted {len(data)} property listings from page {page_number}")
            for item in data:
                try:
                    await extract_property_details(item['url'], item)
                except Exception as e:
                    print(f"Error extracting property details: {e}")
                    continue

            # 7. Find the next page URL (check for 'Next' button) using BeautifulSoup
            soup = BeautifulSoup(result.html, 'html.parser')
            next_button = soup.find("a", class_="page-link", attrs={"aria-label": "Next"})

            if next_button and 'href' in next_button.attrs:
                next_page_url = next_button['href']
                url = next_page_url  # Update the URL to the next page
                page_number += 1  # Increment the page number
                print(f"Next page found: {url}")
            else:
                print("No more pages to scrape.")
                break

        # 8. Print the final collected data
        print(f"Total properties extracted: {len(all_data)}")
        print(json.dumps(all_data, indent=2) if all_data else "No data found")

# Run the extraction asynchronously
asyncio.run(scrape_main_page())
