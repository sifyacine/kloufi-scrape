import asyncio
import json
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
from datetime import datetime
from scrape_details import extract_multimedia_details

async def scrape_main_page():
    # Define the extraction schema for WebSoog product listings
    schema = {
        "name": "Product Listings",
        "baseSelector": "div.product-miniature.js-product-miniature",
        "fields": [
            {
                "name": "title",
                "selector": "h5.product-name a",
                "type": "text"
            },
            {
                "name": "url",
                "selector": "h5.product-name a",
                "type": "attribute",
                "attribute": "href"
            },
            {
                "name": "price",
                "selector": "span.price.product-price",
                "type": "text"
            },
            {
                "name": "old_price",
                "selector": "span.regular-price",
                "type": "text"
            },
            {
                "name": "discount",
                "selector": "span.product-flag.discount",
                "type": "text"
            },
            {
                "name": "availability",
                "selector": "span.available",
                "type": "text"
            },
            {
                "name": "image",
                "selector": "div.product-thumbnail img",
                "type": "attribute",
                "attribute": "src"
            }
        ]
    }

    extraction_strategy = JsonCssExtractionStrategy(schema, verbose=True)

    browser_config = BrowserConfig(
        headless=True,  # Set to False if you want to see the browser in action
        text_mode=False,
        browser_type="chromium",
    )

    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=extraction_strategy,
        delay_before_return_html=5  # Ensures JavaScript-rendered content loads
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        all_data = []
        base_url = "https://www.websoog.com/fr/99-electromenager"
        current_page_url = base_url
        page_number = 1

        while True:
            print(f"📌 Scraping page {page_number}: {current_page_url}")

            result = await crawler.arun(url=current_page_url, config=config)

            if not result.success:
                print(f"❌ Failed to scrape {current_page_url}: {result.error_message}")
                break

            extracted_data = json.loads(result.extracted_content)
            print(f"✅ Extracted {len(extracted_data)} products from page {page_number}")

            for item in extracted_data:
                if item.get("url"):
                    print(f"🛒 Extracted item: {item}")
                    all_data.append(item)

                    # Call extract_multimedia_details for each product
                    await extract_multimedia_details(item["url"], item)  # Pass URL and item to multimedia details
                else:
                    print(f"⚠ Skipping item without URL: {item}")
                    continue

            # **🔄 Pagination Handling**
            soup = BeautifulSoup(result.html, "html.parser")
            next_button = soup.find("a", class_="next js-search-link")

            if next_button and "href" in next_button.attrs:
                next_page = next_button["href"]
                current_page_url = next_page
                page_number += 1
                await asyncio.sleep(1)
            else:
                print("🚀 No more pages to scrape.")
                break

        print(f"📦 Total products extracted: {len(all_data)}")
        # You can insert the data into a database or do further processing here if needed

# Run the scraper
asyncio.run(scrape_main_page())
