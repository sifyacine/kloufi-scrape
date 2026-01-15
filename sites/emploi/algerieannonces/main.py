import asyncio
import json
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from bs4 import BeautifulSoup
from scrape_details import extract_job_details  # Assumes this function is implemented in scrape_details.py
from urllib.parse import urljoin

# Global list to collect detail page URLs
all_urls = []

# Define browser_config globally
browser_config = BrowserConfig(
    headless=True,
    browser_type="chromium",
    text_mode=False
)

async def scrape_listing_pages():
    """Scrape job listing pages to collect job URLs."""
    page = 1
    
    while True:
        # Adjust URL: first page uses base URL, subsequent pages append ?pge={page}
        url = fr"https://www.algerieannonces.com/categorie/309/Offres-emploi/{page}.html"
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
        
        # Find all <li> elements containing job listings
        job_listings = soup.find_all("li")
        valid_links = []
        
        for li in job_listings:
            a_tag = li.find("a")
            if a_tag and a_tag.get("href"):
                job_url = urljoin("https://www.algerieannonces.com", a_tag["href"])
                if "/annonce/" in job_url and job_url not in all_urls:
                    all_urls.append(job_url)
                    valid_links.append(job_url)
        
        if not valid_links:
            print(f"No valid job listings found on page {page}. Stopping pagination.")
            break
        
        print(f"Found {len(valid_links)} job links on page {page}.")
        page += 1
        if page == 2: break

async def main():
    """Main function to orchestrate scraping."""
    await scrape_listing_pages()
    print(f"Total job URLs found: {len(all_urls)}")
    
    jobs = []
    for url in all_urls:
        try:
            details = await extract_job_details(url, browser_config)
            if details:
                jobs.append(details)
        except Exception as e:
            print(f"Error extracting details for {url}: {e}")
            continue
    
    # Save to JSON file
    with open(fr"emploi\algerieannonces\data\algerieannonces_jobs.json", "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=4)
        print("Jobs data saved to algerieannonces_jobs.json")

if __name__ == "__main__":
    asyncio.run(main())