import asyncio
import json
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from bs4 import BeautifulSoup
from scrape_details import extract_product_details # Changed function name
from urllib.parse import urljoin

# Global list to collect detail page URLs
all_urls = []

async def scrape_listing_pages():
    """
    Scrapes listing pages from new.diardzair.com.dz to collect product detail URLs.
    It iterates through pages until no new links are found.
    """
    page = 1
    browser_config = BrowserConfig(
        headless=False,
        browser_type="firefox",
        text_mode=False,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"


    )
    
    while True:
        # Construct the URL for the current listing page on new.diardzair.com.dz
        url = (
            "https://new.diardzair.com.dz/search/"
            f"?page={page}&parent=Electromenager" # Updated URL structure for the new site
        )
        print(f"▶ Loading listing page {page}: {url}")
        
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(
                url=url,
                config=CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    delay_before_return_html=40, # Reduced delay as 20s might be too long
                    magic=True,
                    simulate_user=True,
                    override_navigator=True,
                )
            )
        
        if not result.success:
            print(f"✖ Error loading page {page}: {result.error_message}")
            break
        
        soup = BeautifulSoup(result.html, "html.parser")
        
        # Select product links using the updated CSS selector
        # The 'a' tag containing the 'card-product' div has the href
        links = soup.select("div.col > a") # Select 'a' tags that are direct children of 'div.col'
        
        if not links:
            print(f"ℹ No more product links found on page {page}, stopping.")
            break
        
        new_links = []
        for a in links:
            href = a.get("href")
            if not href:
                continue
            # Construct the full URL by joining with the base URL
            full_url = urljoin("https://new.diardzair.com.dz", href)
            if full_url not in all_urls:
                all_urls.append(full_url)
                new_links.append(full_url)
        
        print(f"✔ Found {len(new_links)} new links on page {page}.")
        
        # If no new links were found on this page, it means we've reached the end of pagination
        if not new_links:
            print(f"ℹ No new links found, stopping pagination.")
            break

        page += 1
        await asyncio.sleep(2) # Be polite with the server, increased sleep slightly

async def main():
    """
    Main function to orchestrate the scraping process.
    Calls the listing page scraper, then iterates through collected URLs
    to extract detailed product information, and finally saves the data to a JSON file.
    """
    print("Starting listing page scraping...")
    await scrape_listing_pages()
    print(f"\nTotal product URLs found: {len(all_urls)}\n")
    
    products = []
    # Iterate through each collected product URL and extract details
    for url in all_urls:
        print(f"Extracting details from: {url}")
        try:
            # Call the updated extract_product_details function
            details = await extract_product_details(url)
            if details: # Only append if details were successfully extracted
                products.append(details)
        except Exception as e:
            print(f"⚠ Error extracting details for {url}: {e}")
            continue
        await asyncio.sleep(1) # Add a small delay between detail page requests
    
    # Define the output path for the JSON file
    output_path = r"electromenager\diardzair\data\scraped_products.json" # Changed filename to reflect products
    
    # Save the collected product data to a JSON file
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=4)
    print(f"✅ Saved {len(products)} product records to {output_path}")

if __name__ == "__main__":
    asyncio.run(main())

