import asyncio
import json
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from bs4 import BeautifulSoup
from scrape_details import extract_car_details  # Note: You'll need to create this function

# Global list to collect detail page URLs
all_urls = []

async def scrape_listing_pages():
    page = 1
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        text_mode=False
    )
    
    while True:
        url = f"https://www.easyexport.fr/vehicules-d-occasion-w{page}"
        print(f"Loading listing page: {url}")
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(
                url=url,
                config=CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    delay_before_return_html=30
                )
            )
        
        if not result.success:
            print(f"Error loading page {page}: {result.error_message}")
            break
        
        soup = BeautifulSoup(result.html, "html.parser")
        
        # Look for <h2> tags that contain the car detail links.
        listing_tags = soup.find_all("h2", class_="headline-ann")
        valid_links = []
        
        for tag in listing_tags:
            a_tag = tag.find("a")
            if a_tag and a_tag.get("href"):
                car_url = a_tag.get("href")
                # Prepend base URL if the URL is relative
                if not car_url.startswith("http"):
                    car_url = "https://www.easyexport.fr/" + car_url
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
    
    cars = []
    for url in all_urls:
        try:
            details = await extract_car_details(url)  # You'll need to implement this function
            cars.append(details)
        except Exception as e:
            print(f"Error extracting details for {url}: {e}")
            continue

if __name__ == "__main__":
    asyncio.run(main())
