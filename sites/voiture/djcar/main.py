import asyncio
import json
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from bs4 import BeautifulSoup
from scrape_details import extract_car_details  

# Global list to collect detail page URLs
all_urls = []

async def scrape_listing_pages():
    browser_config = BrowserConfig(
        headless=True,
        browser_type="firefox",
        text_mode=False
    )
    
    # Define the two different sites
    sites = [
        "https://www.djcar.fr/vehicules-neufs/",
        "https://www.djcar.fr/vehicules-doccasion/"
    ]
    
    for url in sites:
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
            print(f"Error loading {url}: {result.error_message}")
            continue
        
        soup = BeautifulSoup(result.html, "html.parser")
        
        # Updated selector based on provided HTML snippet
        items = soup.find_all("h3", class_="item-title")
        valid_items = []
        
        for item in items:
            a_tag = item.find("a")
            if a_tag and a_tag.get("href"):
                car_url = a_tag.get("href")
                if not car_url.startswith("http"):
                    car_url = "https://www.djcar.fr" + car_url
                if car_url not in all_urls:
                    all_urls.append(car_url)
                    valid_items.append(item)  # Track valid items
        
        if not valid_items:
            print(f"No valid car listings found on {url}.")
        else:
            print(f"Found {len(valid_items)} cars on {url}.")

async def main():
    await scrape_listing_pages()
    print(f"Total car URLs found: {len(all_urls)}")
    
    cars = []
    for url in all_urls:
        try:
            details = await extract_car_details(url)  # You'll need to implement this
            if details:  # Only append if not filtered out
                cars.append(details)
        except Exception as e:
            print(f"Error extracting details for {url}: {e}")
            continue

    # Save the collected car data into a JSON file
    # with open("djcar_cars.json", "w", encoding="utf-8") as f:
    #     json.dump(cars, f, ensure_ascii=False, indent=4)
    # print("Car data saved to djcar_cars.json")

if __name__ == "__main__":
    asyncio.run(main())