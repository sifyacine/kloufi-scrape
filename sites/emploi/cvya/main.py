import asyncio
import re
import json
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from bs4 import BeautifulSoup
from scrape_details import extract_job_details

# Global list to collect {url, willaya} dicts
job_entries = []

async def scrape_listing_pages():
    page = 1
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        text_mode=False
    )
    
    while True:
        listing_url = f"https://cvya.dz/fr/algerie.htm?p={page}"
        print(f"Loading listing page: {listing_url}")
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(
                url=listing_url,
                config=CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    delay_before_return_html=5
                )
            )
        
        if not result.success:
            print(f"Error loading page {page}: {result.error_message}")
            break

        soup = BeautifulSoup(result.html, "html.parser")
        # Find all detail links on this page
        detail_links = soup.find_all("a", class_="detail_link", href=True)
        if not detail_links:
            print(f"No detail links found on page {page}. Stopping pagination.")
            break
        
        for a_tag in detail_links:
            raw_url = a_tag["href"]
            # Normalize URL
            if not raw_url.startswith("http"):
                url = "https://cvya.dz" + raw_url
            else:
                url = raw_url

            # Extract willaya from the same <li> container
            li = a_tag.find_parent("li")
            willaya = None
            if li:
                cat_tag = li.find("h5", class_="moduleItemTitle auto category-ads")
                if cat_tag:
                    text = cat_tag.get_text(strip=True)
                    # e.g. "Formation / Education a ALGER"
                    m = re.search(r"à\s*(.+)$", text) or re.search(r"a\s*(.+)$", text)
                    if m:
                        willaya = m.group(1).strip().upper()

            # Dedupe
            if not any(entry["url"] == url for entry in job_entries):
                job_entries.append({"url": url, "willaya": willaya})

        print(f"Page {page}: found {len(detail_links)} links, total entries so far: {len(job_entries)}")
        page += 1
        if page == 2: break

async def main():
    await scrape_listing_pages()
    print(f"Total job entries found: {len(job_entries)}")
    
    jobs = []
    for entry in job_entries:
        url = entry["url"]
        region = entry.get("willaya")
        try:
            details = await extract_job_details(url)
            # Attach willaya from the listing
            details["willaya"] = region
            jobs.append(details)
        except Exception as e:
            print(f"Error extracting details for {url}: {e}")
            continue

    # Save the collected jobs into a JSON file
    out_path = r"emploi\cvya\data\cvya_jobs.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=4)
    print(f"Jobs data (with willaya) saved to {out_path}")

if __name__ == "__main__":
    asyncio.run(main())
