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
        url = f"https://autoexportmarseille.com/annonces/?annee-de=2023&page-actuelle={page}&trier-par=nouveau"
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
        
        # Find all cards based on the container div's class
        cards = soup.find_all("div", class_="vehica-car-card-row-wrapper vehica-car")
        valid_cards = []
        
        for card in cards:
            # Updated: Use the correct <a> tag class 'vehica-car-card-link'
            a_tag = card.find("a", class_="vehica-car-card-link")
            if a_tag and a_tag.get("href"):
                car_url = a_tag.get("href")
                if not car_url.startswith("http"):
                    car_url = "https://www.autoexportmarseille.com" + car_url
                if car_url not in all_urls:
                    all_urls.append(car_url)
                    valid_cards.append(card)
        
        if not valid_cards:
            print(f"No valid car listings found on page {page}. Stopping pagination.")
            break
        
        print(f"Found {len(valid_cards)} cars on page {page}.")
        page += 1

async def main():
    await scrape_listing_pages()
    print(f"Total car URLs found: {len(all_urls)}")
    
    cars = []
    for url in all_urls:
        try:
            details = await extract_car_details(url)  # You'll need to implement this
            cars.append(details)
        except Exception as e:
            print(f"Error extracting details for {url}: {e}")
            continue
    
    # Save results
    # output_path = r"voiture\autoexportmarseille\data\scraped_vehicles.json"  # Removed 'fr' prefix for raw string
    # with open(output_path, "w", encoding="utf-8") as f:
    #     json.dump(cars, f, ensure_ascii=False, indent=4)
    # print(f"✅ Saved {len(cars)} vehicle records to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
