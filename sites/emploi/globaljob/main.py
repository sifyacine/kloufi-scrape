import asyncio
import json
import sys
import os
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

try:
    from scrape_details import extract_job_details
except ImportError:
    print("Error: Could not import extract_job_details from scrape_details.py")
    sys.exit(1)

async def scrape_listing_page(url="https://globaljobd-dz.com/offres"):
    """Scrape job listing page to extract all job URLs"""
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        text_mode=False
    )
    
    js_commands = [
        "await new Promise(r => setTimeout(r, 5000));",
        "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",
        """
        // Scroll to load all job cards
        await new Promise(r => setTimeout(r, 3000));
        let maxScrollHeight = document.body.scrollHeight;
        let scrollStep = 1000;
        let currentScroll = 0;
        while (currentScroll < maxScrollHeight) {
            window.scrollBy(0, scrollStep);
            currentScroll += scrollStep;
            await new Promise(r => setTimeout(r, 300));
            maxScrollHeight = document.body.scrollHeight;
        }
        """
    ]
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=url,
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                js_code=js_commands,
                delay_before_return_html=10
            )
        )
        
        if not result.success:
            print(f"Failed to load listing page: {result.error_message}")
            return []
        
        soup = BeautifulSoup(result.html, "html.parser")
        
        # Extract job URLs from job cards
        # Based on the HTML structure: div.col-12.col-md-6.col-xl-4 containing h5.job-title a
        job_urls = []
        job_cards = soup.select("div.col-12.col-md-6.col-xl-4")
        
        for card in job_cards:
            title_link = card.select_one("h5 a[href]")
            if title_link:
                href = title_link.get("href", "")
                if href.startswith("/"):
                    full_url = "https://globaljob-dz.com" + href
                elif href.startswith("http"):
                    full_url = href
                else:
                    continue
                job_urls.append(full_url)
        
        print(f"Found {len(job_urls)} job URLs on listing page")
        return job_urls

async def scrape_all_jobs():
    """Main function to scrape all jobs"""
    # Get all job URLs from listing page
    job_urls = await scrape_listing_page()
    
    if not job_urls:
        print("No job URLs found")
        return
    
    # Scrape each job detail
    for i, url in enumerate(job_urls, 1):
        print(f"\n[{i}/{len(job_urls)}] Scraping: {url}")
        try:
            await extract_job_details(url)
            await asyncio.sleep(2)  # Be polite
        except Exception as e:
            print(f"Error scraping {url}: {e}")
            continue

if __name__ == "__main__":
    asyncio.run(scrape_all_jobs())
