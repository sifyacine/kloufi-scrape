import asyncio
import json
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from bs4 import BeautifulSoup
try:
    from scrape_details import extract_car_details
except ImportError as e:
    print(f"Error importing scrape_details: {e}")
    raise

# Global list to collect detail page URLs
all_urls = []

async def scrape_listing_pages():
    page = 1  # Start at page 1
    browser_config = BrowserConfig(
        headless=True,
        browser_type="firefox",
        text_mode=False,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    
    while True:
        # Pagination URL for AutoCango.com
        url = f"https://www.autocango.com/usedcar/energyType=Petrol/minYear=2023/seedId=94401ccaa245aced94401ccaa245aced?page={page}"
        print(f"Loading listing page: {url}")
        async with AsyncWebCrawler(config=browser_config) as crawler:
            try:
                result = await crawler.arun(
                    url=url,
                    config=CrawlerRunConfig(
                        cache_mode=CacheMode.BYPASS,
                        delay_before_return_html=10
                    )
                )
            except Exception as e:
                print(f"Error loading page {page}: {e}")
                break
        
        if not result.success:
            print(f"Error loading page {page}: {result.error_message}")
            break
        
        soup = BeautifulSoup(result.html, "html.parser")
        
        # Find all <div> tags with class "car-item"
        listing_items = soup.find_all("div", class_="car-item")
        valid_links = []
        
        for item in listing_items:
            # Find the <a> tag within the car-item div
            link_tag = item.find("a", href=True)
            if not link_tag:
                continue
                
            try:
                car_url = link_tag["href"]
                
                # If the URL is relative, prepend the base URL
                if car_url and not car_url.startswith("http"):
                    car_url = "https://www.autocango.com" + car_url
                
                # Add unique URLs to the list
                if car_url and car_url not in all_urls:
                    all_urls.append(car_url)
                    valid_links.append(car_url)
                
            except Exception as e:
                print(f"Error processing item on page {page}: {e}")
                continue
        
        if not valid_links:
            print(f"No valid car listings found on page {page}. Stopping pagination.")
            break
        
        print(f"Found {len(valid_links)} car links on page {page}.")
        page += 1

        if page == 2: break

async def main():
    await scrape_listing_pages()
    print(f"Total car URLs found: {len(all_urls)}")
    
    cars = []
    for url in all_urls:
        try:
            details = await extract_car_details(url)
            cars.append(details)
        except Exception as e:
            print(f"Error extracting details for {url}: {e}")
            continue
    
    # # Save the collected vehicles into a JSON file
    with open(r"voiture\autocango\data\scraped_vehicles.json", "w", encoding="utf-8") as f:
        json.dump(cars, f, ensure_ascii=False, indent=4)
    print("Car data saved to scraped_vehicles.json")

if __name__ == "__main__":
    asyncio.run(main())