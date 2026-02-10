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
from scraper.proxy.proxy_sources import fetch_proxies
from scraper.proxy.proxy_manager import ProxyManager
from scraper.crawler.playwright_crawler import crawl_with_playwright
from scraper.extractor.detail_extractor import DetailExtractor

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
    
    # Initialize Proxy Manager
    proxies = await fetch_proxies()
    manager = ProxyManager(proxies)
    print(f"Loaded {len(proxies)} proxies.")

    all_found_urls = []
    
    for page_num in range(START_PAGE, START_PAGE + MAX_PAGES):
        url = BASE_URL.format(page_num)
        print(f"Scraping Listing Page {page_num}/{START_PAGE + MAX_PAGES - 1}: {url}")
        
    for page_num in range(START_PAGE, START_PAGE + MAX_PAGES):
        url = BASE_URL.format(page_num)
        print(f"Scraping Listing Page {page_num}/{START_PAGE + MAX_PAGES - 1}: {url}")
        
        match = tldextract.extract(url)
        domain = match.domain + '.' + match.suffix
        
        # Retry loop for listing pages
        max_retries = 5
        success = False
        
        for attempt in range(max_retries):
            # Get a fresh proxy (rotate if this isn't the first attempt)
            if attempt > 0:
                print(f"  [Retry {attempt}/{max_retries}] Rotating proxy due to failure...")
                manager.rotate(domain)
                
            proxy = manager.get_proxy(domain)
            
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
                success = True
                break # Move to next page
                
            except Exception as e:
                print(f"  [FAILED] Attempt {attempt+1}: {e}")
                import traceback
                # traceback.print_exc() # Reduce noise
                continue
        
                continue
        
        if not success:
            print(f"  [WARN] All {max_retries} proxy attempts failed. Trying DIRECT connection (No Proxy)...")
            try:
                # Last resort: Direct connection
                html, card_count = await crawl_with_playwright(url, proxy=None, headless=True)
                print(f"  [OK] Direct connection successful! Cards detected: {card_count}")
                
                soup = BeautifulSoup(html, 'html.parser')
                cards = soup.select('.o-announ-card-column a.o-announ-card-content')
                extracted_count = 0
                for card in cards:
                    href = card.get('href')
                    if href:
                        full_url = f"https://www.ouedkniss.com{href}" if href.startswith('/') else href
                        all_found_urls.append(full_url)
                        extracted_count += 1
                print(f"  [SUCCESS] Extracted {extracted_count} URLs (Direct)")
                success = True
                
            except Exception as e:
                print(f"  [FAILED] Direct connection also failed: {e}")
                print(f"[ERROR] Failed to scrape page {page_num} completely. Skipping.")

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
    proxies = await fetch_proxies()
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
        browser = await p.chromium.launch(headless=True)
        sem = asyncio.Semaphore(CONCURRENCY)

        async def process_url(url):
            async with sem:
                # Use a fresh context with a proxy for EACH request (or rotated)
                domain = "ouedkniss.com"
                proxy = manager.get_proxy(domain)
                
                context = None
                try:
                    context_options = {
                        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
                    }
                    if proxy:
                        context_options["proxy"] = {"server": proxy}
                        # print(f"  Using proxy for detail: {proxy}")

                    context = await browser.new_context(**context_options)
                    
                    extractor = DetailExtractor(context)
                    data = await extractor.extract(url)
                    
                    if data:
                        announcements.append(data)
                    else:
                        # If failed, maybe rotate proxy?
                        manager.rotate(domain)
                    
                    return data
                except Exception as e:
                    print(f"Error processing {url}: {e}")
                    manager.rotate(domain)
                    return None
                finally:
                    if context:
                        await context.close()

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
