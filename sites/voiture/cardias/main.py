import asyncio
import json
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from bs4 import BeautifulSoup
from scrape_details import extract_car_details  # Ensure this function is implemented
import sys
sys.path.insert(1, '../../../insert2db')
from insert_scrape import insert_data_to_es

# Global list to collect detail page URLs
all_urls = []
semaphore = asyncio.Semaphore(5)

async def limited_extract_car_details(url):
    async with semaphore:
        return await extract_car_details(url)

async def scrape_listing_pages():
    page = 1
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        text_mode=False
    )
    
    while True:
        url = f"https://www.cardias.fr/products/?page={page}"
        print(f"Loading listing page: {url}")
        
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(
                url=url,
                config=CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    delay_before_return_html=10
                )
            )
        
        if not result.success:
            print(f"Error loading page {page}: {result.error_message}")
            break
        
        soup = BeautifulSoup(result.html, "html.parser")
        # Find all the listing blocks using the new structure
        listing_divs = soup.find_all("div", class_="views-row")
        valid_links = []
        
        for listing in listing_divs:
            a_tag = listing.find("a", href=True)
            if a_tag:
                car_url = a_tag.get("href")
                # Prepend the base URL if the link is relative and remove query parameters if needed.
                if car_url.startswith("/"):
                    car_url = "https://www.cardias.fr" + car_url.split('?')[0]
                if car_url not in all_urls:
                    all_urls.append(car_url)
                    valid_links.append(car_url)
        
        if not valid_links:
            print(f"No valid car listings found on page {page}. Stopping pagination.")
            break
        
        print(f"Found {len(valid_links)} car links on page {page}.")
        page += 1

async def main():
    await scrape_listing_pages()
    print(f"Total car URLs found: {len(all_urls)}")
    
    # Process detail extraction concurrently
    tasks = [limited_extract_car_details(url) for url in all_urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    cars = []
    for url, result in zip(all_urls, results):
        if isinstance(result, Exception):
            print(f"Error extracting details for {url}: {repr(result)}")
        else:
            cars.append(result)
    
    # Save the collected vehicles into a JSON file.
    # with open(r"voiture\cardias\data\scraped_vehicles.json", "w", encoding="utf-8") as f:
    #     json.dump(cars, f, ensure_ascii=False, indent=4)
    
    print("Car data saved to scraped_vehicles.json")

if __name__ == "__main__":
    asyncio.run(main())
