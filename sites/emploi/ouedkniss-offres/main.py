# main.py - Ouedkniss Emploi Offres with ProxyManager
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
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from scraper.proxy.proxy_sources import fetch_proxies
from scraper.proxy.proxy_manager import ProxyManager
from scraper.crawler.crawler_runner import crawl
from scraper.browser.fingerprint import build_context
from scraper.utils.logger import get_logger

# ========================= CONFIG =========================
log = get_logger("main_scraper_emploi_offres")

TARGET_URL_BASE = "https://www.ouedkniss.com/emploi_offres/"

BATCH_SIZE = 10
MAX_CONCURRENT_LISTING = 2
MAX_CONCURRENT_DETAILS = 5
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

        # Check for errors
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                log.error(f"Page {page + i} failed: {r}")

        # Move to next batch
        page += BATCH_SIZE
        await asyncio.sleep(DELAY_BETWEEN_BATCHES)


async def scrape_listing_page(page_num, sem, proxy_manager):
    """Scrape one listing page and extract job URLs"""
    async with sem:
        url = f"{TARGET_URL_BASE}{page_num}"
        log.info(f"Listing page {page_num}: {url}")

        # Get proxy
        proxy_url = await proxy_manager.get_proxy()
        if not proxy_url:
            log.warning(f"No proxy available for page {page_num}")
            return

        browser_config = BrowserConfig(
            headless=True,
            browser_type="chromium",
            text_mode=False,
            proxy=proxy_url
        )

        try:
            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(
                    url=url,
                    config=CrawlerRunConfig(
                        cache_mode=CacheMode.BYPASS,
                        delay_before_return_html=5
                    )
                )

                if not result.success:
                    log.error(f"Page {page_num} failed: {result.error_message}")
                    await proxy_manager.mark_bad(proxy_url)
                    return

                # Parse itemListElement from JSON-LD
                pattern = re.compile(r'"itemListElement":(\[.*?\])', re.DOTALL)
                matches = pattern.findall(result.html)

                if matches and len(matches) >= 2:
                    try:
                        data = json.loads(matches[1])
                        log.info(f"Found {len(data)} jobs on page {page_num}")

                        # Extract URLs and add to queue
                        for item in data:
                            job_url = item.get('url')
                            if job_url:
                                await url_queue.put(job_url)

                    except json.JSONDecodeError as e:
                        log.error(f"JSON parse error on page {page_num}: {e}")
                else:
                    log.warning(f"No itemListElement found on page {page_num}")

        except Exception as e:
            log.error(f"Exception on page {page_num}: {e}")
            await proxy_manager.mark_bad(proxy_url)


async def detail_consumer(worker_id, proxy_manager):
    """Consume URLs from queue and scrape details"""
    while True:
        try:
            url = await asyncio.wait_for(url_queue.get(), timeout=30)
        except asyncio.TimeoutError:
            log.info(f"Worker {worker_id} timeout, exiting")
            break

        log.info(f"Worker {worker_id} scraping: {url}")

        try:
            await scrape_single_url(url, proxy_manager)
        except Exception as e:
            log.error(f"Worker {worker_id} error on {url}: {e}")

        url_queue.task_done()
        await asyncio.sleep(2)  # Be polite


async def main():
    """Main orchestrator"""
    log.info("Starting Ouedkniss Emploi Offres scraper")

    # Fetch proxies
    log.info("Fetching proxies...")
    proxies = await fetch_proxies()
    log.info(f"Got {len(proxies)} proxies")

    proxy_manager = ProxyManager(proxies)

    # Start producer and consumers
    producer_task = asyncio.create_task(listing_producer(proxy_manager))

    consumer_tasks = [
        asyncio.create_task(detail_consumer(i, proxy_manager))
        for i in range(MAX_CONCURRENT_DETAILS)
    ]

    # Wait for consumers to finish
    await asyncio.gather(*consumer_tasks, return_exceptions=True)

    # Cancel producer
    producer_task.cancel()
    log.info("Scraping complete")


if __name__ == "__main__":
    asyncio.run(main())
