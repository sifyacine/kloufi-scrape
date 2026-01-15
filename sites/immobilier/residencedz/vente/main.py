import asyncio
import json
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from bs4 import BeautifulSoup
from scrape_details import extract_property_details  # Assuming this function is adapted or created for residencedz.com

# Global list to collect detail page URLs
all_urls = []

async def scrape_listing_pages():
    page = 1
    base_url = "https://www.residencedz.com/advanced-search/page/{}/?filter_search_action%5B0%5D=ventes&adv6_search_tab=ventes&term_id=102&term_counter=0&id-du-bien&filter_search_type%5B0%5D&advanced_city&advanced_area&chambre&etage&surface-min&surface-max&surface-lot-min&surface-lot-max&price_low_102=5000000&price_max_102=900000000&submit=Rechercher&elementor_form_id=30774"
    
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        text_mode=False
    )
    
    while True:
        url = base_url.format(page)
        print(f"Loading listing page: {url}")
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(
                url=url,
                config=CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    delay_before_return_html=5
                )
            )
        
        if not result.success:
            print(f"Error loading page {page}: {result.error_message}")
            break
        
        soup = BeautifulSoup(result.html, "html.parser")
        
        # Find all property cards
        cards = soup.find_all("div", class_="col-md-6 has_prop_slider listing_wrapper")
        if not cards:
            print(f"No property cards found on page {page}. Stopping pagination.")
            break
        
        for card in cards:
            # The detail URL is in the data-modal-link attribute of the card div
            prop_url = card.get("data-modal-link")
            if prop_url:
                if not prop_url.startswith("http"):
                    prop_url = "https://www.residencedz.com" + prop_url
                if prop_url not in all_urls:
                    all_urls.append(prop_url)
        
        print(f"Found {len(cards)} cards on page {page}.")
        page += 1


async def main():
    await scrape_listing_pages()
    print(f"Total property URLs found: {len(all_urls)}")
    
    properties = []
    for url in all_urls:
        try:
            # Note: You will need to implement or adapt extract_property_details for residencedz.com
            details = await extract_property_details(url)
            properties.append(details)
        except Exception as e:
            print(f"Error extracting details for {url}: {e}")
            continue

    # Save the collected properties into a JSON file
    # Adjust the filename/path as needed
    # with open("immobilier/residencedz/data/residencedz_properties.json", "w", encoding="utf-8") as f:
    #     json.dump(properties, f, ensure_ascii=False, indent=4)
    # print("Properties data saved to residencedz_properties.json")

if __name__ == "__main__":
    asyncio.run(main())