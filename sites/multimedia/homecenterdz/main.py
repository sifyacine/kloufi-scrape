import asyncio
import json
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
from scrape_details import scrape_product_details

async def scrape_main_page(url):
    # Define the new extraction schema
    schema = {
        "name": "Product Listings",
        "baseSelector": "div.article",
        "fields": [
            {
                "name": "category",
                "selector": "h2.categorie a",
                "type": "text"
            },
            {
                "name": "title",
                "selector": "h3.designation a",
                "type": "text"
            },
            {
                "name": "url",
                "selector": "h3.designation a",
                "type": "attribute",
                "attribute": "href"
            },
            {
                "name": "image",
                "selector": "div.img_container img",
                "type": "attribute",
                "attribute": "src"
            },
            {
                "name": "price",
                "selector": "div.prix span",
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
        current_page_url = url
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
                    item["url"] = "https://homecenterdz.com/" + item["url"]  # Ensure full URL
                    item["image"] = "https://homecenterdz.com/" + item["image"]
                    print(f"🛒 Extracted item: {item}")
                    await scrape_product_details(item["url"], item)
                    all_data.append(item)
                else:
                    print(f"⚠ Skipping item without URL: {item}")

            # **🔄 Pagination Handling**
            soup = BeautifulSoup(result.html, "html.parser")
            # <a href="rayon.php?id=3&amp;sort=DESC&amp;page=2" rel="2" class="next">Page suivante</a>
            next_button = soup.find("a", class_="next", string="Page suivante")

            if next_button and "href" in next_button.attrs:
                next_page = next_button["href"]
                current_page_url = "https://homecenterdz.com/" + next_page
                page_number += 1
                await asyncio.sleep(1)
            else:
                print("🚀 No more pages to scrape.")
                break

        print(f"📦 Total products extracted: {len(all_data)}")


async def scrape_all_categories():
    await scrape_main_page("https://homecenterdz.com/rayon.php?id=5")
        
# Run the scraper
asyncio.run(scrape_all_categories())
