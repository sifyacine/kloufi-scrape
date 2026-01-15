import asyncio
import json
from urllib.parse import urljoin

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
)
from bs4 import BeautifulSoup
from scrape_details import extract_car_details  # your detail‐page extractor

async def scrape_listing_pages():
    page = 1
    all_urls = []
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        text_mode=False
    )

    while True:
        listing_url = (
            f"https://www.algerieannonces.com/"
            f"categorie/314/Voitures-occasion/{page}.html"
        )
        print(f"→ Loading page {page}: {listing_url}")

        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(
                url=listing_url,
                config=CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    delay_before_return_html=10
                )
            )

        if not result.success:
            print(f"⛔ Failed to load page {page}: {result.error_message}")
            break

        soup = BeautifulSoup(result.html, "html.parser")

        # Select every <a> under an <li> whose href contains "/annonce/"
        anchors = soup.select("li a[href*='/annonce/']")
        new_links = []
        for a in anchors:
            href = a["href"]
            full_url = urljoin("https://www.algerieannonces.com", href)
            if full_url not in all_urls:
                all_urls.append(full_url)
                new_links.append(full_url)

        if not new_links:
            print(f"✅ No new listings on page {page}. Stopping.")
            break

        print(f"✔ Found {len(new_links)} new links on page {page}")
        page += 1

    return all_urls

async def main():
    # 1) scrape all the listing URLs
    urls = await scrape_listing_pages()
    print(f"\nTotal annonces found: {len(urls)}\n")

    # 2) visit each annonce and extract details
    jobs = []
    for url in urls:
        try:
            details = await extract_car_details(url)
            jobs.append(details)
            print(f"  • Extracted {details.get('numero', url)}")
        except Exception as e:
            print(f"  ⚠ Error on {url}: {e}")

    # 3) save to JSON
    output_file = fr"voiture\algerieannonces\data\scraped_cars.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(jobs)} annonces to {output_file}")

if __name__ == "__main__":
    asyncio.run(main())
