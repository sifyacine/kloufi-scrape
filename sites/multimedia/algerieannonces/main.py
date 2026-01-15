import asyncio
import json
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from bs4 import BeautifulSoup
from scrape_details import extract_item_details
from urllib.parse import quote

# Global list to collect detail page URLs and their corresponding dates
all_urls_with_dates = []

async def scrape_listing_pages():
    page = 1
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        text_mode=False
    )
    
    while True:
        url = f"https://www.algerieannonces.com/categorie/306/Multim%C3%A9dia/{page}.html"
        print(f"Loading listing page: {url}")
        
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(
                url=url,
                config=CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    wait_for="css:li div.holder",
                    delay_before_return_html=15,
                    page_timeout=60000
                )
            )
        
        if not result.success:
            print(f"Error loading page {page}: {result.error_message}")
            break
        
        soup = BeautifulSoup(result.html, "html.parser")
        # Select <li> elements that contain a div.holder
        product_items = soup.find_all("li", class_=lambda x: x is None)
        product_items = [item for item in product_items if item.find("div", class_="holder")]
        
        if not product_items:
            print(f"No product items found on page {page}. Stopping pagination.")
            break
        
        for item in product_items:
            # Find the <a> tag directly within the <li>
            a_tag = item.find("a", href=True)
            if a_tag and a_tag.get("href"):
                prop_url = a_tag.get("href")
                # Ensure the URL is a product detail page
                if "/annonce/" in prop_url:
                    # URL-encode the href to handle special characters like non-breaking spaces
                    prop_url = quote(prop_url, safe='/:?=&')
                    # Ensure absolute URL
                    if not prop_url.startswith("http"):
                        prop_url = "https://www.algerieannonces.com/" + prop_url.lstrip("/")
                    # Extract date from <em class="date">
                    date_elem = item.find("em", class_="date")
                    date_text = date_elem.get_text(strip=True).split("<br>")[0].strip() if date_elem else ""
                    if prop_url not in [item[0] for item in all_urls_with_dates]:
                        all_urls_with_dates.append((prop_url, date_text))

        print(f"Found {len(product_items)} product items with {len(all_urls_with_dates)} URLs collected so far on page {page}.")
        page += 1
        if page == 2: break

async def main():
    await scrape_listing_pages()
    print(f"Total item URLs found: {len(all_urls_with_dates)}")
    
    items = []
    for url, date_text in all_urls_with_dates:  # Unpack the tuple
        try:
            details = await extract_item_details(url, date_text)  # Pass URL and date_text
            items.append(details)
        except Exception as e:
            print(f"Error extracting details for {url}: {e}")
            continue

    # Save the collected items into a JSON file
    with open(r"multimedia\algerieannonces\data\algerieannonces_items.json", "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=4)
    print("Items data saved to algerieannonces_items.json")

if __name__ == "__main__":
    asyncio.run(main())