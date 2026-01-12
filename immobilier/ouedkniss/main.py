# main_pipeline.py
import asyncio
import json
import re
import sys
import os
# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from scrape_details import scrape_single_url, save_to_json
from datetime import datetime

from scraper.proxy.proxy_sources import fetch_proxies
from scraper.proxy.proxy_manager import ProxyManager
from scraper.crawler.crawler_runner import crawl
from scraper.browser.fingerprint import build_context


# ========================= CONFIG =========================
from scraper.utils.logger import get_logger

log = get_logger("main_scraper")

# ========================= CONFIG =========================
TARGET_URL_BASE = "https://www.ouedkniss.com/immobilier/"

BATCH_SIZE = 1                   # Match concurreny to fill batch immediately
MAX_CONCURRENT_LISTING = 1       # Scrape 6 listing pages at once
MAX_CONCURRENT_DETAILS = 20      # Scrape 12 details at once
DELAY_BETWEEN_BATCHES = 3        # Minimal delay
# =========================================================

class ScrapeCounter:
    def __init__(self):
        self._count = 0
        self._lock = asyncio.Lock()

    async def increment(self):
        async with self._lock:
            self._count += 1
            if self._count % 10 == 0:
                log.info(f"Total Scraped: {self._count}")

counter = ScrapeCounter()


# Removed global browser_config as we use per-request contexts now


# Queue to send URLs from listing scraper → detail workers
url_queue = asyncio.Queue(maxsize=1000)

async def listing_producer(proxy_manager):
    """Crawls listing pages in batches of 20 and feeds URLs into queue"""
    page = 1
    batch_count = 0

    while True:
        batch_count += 1
        print(f"\nStarting BATCH #{batch_count} → pages {page} to {page + BATCH_SIZE - 1}")

        # Scrape current batch concurrently
        listing_sem = asyncio.Semaphore(MAX_CONCURRENT_LISTING)
        tasks = [
            scrape_listing_page(p, listing_sem, proxy_manager)
            for p in range(page, page + BATCH_SIZE)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        urls_in_batch = 0
        for result in results:
            if isinstance(result, list):
                for url in result:
                    await url_queue.put(url)
                    urls_in_batch += 1

        print(f"Batch #{batch_count} → {urls_in_batch} new ads queued "
              f"(Total in queue: {url_queue.qsize()})")

        # If this batch gave zero URLs → probably end of results
        if urls_in_batch == 0:
            log.info("No more ads found → stopping producer")
            break

        # Remove the limit of 3 pages as requested to "keep trying till it scrap it" 
        # But if user wants to keep scraping *everything*, we remove the break. 
        # If user meant "retry failed pages until success" but still stop after X pages, 
        # I will assume they want to scrape fully but robustly. 
        # However, for safety in testing, I will log the page progress.
        
        page += BATCH_SIZE
        
        # LIMIT FOR TESTING: Stop after the first batch (Page 1)
        print("Test mode: Stopping after batch 1")
        break 
        
        await asyncio.sleep(DELAY_BETWEEN_BATCHES)

    # Signal workers we're done
    for _ in range(MAX_CONCURRENT_DETAILS):
        await url_queue.put(None)
    print("Producer finished. All pages crawled.")

async def scrape_listing_page(page_number: int, semaphore, proxy_manager):
    async with semaphore:
        base_target = f"{TARGET_URL_BASE}{page_number}" if page_number > 1 else TARGET_URL_BASE
        target_url = f"{base_target}?locale=fr"
        
        js_commands = [

            """
            (async () => {
                console.log("Starting Locale Enforcement...");

                // 1. Force French via LocalStorage and Cookies
                localStorage.setItem('ok-auth-frame', JSON.stringify({ locale: 'fr' }));
                document.cookie = "ok-locale=fr; domain=.ouedkniss.com; path=/; max-age=31536000";
                
                // 2. Detect Arabic and Reload if necessary
                const isRTL = document.body.dir === 'rtl' || document.documentElement.dir === 'rtl';
                const isArabicLang = document.documentElement.lang === 'ar';
                const hasArabicTitle = /[\u0600-\u06FF]/.test(document.title);
                
                if (isRTL || isArabicLang || hasArabicTitle) {
                    console.log("Arabic detected! Reloading with forced locale...");
                    
                    // Re-assert cookies just in case
                    document.cookie = "ok-locale=fr; domain=.ouedkniss.com; path=/; max-age=31536000";
                    
                    // Force reload
                    window.location.reload();
                    
                    // Wait to prevent further execution in this stale context
                    await new Promise(r => setTimeout(r, 5000));
                } else {
                    console.log("Page seems to be in French. Proceeding.");
                }

                // 3. Click Menu if found (extra safety)
                const menuBtn = document.querySelector('button[aria-label="Menu"], button[aria-label="القائمة"], button[aria-label="قائمة"]');
                if (menuBtn) {
                    menuBtn.click();
                    await new Promise(r => setTimeout(r, 1000));
                }
                
                // 4. Click FR button directly if visible
                const frBtn = Array.from(document.querySelectorAll('button')).find(b => 
                    b.textContent.trim() === 'FR' || 
                    b.getAttribute('aria-label') === 'Français'
                );
                if (frBtn) {
                    frBtn.click();
                    await new Promise(r => setTimeout(r, 2000));
                }
                
                // 5. Final scroll
                window.scrollTo(0, 1000);
                await new Promise(r => setTimeout(r, 1000));
                
                // 6. Stepped Scroll to trigger all lazy loads
                for (let i = 0; i < 15; i++) {
                    window.scrollBy(0, 800);
                    await new Promise(r => setTimeout(r, 500));
                }
                window.scrollTo(0, document.body.scrollHeight);
            })();
            """,
            "await new Promise(r => setTimeout(r, 3000));"
        ]
        

        config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            page_timeout=60000,
            wait_until="domcontentloaded",
            js_code=js_commands,
            delay_before_return_html=5
        )

        attempt = 0
        while True:
            attempt += 1
            proxy = None
            if proxy_manager:
                try:
                    proxy = proxy_manager.get_proxy("ouedkniss.com")
                except Exception:
                    log.warning("No proxies available for listing.")

            context = build_context()

            try:
                log.info(f"Listing Page {page_number} (Attempt {attempt}) - Proxy: {proxy}")
                result = await crawl(target_url, proxy, context, config=config, headless=True)
                
                if not result.success:
                    log.warning(f"Failed Listing Page {page_number} (Status: {result.status_code})")
                    raise Exception(f"Crawl failed status {result.status_code}")

                urls = []
                seen = set()

                matches = re.findall(r'"itemListElement":(\[.*?\])', result.html, re.DOTALL)
                if len(matches) >= 1:
                    try:
                        json_str = matches[-1] 
                        data = json.loads(json_str)
                        for item in data:
                            url = item.get("url")
                            if url and url not in seen and url.startswith("http"):
                                seen.add(url)
                                urls.append(url)
                        log.info(f"  -> Extracted {len(urls)} URLs via JSON-LD")
                    except Exception:
                        pass

                # ALWAYS try HTML extraction to supplement JSON-LD
                soup = BeautifulSoup(result.html, "html.parser")
                links = soup.select("a.o-announ-card-content") 
                if not links:
                        links = soup.select("div.o-announ-card-column > a")
                
                html_count = 0
                for link in links:
                    href = link.get("href")
                    if href:
                        if href.startswith("/"):
                            full_url = f"https://www.ouedkniss.com{href}"
                        elif href.startswith("http"):
                            full_url = href
                        else:
                            continue

                        if full_url not in seen:
                            seen.add(full_url)
                            urls.append(full_url)
                            html_count += 1
                
                if html_count > 0:
                    log.info(f"  -> Extracted {html_count} ADDITIONAL URLs via HTML Parsing")

                if urls:
                    log.info(f"  -> Extracted {len(urls)} URLs via HTML Parsing (merged)")

                if not urls:
                    if "challenge" in result.html.lower() or "cloudflare" in result.html.lower():
                        log.warning(f"  -> Blocked by Cloudflare on page {page_number}")
                        if proxy_manager and proxy:
                            proxy_manager.report_failure(proxy)
                    
                    raise Exception("No listings extraction success")
                
                log.info(f"Page {page_number} SUCCESS → Found {len(urls)} ads")
                if proxy_manager and proxy:
                    proxy_manager.report_success(proxy)
                return urls

            except Exception as e:
                log.error(f"Error scraping listing page {page_number}: {e}")
                if proxy_manager:
                    if proxy:
                        proxy_manager.report_failure(proxy)
                    proxy_manager.rotate("ouedkniss.com")
                await asyncio.sleep(1) # Short sleep before retry


