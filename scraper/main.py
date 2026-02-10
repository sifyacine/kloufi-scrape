import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import tldextract
import json
import time
import random
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from scraper.proxy.proxy_sources import fetch_and_validate_proxies
from scraper.proxy.proxy_manager import ProxyManager
from scraper.crawler.playwright_crawler import crawl_with_playwright
from scraper.extractor.detail_extractor import DetailExtractor

# Try to import stealth, warn if missing
try:
    from playwright_stealth import stealth_async
except ImportError:
    print("WARNING: playwright-stealth not installed. Stealth mode disabled.")
    async def stealth_async(page): pass

# Configuration
BASE_URL = "https://www.ouedkniss.com/immobilier/{}"
START_PAGE = 1
MAX_PAGES = 5  # Scrape 5 pages
CONCURRENCY = 3 # Number of concurrent detail extractions

async def crawl_listings():
    """Phase 1: Crawl listing pages to get announcement URLs."""
    print(f"\n{'='*60}")
    print(f"PHASE 1: CRAWLING LISTING PAGES")
    print(f"{'='*60}")
    
    # Initialize Proxy Manager with VALIDATED proxies
    proxies = await fetch_and_validate_proxies()
    if not proxies:
        print("CRITICAL: No valid proxies found. Exiting.")
        return []
        
    manager = ProxyManager(proxies)
    print(f"Loaded {len(proxies)} validated proxies.")

    all_found_urls = []
    
    for page_num in range(START_PAGE, START_PAGE + MAX_PAGES):
        url = BASE_URL.format(page_num)
        print(f"Scraping Listing Page {page_num}/{START_PAGE + MAX_PAGES - 1}: {url}")
        
        match = tldextract.extract(url)
        domain = match.domain + '.' + match.suffix
        
        # Retry loop for listing pages (Aggressive retries for free proxies)
        max_retries = 20
        success = False
        
        for attempt in range(max_retries):
            # Get a fresh proxy (rotate if this isn't the first attempt)
            should_rotate = attempt > 0
            if should_rotate:
                print(f"  [Retry {attempt}/{max_retries}] Rotating proxy due to failure...")
                
            proxy = manager.get_proxy(domain, rotate=should_rotate)
            
            try:
                print(f"  Using proxy: {proxy}")
                # Crawl with Playwright WITH PROXY
                html, card_count = await crawl_with_playwright(url, proxy=proxy, headless=True)
                
                print(f"  [OK] Cards detected: {card_count}")
                
                soup = BeautifulSoup(html, 'html.parser')
                # Extract URLs
                cards = soup.select('.o-announ-card-column a.o-announ-card-content')
                
                extracted_count = 0
                for card in cards:
                    href = card.get('href')
                    if href:
                        full_url = f"https://www.ouedkniss.com{href}" if href.startswith('/') else href
                        all_found_urls.append(full_url)
                        extracted_count += 1
                
                print(f"  [SUCCESS] Extracted {extracted_count} URLs")
                manager.report_success(proxy)
                success = True
                break # Move to next page
                
            except Exception as e:
                print(f"  [FAILED] Attempt {attempt+1}: {e}")
                manager.report_failure(proxy)
                continue
        
        if not success:
            print(f"[ERROR] Failed to scrape page {page_num} after {max_retries} attempts.")

    # De-duplicate
    unique_urls = list(set(all_found_urls))
    print(f"\nPhase 1 Complete. Total Unique URLs: {len(unique_urls)}")
    
    # Save raw URLs
    with open('crawled_urls.json', 'w', encoding='utf-8') as f:
        json.dump(unique_urls, f, indent=4, ensure_ascii=False)
        
    return unique_urls

async def extract_details(urls):
    """Phase 2: Extract details for each URL."""
    print(f"\n{'='*60}")
    print(f"PHASE 2: EXTRACTING DETAILS ({len(urls)} URLs)")
    print(f"{'='*60}")

    # Initialize Proxy Manager
    proxies = await fetch_and_validate_proxies()
    if not proxies:
        print("CRITICAL: No valid proxies found. Exiting.")
        return

    manager = ProxyManager(proxies)

    announcements = []
    
    # Check for existing progress
    if os.path.exists('announcements.json'):
        try:
            with open('announcements.json', 'r', encoding='utf-8') as f:
                existing = json.load(f)
                # Map existing by URL to skip
                existing_urls = {item['url'] for item in existing if 'url' in item}
                print(f"Found {len(existing)} existing announcements. Skipping them.")
                announcements = existing
                urls = [u for u in urls if u not in existing_urls]
                print(f"Remaining to scrape: {len(urls)}")
        except:
            pass

    if not urls:
        print("No new URLs to scrape.")
        return

    async with async_playwright() as p:
        # STEALTH ARGS
        browser_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox"
        ]
        
        browser = await p.chromium.launch(headless=True, args=browser_args)
        sem = asyncio.Semaphore(CONCURRENCY)

        async def process_url(url):
            async with sem:
                domain = "ouedkniss.com"
                
                # Retry loop
                for attempt in range(3):
                    # Rotate proxy for EVERY attempt (even the first one if we want distribution)
                    # Use rotate=True to pick from top 20
                    proxy = manager.get_proxy(domain, rotate=True)
                    
                    context = None
                    page = None
                    try:
                        context_options = {
                            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
                        }
                        if proxy:
                            context_options["proxy"] = {"server": proxy}
                        
                        context = await browser.new_context(**context_options)
                        page = await context.new_page()
                        
                        # Apply stealth
                        await stealth_async(page)
                        
                        print(f"[Attempt {attempt+1}/3] {url} (Proxy: {proxy})")
                        
                        extractor = DetailExtractor(page) # Pass page directly
                        data = await extractor.extract(url)
                        
                        if data:
                            announcements.append(data)
                            manager.report_success(proxy)
                            return data # Success
                        else:
                            # Extraction returned None (failed internally)
                            manager.report_failure(proxy)
                            # Continue to next attempt
                    
                    except Exception as e:
                        print(f"  Error processing {url}: {e}")
                        manager.report_failure(proxy)
                    finally:
                        if page: await page.close()
                        if context: await context.close()
                
                return None # Failed after all retries

        # Shuffle to distribute load
        random.shuffle(urls)
        
        # Process in chunks
        chunk_size = 10
        total_chunks = (len(urls) + chunk_size - 1) // chunk_size
        
        for i in range(0, len(urls), chunk_size):
            chunk = urls[i:i+chunk_size]
            current_chunk_idx = i // chunk_size + 1
            print(f"Processing chunk {current_chunk_idx}/{total_chunks}...")
            
            chunk_tasks = [process_url(u) for u in chunk]
            await asyncio.gather(*chunk_tasks)
            
            # Save after chunk
            with open('announcements.json', 'w', encoding='utf-8') as f:
                json.dump(announcements, f, indent=4, ensure_ascii=False)
            print(f"Saved {len(announcements)} total announcements.")
            
            # Small delay between chunks
            await asyncio.sleep(2)

        await browser.close()

    print(f"\n[SUCCESS] Extraction complete. Saved {len(announcements)} announcements to 'announcements.json'")

async def main():
    # 1. Get URLs
    if os.path.exists('crawled_urls.json'):
        print("Found existing 'crawled_urls.json'. Using it.")
        with open('crawled_urls.json', 'r', encoding='utf-8') as f:
            urls = json.load(f)
    else:
        urls = await crawl_listings()
    
    # 2. Extract Details
    await extract_details(urls)

if __name__ == "__main__":
    asyncio.run(main())
