import asyncio
import json
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from bs4 import BeautifulSoup
from scrape_details import extract_job_details

# Global list for detail page URLs
all_urls = []

async def scrape_listing_pages():
    page = 1
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        text_mode=True,  # Enable JS rendering
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    )
    
    # Step 1: Load the parent page to get the iframe URL
    parent_url = "https://halkorb-rh.com/offre-demploi"
    print(f"Loading parent listing page: {parent_url}")
    async with AsyncWebCrawler(config=browser_config) as crawler:
        parent_result = await crawler.arun(
            url=parent_url,
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                delay_before_return_html=15
            )
        )
    
    if not parent_result.success:
        print(f"Error loading parent page: {parent_result.error_message}")
        return
    
    parent_soup = BeautifulSoup(parent_result.html, 'html.parser')
    iframe = parent_soup.find("iframe")
    if iframe and iframe.get("src"):
        listing_url = iframe.get("src")
        print(f"Found iframe listing URL: {listing_url}")
    else:
        print("No iframe found; using parent URL.")
        listing_url = parent_url

    # Step 2: Load the listing page from the iframe with custom JS commands
    js_commands = [
        "window.scrollTo(0, document.body.scrollHeight);",
        "setTimeout(function(){ window.scrollTo(0, document.body.scrollHeight); }, 3000);",
        "setTimeout(function(){ window.scrollTo(0, document.body.scrollHeight); }, 6000);"
    ]
    
    print(f"Loading listing page: {listing_url}")
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=listing_url,
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                delay_before_return_html=30,  # Allow time for dynamic content to load
                js_code=js_commands         # Inject JS commands to simulate scrolling
            )
        )
    
    if not result.success:
        print(f"Error loading listing page: {result.error_message}")
        return
    
    # Debug: Output a snippet of the HTML for verification
    print("Page HTML snippet:", result.html[:500])
    
    soup = BeautifulSoup(result.html, 'html.parser')
    # Select the anchor tags that contain the job links
    anchor_tags = soup.select("a.background-link.text-truncate")
    if not anchor_tags:
        print(f"No job cards found on page {page}. Ending pagination.")
        return
    
    print(f"Found {len(anchor_tags)} job links on page {page}.")
    for a_tag in anchor_tags:
        href = a_tag.get("href")
        if href:
            # Ensure full URL
            if not href.startswith("http"):
                href = "https://ats.talenteo.com" + href
            if href not in all_urls:
                all_urls.append(href)

async def main():
    await scrape_listing_pages()
    print(f"Total detail URLs found: {len(all_urls)}")
    
    jobs = []
    for url in all_urls:
        try:
            details = await extract_job_details(url)
            jobs.append(details)
        except Exception as e:
            print(f"Error extracting details for {url}: {e}")
            continue

    # Save the collected jobs into a JSON file
    with open(r"emploi\halkorb-rh\data\halkorb-rh_jobs.json", "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=4)
    print("jobs data saved to halkorb-rh_jobs.json")

if __name__ == "__main__":
    asyncio.run(main())