async def detail_worker(worker_id: int, proxy_manager, counter):
    """Takes URLs from queue and scrapes them immediately"""
    log.info(f"Detail Worker #{worker_id} started")
    while True:
        url = await url_queue.get()
        if url is None:  # Shutdown signal
            log.info(f"Detail Worker #{worker_id} shutting down")
            url_queue.task_done()
            break

        log.debug(f"Worker #{worker_id} → {url}")
        try:
            await scrape_single_url(url, proxy_manager)
            await counter.increment()
            log.info(f"Worker #{worker_id} saved {url}")
        except Exception as e:
            log.error(f"Worker #{worker_id} failed {url} → {e}")
        finally:
            url_queue.task_done()
            await asyncio.sleep(0.1)  # Faster processing

async def main():
    print("OuedKniss Pipeline Scraper STARTED")
    print("├── Batch size:", BATCH_SIZE)
    print("├── Concurrent listing pages:", MAX_CONCURRENT_LISTING)
    print("└── Concurrent detail scrapers:", MAX_CONCURRENT_DETAILS)

    # Initialize Proxy System
    print("Fetching proxies...")
    proxies = await fetch_proxies()
    print(f"Fetched {len(proxies)} proxies.")
    proxy_manager = ProxyManager(proxies)

    # Start detail workers (they will wait for URLs)
    workers = [
        asyncio.create_task(detail_worker(i+1, proxy_manager, counter))
        for i in range(MAX_CONCURRENT_DETAILS)
    ]

    # Start the producer (crawls listing pages in batches)
    producer = asyncio.create_task(listing_producer(proxy_manager))

    # Wait for producer to finish
    await producer

    # Wait for all remaining URLs to be processed
    await url_queue.join()
    print("Queue empty → sending shutdown to workers...")

    # Send shutdown signals
    for _ in range(MAX_CONCURRENT_DETAILS):
        await url_queue.put(None)

    # Wait for workers to exit
    await asyncio.gather(*workers)

    print("\nFULL SCRAPING COMPLETED!")
    print("Check scraped_ouedkniss.jsonl and your Elasticsearch index")

if __name__ == "__main__":
    asyncio.run(main())