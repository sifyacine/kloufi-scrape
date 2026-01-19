# main_pipeline.py
import asyncio
import json
import re
import sys
import os
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from scrape_details import scrape_single_url
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from scraper.proxy.proxy_sources import fetch_proxies
from scraper.proxy.proxy_manager import ProxyManager
from scraper.crawler.crawler_runner import crawl
from scraper.browser.fingerprint import build_context
from scraper.utils.logger import get_logger

# ========================= CONFIG =========================
log = get_logger("main_scraper_voiture")

TARGET_URL_BASE = "https://www.ouedkniss.com/automobiles_vehicules/"

BATCH_SIZE = 10                  # Lower burst
MAX_CONCURRENT_LISTING = 2
MAX_CONCURRENT_DETAILS = 5       # Stabilize
DELAY_BETWEEN_BATCHES = 5
# =========================================================

# Queue to send URLs from listing scraper → detail workers
url_queue = asyncio.Queue(maxsize=1000)

async def listing_producer(proxy_manager):
    """Crawls listing pages in batches and feeds URLs into queue"""
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
            print("No more ads found → stopping producer")
            break

        page += BATCH_SIZE
        await asyncio.sleep(DELAY_BETWEEN_BATCHES)

    # Signal workers we're done
    for _ in range(MAX_CONCURRENT_DETAILS):
        await url_queue.put(None)
    print("Producer finished. All pages crawled.")

async def scrape_listing_page(page_number: int, semaphore, proxy_manager):
    async with semaphore:
        target_url = f"{TARGET_URL_BASE}{page_number}" if page_number > 1 else f"{TARGET_URL_BASE}"
        # append lang=fr or locale=fr parameter if supported/needed by the site, but usually cookies/localstorage do it
        target_url += "?locale=fr"

        
        js_commands = [
            """
            (async () => {
                // 1. Force French via LocalStorage and Cookies
                localStorage.setItem('ok-auth-frame', JSON.stringify({ locale: 'fr' }));
                document.cookie = "ok-locale=fr; domain=.ouedkniss.com; path=/; max-age=31536000";
                
                // 2. Click Menu if found (extra safety for language)
                const menuBtn = document.querySelector('button[aria-label="Menu"], button[aria-label="القائمة"], button[aria-label="قائمة"]');
                if (menuBtn) {
                    menuBtn.click();
                    await new Promise(r => setTimeout(r, 1000));
                }
                
                // 3. Click FR button directly if visible
                const frBtn = Array.from(document.querySelectorAll('button')).find(b => 
                    b.textContent.trim() === 'FR' || 
                    b.getAttribute('aria-label') === 'Français'
                );
                if (frBtn) {
                    frBtn.click();
                    await new Promise(r => setTimeout(r, 2000));
                }

                // 4. Stepped Scroll to trigger all lazy loads
                window.scrollTo(0, 1000);
                await new Promise(r => setTimeout(r, 1000));
                
                for (let i = 0; i < 15; i++) {
                    window.scrollBy(0, 1000);
                    await new Promise(r => setTimeout(r, 400));
                }
                window.scrollTo(0, document.body.scrollHeight);
                await new Promise(r => setTimeout(r, 2000));
            })();
            """
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
            if attempt > 5:
                log.warning(f"Page {page_number} failed after 5 attempts. Skipping.")
                return []

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
                    log.warning(f"Fetch failed for Page {page_number}. Retrying...")
                    if proxy_manager and proxy:
                        proxy_manager.report_failure(proxy)
                    await asyncio.sleep(2)
                    continue

                if proxy_manager and proxy:
                    proxy_manager.report_success(proxy)

                # Strategy: Extract URLs from JSON-LD using BeautifulSoup (More Robust)
                soup = BeautifulSoup(result.html, "html.parser")
                urls = []
                seen = set()

                # 1. JSON-LD Extraction
                script_tags = soup.find_all("script", type="application/ld+json")
                for script in script_tags:
                    if not script.string:
                        continue
                    try:
                        data = json.loads(script.string)
                        # Check if it's the ItemList
                        if isinstance(data, dict) and (data.get("@type") == "ItemList" or "itemListElement" in data):
                            items = data.get("itemListElement", [])
                            for item in items:
                                url = item.get("url")
                                if url and url not in seen and url.startswith("http"):
                                    seen.add(url)
                                    urls.append(url)
                        # Sometimes it's a list of objects
                        elif isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict) and "itemListElement" in item:
                                     items = item.get("itemListElement", [])
                                     for sub_item in items:
                                        url = sub_item.get("url")
                                        if url and url not in seen and url.startswith("http"):
                                            seen.add(url)
                                            urls.append(url)
                    except Exception as e:
                        log.debug(f"JSON extract warning: {e}")

                # 2. Fallback HTML Extraction if JSON failed or returned few results
                if len(urls) < 5:
                    selectors = [
                        "a.o-announ-card-content", 
                        "div.o-announ-card-column > a",
                        "a.v-card",
                        "div.announcement-card a",
                        ".o-announ-card a"
                    ]
                    for sel in selectors:
                        found = soup.select(sel)
                        for link in found:
                            href = link.get("href")
                            if href:
                                if href.startswith("/"):
                                     if not re.search(r'/[^/]+-d\d+$', href): 
                                         if "/automobiles_vehicules-" in href: continue
                                     full_url = f"https://www.ouedkniss.com{href}"
                                elif href.startswith("https://www.ouedkniss.com"):
                                    full_url = href
                                else:
                                    continue
                                
                                if full_url not in seen:
                                    seen.add(full_url)
                                    urls.append(full_url)

                if urls:
                    print(f"Successfully scraped {len(urls)} URLs from Page {page_number}")
                    return urls
                else:
                    # Check for "no results" markers
                    no_results_markers = [
                        "aucune annonce trouvée", 
                        "aucun résultat ne correspond",
                        "no results found"
                    ]
                    page_text = soup.get_text().lower()
                    if any(marker in page_text for marker in no_results_markers):
                        print(f"Page {page_number} seems empty (No Results). Stopping.")
                        return []
                    
                    print(f"Page {page_number} returned 0 URLs but no empty marker. Retrying...")
                    
            except Exception as e:
                log.error(f"Exception scraping Listing Page {page_number}: {e}")
                if proxy_manager and proxy:
                    proxy_manager.report_failure(proxy)
                    proxy_manager.rotate("ouedkniss.com")

            await asyncio.sleep(2)

async def detail_worker(worker_id: int, proxy_manager):
    """Takes URLs from queue and scrapes them immediately"""
    print(f"Detail Worker #{worker_id} started")
    while True:
        url = await url_queue.get()
        if url is None:  # Shutdown signal
            print(f"Detail Worker #{worker_id} shutting down")
            url_queue.task_done()
            break

        print(f"Worker #{worker_id} → {url}")
        try:
            await scrape_single_url(url, proxy_manager)
            print(f"Worker #{worker_id} finished {url}")
        except Exception as e:
            print(f"Worker #{worker_id} failed {url} → {e}")
        finally:
            url_queue.task_done()
            await asyncio.sleep(0.8)

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
        asyncio.create_task(detail_worker(i+1, proxy_manager))
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
    print("Check your Elasticsearch index")

if __name__ == "__main__":
    asyncio.run(main())