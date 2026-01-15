import asyncio
import json
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy

async def scrape_main_page(url):
    # Define extraction schema
    schema = {
        "name": "Job Listings",
        "baseSelector": "div.cursor-pointer",  # Adjusted based on provided HTML
        "fields": [
            {
                "name": "company",
                "selector": "p.font-normal.text-sm",
                "type": "text"
            },
            {
                "name": "title",
                "selector": "p.font-semibold.text-xl",
                "type": "text"
            },
            {
                "name": "location",
                "selector": "p.font-medium.text-base",
                "type": "text"
            },
            {
                "name": "contract_type",
                "selector": "div.bg-gray-100 p.text-gray-700",
                "type": "text"
            },
            {
                "name": "experience",
                "selector": "div.bg-gray-100 p.text-gray-700",
                "type": "text"
            }
        ]
    }

    extraction_strategy = JsonCssExtractionStrategy(schema, verbose=True)

    browser_config = BrowserConfig(
        headless=False,
        text_mode=False,
        browser_type="Chrome",
        java_script_enabled=True
    )

    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=extraction_strategy,
        delay_before_return_html=150,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:  # Correctly using config here
        all_data = []
        current_page_url = url
        page_number = 1

        while True:
            print(f"📌 Scraping page {page_number}: {current_page_url}")

            result = await crawler.arun(url=current_page_url, config=config)

            if not result.success:
                print(f"❌ Failed to scrape {current_page_url}: {result.error_message}")
                break

            extracted_data = json.loads(result.extracted_content)
            print(f"✅ Extracted {len(extracted_data)} job listings from page {page_number}")

            all_data.extend(extracted_data)

            # **🔄 Pagination Handling**
            soup = BeautifulSoup(result.html, "html.parser")
            next_button = soup.find("a", class_="next")

            if next_button and next_button.get("href"):
                next_page = next_button["href"]
                current_page_url = "https://www.emploipartner.com" + next_page
                page_number += 1
                await asyncio.sleep(1)
            else:
                print("🚀 No more pages to scrape.")
                break

        print(f"📦 Total job listings extracted: {len(all_data)}")
        return all_data  # Return data for further processing

async def scrape_all_categories():
    jobs = await scrape_main_page("https://www.emploipartner.com/fr/jobs/search")
    print(f"Total jobs: {len(jobs)}")
    # with open("jobs.json", "w", encoding="utf-8") as f:
    #     json.dump(jobs, f, ensure_ascii=False, indent=4)

# Run the scraper
asyncio.run(scrape_all_categories())
