import asyncio
import json
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy


async def scrape_main_page(url):
    # Define extraction schema based on new structure
    schema = {
        "name": "Job Listings",
        "baseSelector": "div.description",  # Adjusted for the correct job container
        "fields": [
            {
                "name": "contract_type",
                "selector": "span.j_contrat",
                "type": "text"
            },
            {
                "name": "title",
                "selector": "span.j_titre",
                "type": "text"
            },
            {
                "name": "date",
                "selector": "span.j_date",
                "type": "text"
            },
            {
                "name": "location",
                "selector": "span.j_location",
                "type": "text"
            }
        ]
    }

    extraction_strategy = JsonCssExtractionStrategy(schema, verbose=True)

    browser_config = BrowserConfig(
        headless=False,  # Set to True to run in the background
        text_mode=False,
        browser_type="chromium",
        java_script_enabled=True
    )

    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=extraction_strategy,
        delay_before_return_html=150,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        all_data = []
        current_page_url = url
        page_number = 1

        crawler.crawler_strategy.set_custom_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"})

        while True:
            print(f"📌 Scraping page {page_number}: {current_page_url}")

            result = await crawler.arun(url=current_page_url, config=config)

            if not result.success:
                print(
                    f"❌ Failed to scrape {current_page_url}: {result.error_message}")
                break

            extracted_data = json.loads(result.extracted_content)
            print(
                f"✅ Extracted {len(extracted_data)} job listings from page {page_number}")

            all_data.extend(extracted_data)

            # **🔄 Pagination Handling**
            soup = BeautifulSoup(result.html, "html.parser")
            # Adjusted to match the next button text
            next_button = soup.find("a", string="Suivant")

            if next_button and next_button.get("href"):
                next_page = next_button["href"]
                current_page_url = "https://globaljob-dz.com" + next_page  # Adjusted base URL
                page_number += 1
                await asyncio.sleep(1)
            else:
                print("🚀 No more pages to scrape.")
                break

        print(f"📦 Total job listings extracted: {len(all_data)}")
        return all_data  # Return data for further processing


async def scrape_all_categories():
    jobs = await scrape_main_page("https://globaljob-dz.com/offres#nooffres")
    print(f"Total jobs: {len(jobs)}")
    # with open("jobs.json", "w", encoding="utf-8") as f:
    #     json.dump(jobs, f, ensure_ascii=False, indent=4)

# Run the scraper
asyncio.run(scrape_all_categories())
