import asyncio
import json
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from bs4 import BeautifulSoup
from scrape_details import extract_item_details

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
        url = f"https://informatics-dz.com/product-category/laptop-ordinateur-portable/page/{page}/?per_page=24"
        print(f"Loading listing page: {url}")
        
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(
                url=url,
                config=CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    # Wait for the product cards to appear instead of using "networkidle"
                    wait_for="css:div.wd-product",
                    delay_before_return_html=2,
                    page_timeout=60000
                )
            )
        
        if not result.success:
            print(f"Error loading page {page}: {result.error_message}")
            break
        
        soup = BeautifulSoup(result.html, "html.parser")
        # Each product is contained within a <div> with class "wd-product"
        cards = soup.find_all("div", class_="wd-product")
        if not cards:
            print(f"No item cards found on page {page}. Stopping pagination.")
            break
        
        for card in cards:
            # Extract the product detail URL from the <h3 class="wd-entities-title">
            title_tag = card.find("h3", class_="wd-entities-title")
            if title_tag:
                a_tag = title_tag.find("a")
                if a_tag and a_tag.get("href"):
                    prop_url = a_tag.get("href")
                    # Ensure we have an absolute URL
                    if not prop_url.startswith("http"):
                        prop_url = "https://informatics-dz.com" + prop_url
                    if prop_url not in all_urls:
                        all_urls.append(prop_url)

        print(f"Found {len(cards)} cards on page {page}.")
        page += 1


async def main():
    await scrape_listing_pages()
    print(f"Total item URLs found: {len(all_urls)}")
    
    items = []
    for url in all_urls:
        try:
            details = await extract_item_details(url)
            items.append(details)
        except Exception as e:
            print(f"Error extracting details for {url}: {e}")
            continue

    # Save the collected items into a JSON file
    with open(r"multimedia\informatics\data\informatics_laptop_items.json", "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=4)
    print("Items data saved to algeriahome_items.json")

if __name__ == "__main__":
    asyncio.run(main())
