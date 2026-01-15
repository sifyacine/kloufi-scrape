import asyncio
import json
import sys
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
from datetime import datetime
from scrape_details import scrape_product_details
sys.setrecursionlimit(10000)

async def scrape_main_page():
    # Define the extraction schema for the new product structure
    schema = {
        "name": "Product Listings",
        "baseSelector": "div.single-product-wrap.pb-2.p-md-0",
        "fields": [
            {
                "name": "title",
                "selector": "h4.product_name",
                "type": "text"
            },
            {
                "name": "url",
                "selector": "a.product_name",
                "type": "attribute",
                "attribute": "href"
            },
            {
                "name": "image",
                "selector": "img",
                "type": "attribute",
                "attribute": "src"
            },
            {
                "name": "price",
                "selector": "span.new-price",
                "type": "text"
            },
            {
                "name": "brand",
                "selector": "a[href*='/produits/?brand=']",
                "type": "text"
            },
            {
                "name": "category",
                "selector": "a[href*='/produits/?category=']",
                "type": "text"
            }
        ]
    }

    extraction_strategy = JsonCssExtractionStrategy(schema, verbose=True)

    browser_config = BrowserConfig(
        headless=True,
        text_mode=False,
        browser_type="chromium",
        java_script_enabled=True
    )

    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=extraction_strategy,
        delay_before_return_html=5,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        all_data = []
        base_url = "https://starmania.dz/fr/produits/?category=21"
        current_page_url = base_url
        page_number = 1
        crawler.crawler_strategy.set_custom_headers({
            "Accept-Language": "fr-FR,fr;q=0.9",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive"
        })

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
                    await scrape_product_details("https://starmania.dz" + item["url"], item)
                    all_data.append(item)
                else:
                    print(f"⚠ Skipping item without URL: {item}")

            # **🔄 Pagination Handling**
            soup = BeautifulSoup(result.html, "html.parser")
            # <a href="?page=2&amp;category=21" class="Next"> Suivant <i class="fa fa-chevron-right"></i></a>
            next_button = soup.find("a", class_="Next")

            if next_button and "href" in next_button.attrs:
                next_page = next_button["href"]
                current_page_url = f"https://starmania.dz/fr/produits{next_page}"
                page_number += 1
                await asyncio.sleep(1)
            else:
                print("🚀 No more pages to scrape.")
                break

        print(f"📦 Total products extracted: {len(all_data)}")
        # Further processing or saving data can be done here

# Run the scraper
asyncio.run(scrape_main_page())
