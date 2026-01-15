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
    page = 1  # Start at page 0 to ensure first page is included
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        text_mode=False,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    
    while True:
        # Pagination URL for Autobessah.fr
        url = f"https://www.autobessah.fr/voiture-moins-de-3-ans-algerie?ep%5B210193371%5D%5Bpage%5D={page}&ep%5B210193371%5D%5Bsort%5D=created-desc"
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
        
        # Find all <li> tags representing product items
        listing_items = soup.find_all("li", class_="product-gallery__item")
        valid_links = []
        
        for item in listing_items:
            content_div = item.find("div", class_="product-gallery__content")
            if not content_div or not content_div.has_attr("data-webshop-product"):
                continue
                
            try:
                # Parse the JSON from the data-webshop-product attribute
                product_data = json.loads(content_div["data-webshop-product"])
                car_url = product_data.get("url", "")
                
                # If the URL is relative, prepend the base URL
                if car_url and not car_url.startswith("http"):
                    car_url = "https://www.autobessah.fr" + car_url
                
                # Add unique URLs to the list
                if car_url and car_url not in all_urls:
                    all_urls.append(car_url)
                    valid_links.append(car_url)
                
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON on page {page}: {e}")
                continue
            except Exception as e:
                print(f"Error processing item on page {page}: {e}")
                continue
        
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
        #Save the collected vehicles into a JSON file
    # with open(r"voiture\autobessah\data\scraped_vehicles.json", "w", encoding="utf-8") as f:
    #     json.dump(cars , f, ensure_ascii=False, indent=4)
    # print("Jobs data saved to scraped_vehicles.json")

if __name__ == "__main__":
    asyncio.run(main())