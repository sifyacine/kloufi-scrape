import asyncio
import json
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from bs4 import BeautifulSoup
from scrape_details import extract_property_details

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
        url = f"https://www.algeriahome.com/search/iPage,{page}"
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
        # Find all property cards using the provided class selector
        cards = soup.find_all("div", class_="detail_info")
        if not cards:
            print(f"No property cards found on page {page}. Stopping pagination.")
            break
        
        for card in cards:
            # In each card, the property link is inside the <h4> tag
            title_tag = card.find("h4")
            if title_tag:
                a_tag = title_tag.find("a")
                if a_tag and a_tag.get("href"):
                    prop_url = a_tag.get("href")
                    if not prop_url.startswith("http"):
                        prop_url = "https://www.algeriahome.com" + prop_url
                    if prop_url not in all_urls:
                        all_urls.append(prop_url)

        print(f"Found {len(cards)} cards on page {page}.")
        page += 1
        if page == 25: break

async def main():
    await scrape_listing_pages()
    print(f"Total property URLs found: {len(all_urls)}")
    
    properties = []
    for url in all_urls:
        try:
            details = await extract_property_details(url)
            properties.append(details)
        except Exception as e:
            print(f"Error extracting details for {url}: {e}")
            continue

    # Save the collected properties into a JSON file
    with open("immobilier/algeriahome/data/algeriahome_properties.json", "w", encoding="utf-8") as f:
        json.dump(properties, f, ensure_ascii=False, indent=4)
    print("Properties data saved to algeriahome_properties.json")

if __name__ == "__main__":
    asyncio.run(main())
