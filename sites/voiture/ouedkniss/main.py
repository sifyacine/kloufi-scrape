# main_pipeline.py
import asyncio
import json
import re
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from scrape_details import scrape_single_url
from datetime import datetime

# ========================= CONFIG =========================
PROXY_URL = "https://proxyium.com/"
TARGET_URL_BASE = "https://www.ouedkniss.com/automobiles_vehicules/"

BATCH_SIZE = 10                  # Lower burst
MAX_CONCURRENT_LISTING = 2
MAX_CONCURRENT_DETAILS = 5       # Stabilize
DELAY_BETWEEN_BATCHES = 5
# =========================================================

browser_config = BrowserConfig(
    headless=True,
    text_mode=False,
    browser_type="chromium",
    java_script_enabled=True,
)

# Queue to send URLs from listing scraper → detail workers
url_queue = asyncio.Queue(maxsize=1000)

async def listing_producer():
    """Crawls listing pages in batches of 20 and feeds URLs into queue"""
    page = 1
    batch_count = 0

    while True:
        batch_count += 1
        print(f"\nStarting BATCH #{batch_count} → pages {page} to {page + BATCH_SIZE - 1}")

        # Scrape current batch concurrently
        listing_sem = asyncio.Semaphore(MAX_CONCURRENT_LISTING)
        tasks = [
            scrape_listing_page(p, listing_sem)
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

async def scrape_listing_page(page_number: int, semaphore):
    async with semaphore:
        target_url = f"{TARGET_URL_BASE}{page_number}" if page_number > 1 else f"{TARGET_URL_BASE}"
        attempt = 1

        while True:
            print(f"--- Listing Page {page_number} - Attempt #{attempt} ---")
            js_commands = [
                "await new Promise(resolve => setTimeout(resolve, 10000));",
                "localStorage.setItem('ok-auth-frame', JSON.stringify({ locale: 'fr' }));",
                "document.cookie = 'ok-locale=fr; path=/; domain=.ouedkniss.com';",
                "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",
                f"document.getElementById('unique-form-control').value = '{target_url}{'&' if '?' in target_url else '?'}lang=fr';",
                "document.querySelector('#web_proxy_form').submit();",
                "await new Promise(resolve => setTimeout(resolve, 5000));",
                "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",
            ]

            config = CrawlerRunConfig(
                js_code=js_commands, 
                delay_before_return_html=30,
                page_timeout=120000,
                wait_until="domcontentloaded"
            )

            async with AsyncWebCrawler(config=browser_config) as crawler:
                try:
                    result = await crawler.arun(url=PROXY_URL, config=config)
                    if not result.success:
                        print(f"Fetch failed for Page {page_number}. Retrying...")
                        await asyncio.sleep(12)
                        attempt += 1
                        continue

                    # Strategy: Extract URLs from JSON-LD
                    matches = re.findall(r'"itemListElement":(\[.*?\])', result.html, re.DOTALL)
                    if len(matches) >= 2:
                        try:
                            data = json.loads(matches[1])
                            urls = []
                            seen = set()
                            for item in data:
                                url = item.get("url")
                                if url and url not in seen and url.startswith("http"):
                                    seen.add(url)
                                    urls.append(url)
                            
                            if urls:
                                print(f"Successfully scraped {len(urls)} URLs from Page {page_number}")
                                return urls
                            else:
                                # Could be real end or just dynamic load failure
                                if attempt >= 5: # After 5 tries with successful fetch but 0 URLs, assume end
                                    print(f"Page {page_number} seems empty after 5 attempts. Stopping.")
                                    return []
                                print(f"Page {page_number} returned 0 URLs. Retrying ({attempt}/5)...")
                        except Exception as e:
                            print(f"JSON parse error on Page {page_number}: {e}")
                    else:
                        print(f"Listing markers not found on Page {page_number}. Retrying...")
                    
                except Exception as e:
                    print(f"Exception scraping Listing Page {page_number}: {e}")

            await asyncio.sleep(12)
            attempt += 1

async def detail_worker(worker_id: int):
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
            await scrape_single_url(url)  # This already saves to ES
            print(f"Worker #{worker_id} saved to ES")
        except Exception as e:
            print(f"Worker #{worker_id} failed {url} → {e}")
        finally:
            url_queue.task_done()
            await asyncio.sleep(0.8)  # Be gentle

async def main():
    print("OuedKniss Pipeline Scraper STARTED")
    print("├── Batch size:", BATCH_SIZE)
    print("├── Concurrent listing pages:", MAX_CONCURRENT_LISTING)
    print("└── Concurrent detail scrapers:", MAX_CONCURRENT_DETAILS)

    # Start detail workers (they will wait for URLs)
    workers = [
        asyncio.create_task(detail_worker(i+1))
        for i in range(MAX_CONCURRENT_DETAILS)
    ]

    # Start the producer (crawls listing pages in batches)
    producer = asyncio.create_task(listing_producer())

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