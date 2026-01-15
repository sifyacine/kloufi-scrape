import json
import asyncio
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
from scrape_details import extract_multimedia_details
import sys
sys.setrecursionlimit(10000)

async def scrape_main_page():
    # Define the extraction schema for Jumia product listings
    schema = {
        "name": "Product Listings",
        "baseSelector": "article.prd._fb.col.c-prd",
        "fields": [
            {
                "name": "title",
                "selector": "h3.name",
                "type": "text"
            },
            {
                "name": "url",
                "selector": "a.core",
                "type": "attribute",
                "attribute": "href"
            },
            {
                "name": "price",
                "selector": "div.prc",
                "type": "text"
            },
            {
                "name": "old_price",
                "selector": "div.old",
                "type": "text"
            },
            {
                "name": "discount",
                "selector": "div.bdg._dsct",
                "type": "text"
            },
            {
                "name": "rating",
                "selector": "div.stars",
                "type": "text"
            },
            {
                "name": "image",
                "selector": "div.img-c img",
                "type": "attribute",
                "attribute": "data-src"
            }
        ]
    }

    extraction_strategy = JsonCssExtractionStrategy(schema, verbose=True)

    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=extraction_strategy,
    )

    async with AsyncWebCrawler(verbose=True) as crawler:
        all_data = []
        base_url = "https://www.jumia.com.dz/electromenager/#catalog-listing"
        current_page_url = base_url
        page_number = 1

        while True:
            print(f"Scraping page {page_number}: {current_page_url}")

            result = await crawler.arun(url=current_page_url, config=config)
            
            if not result.success:
                print(f"Failed to scrape {current_page_url}: {result.error_message}")
                break

            extracted_data = json.loads(result.extracted_content)
            print(f"Extracted {len(extracted_data)} products from page {page_number}")

            for item in extracted_data:
                if item.get("url"):
                    item["url"] = "https://www.jumia.com.dz" + item["url"]
                    try:
                        await extract_multimedia_details(item["url"], item)
                    except Exception as e:
                        print(f"Failed to extract details for {item['url']}: {str(e)}")
                        continue
                else:
                    print(f"Skipping item without URL: {item}")
                    continue
                all_data.append(item)

            soup = BeautifulSoup(result.html, "html.parser")
            next_button = soup.find("a", class_="pg", attrs={"aria-label": "Page suivante"})

            if next_button and "href" in next_button.attrs:
                current_page_url = "https://www.jumia.com.dz" + next_button["href"]
                page_number += 1
            else:
                print("No more pages to scrape.")
                break

        print(f"Total products extracted: {len(all_data)}")
        print(json.dumps(all_data, indent=2) if all_data else "No data found")

# Run the scraper
asyncio.run(scrape_main_page())