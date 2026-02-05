# main_pipeline.py
# ========================= HYBRID MULTI-PASS SCRAPING SYSTEM =========================
# This module implements a three-zone concurrent scraping strategy:
#   - HOT ZONE (pages 1-5): High priority, runs every 10 minutes
#   - WARM ZONE (pages 5-50): Medium priority, runs every 2 hours
#   - COLD ZONE (pages 1-∞): Low priority, runs weekly for backfill
# All zones run concurrently with independent workers and deduplication.
# =====================================================================================

import asyncio
import json
import re
import sys
import os
import time
import hashlib
from enum import Enum
from dataclasses import dataclass, field
from typing import Set, Optional, Dict, List
from collections import deque
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from sites.immobilier.ouedkniss.scrape_details import scrape_single_url
from utils.immobilier import ImmobilierUtils
from datetime import datetime

from scraper.proxy.proxy_sources import fetch_proxies
from scraper.proxy.proxy_manager import ProxyManager
from scraper.crawler.crawler_runner import crawl
from scraper.browser.fingerprint import build_context


# ========================= CONFIG =========================
from scraper.utils.logger import get_logger

log = get_logger("main_scraper")

import argparse


# ========================= ZONE DEFINITIONS =========================
class ZoneType(Enum):
    """Scraping zone types with different priorities and behaviors."""
    REALTIME = "realtime"  # Page 1 only, every 30 seconds - catches new listings immediately
    WARM = "warm"          # Pages 1-∞, every 2 hours - regular full crawl
    COLD = "cold"          # Pages 1-∞, weekly - deep backfill crawl


@dataclass
class ZoneConfig:
    """Configuration for each scraping zone."""
    zone_type: ZoneType
    start_page: int
    end_page: Optional[int]  # None means infinite
    interval_seconds: int
    max_concurrent_details: int
    priority: int  # Lower = higher priority
    throttle_delay: float = 0.1  # Delay between requests
    
    @property
    def name(self) -> str:
        return self.zone_type.value.upper()


# Zone configurations
ZONE_CONFIGS = {
    ZoneType.REALTIME: ZoneConfig(
        zone_type=ZoneType.REALTIME,
        start_page=1,
        end_page=1,                  # Only page 1
        interval_seconds=30,         # Every 30 seconds
        max_concurrent_details=5,    # Fast processing for few URLs
        priority=1,                  # Highest priority
        throttle_delay=0.02          # Minimal delay for speed
    ),
    ZoneType.WARM: ZoneConfig(
        zone_type=ZoneType.WARM,
        start_page=1,                # Start from page 1
        end_page=None,               # Scrape everything
        interval_seconds=7200,       # 2 hours
        max_concurrent_details=10,
        priority=2,
        throttle_delay=0.15
    ),
    ZoneType.COLD: ZoneConfig(
        zone_type=ZoneType.COLD,
        start_page=1,                # Start from page 1
        end_page=None,               # Scrape everything
        interval_seconds=604800,     # 1 week
        max_concurrent_details=5,    # Throttled
        priority=3,
        throttle_delay=0.5           # Slower to reduce load
    ),
}


# ========================= URL DEDUPLICATION =========================
class URLDeduplicator:
    """
    Thread-safe URL deduplication with persistent storage.
    Prevents re-processing of already-scraped items across all zones.
    Stores full URLs for debugging and transparency.
    """
    
    def __init__(self, cache_file: str = "scraped_urls_cache.json"):
        self._seen_urls: Set[str] = set()
        self._lock = asyncio.Lock()
        self._cache_file = Path(__file__).parent / cache_file
        self._load_cache()
    
    def _load_cache(self):
        """Load previously seen URLs from disk."""
        try:
            if self._cache_file.exists():
                with open(self._cache_file, 'r') as f:
                    data = json.load(f)
                    self._seen_urls = set(data.get('urls', []))
                    log.info(f"Loaded {len(self._seen_urls)} URLs from dedup cache")
        except Exception as e:
            log.warning(f"Could not load dedup cache: {e}")
    
    async def save_cache(self):
        """Persist seen URLs to disk."""
        async with self._lock:
            try:
                with open(self._cache_file, 'w') as f:
                    json.dump({'urls': list(self._seen_urls)}, f, indent=2)
            except Exception as e:
                log.warning(f"Could not save dedup cache: {e}")
    
    async def is_seen(self, url: str) -> bool:
        """Check if URL was already processed."""
        async with self._lock:
            return url in self._seen_urls
    
    async def mark_seen(self, url: str):
        """Mark URL as processed."""
        async with self._lock:
            self._seen_urls.add(url)
    
    async def filter_new_urls(self, urls: List[str]) -> List[str]:
        """Filter out already-seen URLs, return only new ones."""
        new_urls = []
        async with self._lock:
            for url in urls:
                if url not in self._seen_urls:
                    new_urls.append(url)
        return new_urls
    
    async def get_stats(self) -> Dict:
        """Get deduplication statistics."""
        async with self._lock:
            return {
                'total_seen': len(self._seen_urls),
            }


# Global deduplicator instance
url_deduplicator = URLDeduplicator()


# ========================= ARGUMENT PARSING =========================
parser = argparse.ArgumentParser(description="Ouedkniss Immobilier Scraper - Hybrid Multi-Pass System")
parser.add_argument("--transaction", type=str, default=os.getenv("TRANSACTION", ""), help="Transaction type (e.g. vente, location)")
parser.add_argument("--bien", type=str, default=os.getenv("BIEN", ""), help="Property type (e.g. appartement, villa)")
parser.add_argument("--zone", type=str, default=os.getenv("ZONE", "all"), 
                    choices=["realtime", "warm", "cold", "all"], 
                    help="Zone to run: realtime (page 1 every 30s), warm (all pages every 2h), cold (all pages weekly), or all (default: all)")
parser.add_argument("--continuous", action="store_true", default=os.getenv("CONTINUOUS", "false").lower() == "true",
                    help="Run continuously with scheduled intervals")
parser.add_argument("--single-pass", action="store_true", default=False,
                    help="Run a single pass then exit (default behavior for backward compatibility)")
args = parser.parse_args()


# Normalization mapping for common slugs
SLUG_NORMALIZATION = {
    "location-vacance": "location-vacances",
    "location-vacances": "location-vacances",
    "vente": "vente",
    "location": "location",
    "echange": "echange",
    "cherche-achat": "cherche-achat",
    "cherche-location": "cherche-location",
    # Bien types
    "appartement": "appartement",
    "villa": "villa",
    "terrain": "terrain",
    "niveau-de-villa": "niveau-de-villa",
    "studio": "studio",
    "local": "local",
}

def normalize_slug(slug):
    if not slug: return ""
    cleaned = slug.strip().lower()
    return SLUG_NORMALIZATION.get(cleaned, cleaned)

TRANSACTION = normalize_slug(args.transaction)
BIEN = normalize_slug(args.bien)

# Construct the base URL dynamically
base_slug = "immobilier"
if TRANSACTION:
    base_slug += f"-{TRANSACTION}"
if BIEN:
    base_slug += f"-{BIEN}"

TARGET_URL_BASE = f"https://www.ouedkniss.com/{base_slug}/"
# Force French via URL parameter to avoid JS reloads
TARGET_URL_PARAMS = "?locale=fr"
log.info(f"Targeting Base URL: {TARGET_URL_BASE} (Force FR: {TARGET_URL_PARAMS})")

# ========================= LEGACY CONFIG (preserved for backward compatibility) =========================
BATCH_SIZE = 1                   # Match concurrency to fill batch immediately
MAX_CONCURRENT_LISTING = 1       # Scrape 1 listing page at once
MAX_CONCURRENT_DETAILS = 20      # Scrape 20 details at once
DELAY_BETWEEN_BATCHES = 3        # Minimal delay
# =========================================================================================================


class ScrapeCounter:
    """Thread-safe counter for tracking scrape progress across zones."""
    def __init__(self):
        self._counts: Dict[str, int] = {"hot": 0, "warm": 0, "cold": 0, "total": 0}
        self._lock = asyncio.Lock()

    async def increment(self, zone: str = "total"):
        async with self._lock:
            self._counts[zone] = self._counts.get(zone, 0) + 1
            self._counts["total"] += 1
            if self._counts["total"] % 10 == 0:
                log.info(f"Scraped → Total: {self._counts['total']} | "
                        f"Hot: {self._counts['hot']} | Warm: {self._counts['warm']} | Cold: {self._counts['cold']}")

    async def get_counts(self) -> Dict[str, int]:
        async with self._lock:
            return self._counts.copy()


counter = ScrapeCounter()


# ========================= ZONE RUNNER CLASS =========================
class ZoneRunner:
    """
    Manages scraping for a specific zone with its own queue and workers.
    Each zone operates independently with its own concurrency settings.
    """
    
    def __init__(self, config: ZoneConfig, proxy_manager: ProxyManager, deduplicator: URLDeduplicator):
        self.config = config
        self.proxy_manager = proxy_manager
        self.deduplicator = deduplicator
        self.url_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._running = False
        self._workers: List[asyncio.Task] = []
        self._producer_task: Optional[asyncio.Task] = None
        self._last_run: Optional[datetime] = None
        self._pages_scraped = 0
        self._urls_processed = 0
    
    async def start(self):
        """Start the zone's producer and workers."""
        if self._running:
            log.warning(f"[{self.config.name}] Zone already running")
            return
        
        self._running = True
        log.info(f"[{self.config.name}] Starting zone (pages {self.config.start_page}-{self.config.end_page or '∞'})")
        
        # Start detail workers
        self._workers = [
            asyncio.create_task(self._detail_worker(i + 1))
            for i in range(self.config.max_concurrent_details)
        ]
        
        # Start producer
        self._producer_task = asyncio.create_task(self._listing_producer())
        self._last_run = datetime.now()
    
    async def stop(self):
        """Stop the zone gracefully."""
        self._running = False
        log.info(f"[{self.config.name}] Stopping zone...")
        
        # Signal workers to stop
        for _ in range(self.config.max_concurrent_details):
            await self.url_queue.put(None)
        
        # Wait for workers
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        
        # Cancel producer if still running
        if self._producer_task and not self._producer_task.done():
            self._producer_task.cancel()
            try:
                await self._producer_task
            except asyncio.CancelledError:
                pass
        
        log.info(f"[{self.config.name}] Zone stopped. Processed {self._urls_processed} URLs from {self._pages_scraped} pages")
    
    async def run_single_pass(self):
        """Run a single complete pass of this zone."""
        await self.start()
        
        # Wait for producer to finish
        if self._producer_task:
            await self._producer_task
        
        # Wait for queue to drain
        await self.url_queue.join()
        
        # Stop workers
        await self.stop()
        
        # Save deduplication cache
        await self.deduplicator.save_cache()
    
    async def _listing_producer(self):
        """Crawls listing pages and feeds URLs into the zone's queue."""
        page = self.config.start_page
        consecutive_empty = 0
        max_consecutive_empty = 3  # Stop after 3 consecutive empty pages
        
        while self._running:
            # Check if we've reached the end page
            if self.config.end_page and page > self.config.end_page:
                log.info(f"[{self.config.name}] Reached end page {self.config.end_page}")
                break
            
            try:
                urls = await self._scrape_listing_page(page)
                
                if not urls:
                    consecutive_empty += 1
                    if consecutive_empty >= max_consecutive_empty:
                        log.info(f"[{self.config.name}] No more listings found after {max_consecutive_empty} empty pages")
                        break
                else:
                    consecutive_empty = 0
                    
                    # Filter already-seen URLs
                    new_urls = await self.deduplicator.filter_new_urls(urls)
                    
                    if new_urls:
                        log.info(f"[{self.config.name}] Page {page}: {len(new_urls)} new URLs (filtered {len(urls) - len(new_urls)} duplicates)")
                        for url in new_urls:
                            await self.url_queue.put(url)
                    else:
                        log.debug(f"[{self.config.name}] Page {page}: All {len(urls)} URLs already seen")
                
                self._pages_scraped += 1
                page += 1
                
                # Zone-specific delay
                await asyncio.sleep(self.config.throttle_delay)
                
            except Exception as e:
                log.error(f"[{self.config.name}] Producer error on page {page}: {e}")
                await asyncio.sleep(1)
        
        # Signal workers that producer is done
        for _ in range(self.config.max_concurrent_details):
            await self.url_queue.put(None)
        
        log.info(f"[{self.config.name}] Producer finished. Scraped {self._pages_scraped} pages")
    
    async def _scrape_listing_page(self, page_number: int) -> List[str]:
        """Scrape a single listing page and return URLs."""
        base_target = f"{TARGET_URL_BASE}{page_number}" if page_number > 1 else TARGET_URL_BASE
        target_url = f"{base_target}{TARGET_URL_PARAMS}" # Append locale parameter
        
        js_commands = [
            # Helper to wait for elements
            "const wait = ms => new Promise(r => setTimeout(r, ms));",
            """
            (async () => {
                console.log("Starting Passive Locale Enforcement...");
                localStorage.setItem('ok-auth-frame', JSON.stringify({ locale: 'fr' }));
                document.cookie = "ok-locale=fr; domain=.ouedkniss.com; path=/; max-age=31536000";
                
                // 4. Click FR button ONLY if visible and not already active
                const frBtn = Array.from(document.querySelectorAll('button, a')).find(b => 
                    (b.textContent.trim().toUpperCase() === 'FR' || b.getAttribute('aria-label') === 'Français') &&
                    !b.classList.contains('v-btn--active')
                );
                if (frBtn) {
                    frBtn.click();
                    await wait(2000);
                }
                
                // 5. Stepped Scroll to trigger all lazy loads
                for (let i = 0; i < 15; i++) {
                    window.scrollBy(0, 800);
                    await wait(300);
                }
                window.scrollTo(0, document.body.scrollHeight);
                await wait(2000);
            })();
            """,
            "await new Promise(r => setTimeout(r, 5000));"
        ]
        

        config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            page_timeout=60000,
            wait_until="networkidle", # More lenient for slower VPS
            js_code=js_commands,
            delay_before_return_html=5
        )

        max_retries = 5
        for attempt in range(1, max_retries + 1):
            proxy = None
            if self.proxy_manager:
                try:
                    proxy = self.proxy_manager.get_proxy("ouedkniss.com")
                except Exception:
                    log.warning(f"[{self.config.name}] No proxies available for listing.")

            try:
                log.info(f"[{self.config.name}] Page {page_number} (Attempt {attempt}) - Proxy: {proxy}")
                
                # Robust crawl with error handling for partial results
                result = None
                try:
                    result = await crawl(target_url, proxy, context, config=config, headless=True)
                except Exception as e:
                    log.warning(f"[{self.config.name}] Crawl error (possible timeout): {e}")
                    # If we have a log of the failure, it might be in crawl logs
                    raise # Re-raise to trigger catch block
                
                if not result.success:
                    log.warning(f"[{self.config.name}] Failed Page {page_number} (Status: {result.status_code})")
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
                        log.debug(f"[{self.config.name}] Extracted {len(urls)} URLs via JSON-LD")
                    except Exception:
                        pass

                # ALWAYS try HTML extraction to supplement JSON-LD
                soup = BeautifulSoup(result.html, "html.parser")
                
                # Check for "No results" markers to avoid infinite retries on invalid pages
                no_results_markers = [
                    "aucune annonce trouvée", 
                    "aucun résultat ne correspond",
                    "أية نتيجة", 
                    "no results found"
                ]
                page_text = soup.get_text().lower()
                if any(marker in page_text for marker in no_results_markers):
                    log.info(f"[{self.config.name}] Page {page_number} -> No ads found")
                    return []

                # Comprehensive list of selectors for Ouedkniss listing links
                selectors = [
                    "a.o-announ-card-content", 
                    ".search-view-item a",
                    "div.o-announ-card-column > a",
                    "a.v-card",
                    "div.announcement-card a",
                    ".o-announ-card a"
                ]
                
                links = []
                for sel in selectors:
                    found = soup.select(sel)
                    if found:
                        links.extend(found)
                        log.debug(f"[{self.config.name}] Found {len(found)} links with selector '{sel}'")
                
                # FALLBACK: If no links found via selectors, try finding any link that looks like an ad
                if not links:
                    all_links = soup.find_all("a")
                    log.debug(f"[{self.config.name}] Extraction fallback: Checking all {len(all_links)} links")
                    for link in all_links:
                        href = link.get("href")
                        if href and re.search(r'-d\d+$', href):
                            links.append(link)
                
                html_count = 0
                for link in links:
                    href = link.get("href", "")
                    if href:
                        # Skip social or auth links
                        if any(x in href for x in ["/membre/", "/login", "/register", "facebook.com", "google.com"]):
                            continue
                        
                        full_url = ""
                        if href.startswith("/"):
                            # Filter for actual ad links (usually follow a pattern)
                            if not re.search(r'-d\d+$', href):
                                if "/immobilier-" in href: continue 
                            
                            full_url = f"https://www.ouedkniss.com{href}"
                        elif href.startswith("https://www.ouedkniss.com"):
                            full_url = href
                        
                        if full_url and full_url not in seen:
                            seen.add(full_url)
                            urls.append(full_url)
                            html_count += 1
                
                if not result or not result.success or not urls:
                    if result and ("challenge" in result.html.lower() or "cloudflare" in result.html.lower()):
                        log.warning(f"[{self.config.name}] Blocked by Cloudflare on page {page_number}")
                        if self.proxy_manager and proxy:
                            self.proxy_manager.report_failure(proxy)
                    
                    raise Exception("No listings extraction success or crawl failed")
                else:
                    log.debug(f"[{self.config.name}] Found {len(urls)} ads")
                
                log.info(f"[{self.config.name}] Page {page_number} SUCCESS → Found {len(urls)} ads")
                if self.proxy_manager and proxy:
                    self.proxy_manager.report_success(proxy)
                return urls

            except Exception as e:
                log.error(f"[{self.config.name}] Error scraping page {page_number}: {e}")
                
                # Diagnostic: Save HTML on any failure if we have it
                if 'result' in locals() and result and hasattr(result, 'html'):
                    diag_path = Path(__file__).parent / "logs" / f"failed_page_{page_number}_{int(time.time())}.html"
                    diag_path.parent.mkdir(exist_ok=True)
                    with open(diag_path, "w", encoding="utf-8") as f:
                        f.write(result.html)
                    log.info(f"[{self.config.name}] Failure diagnostic: HTML saved to {diag_path}")

                if self.proxy_manager:
                    if proxy:
                        self.proxy_manager.report_failure(proxy)
                    self.proxy_manager.rotate("ouedkniss.com")
                await asyncio.sleep(1)
        
        log.warning(f"[{self.config.name}] Failed to scrape page {page_number} after {max_retries} attempts")
        return []
    
    async def _detail_worker(self, worker_id: int):
        """Takes URLs from queue and scrapes them."""
        log.info(f"[{self.config.name}] Worker #{worker_id} started")
        
        while self._running or not self.url_queue.empty():
            try:
                url = await asyncio.wait_for(self.url_queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                if not self._running:
                    break
                continue
            
            if url is None:
                self.url_queue.task_done()
                break

            try:
                # Mark as seen before processing to avoid race conditions
                await self.deduplicator.mark_seen(url)
                
                # Scrape with zone info for priority handling
                await scrape_single_url(url, self.proxy_manager, zone=self.config.zone_type.value)
                await counter.increment(self.config.zone_type.value)
                self._urls_processed += 1
                
                log.debug(f"[{self.config.name}] Worker #{worker_id} completed {url}")
                
            except Exception as e:
                log.error(f"[{self.config.name}] Worker #{worker_id} failed {url} → {e}")
            finally:
                self.url_queue.task_done()
                await asyncio.sleep(self.config.throttle_delay)
        
        log.info(f"[{self.config.name}] Worker #{worker_id} shutting down")


# ========================= MULTI-ZONE ORCHESTRATOR =========================
class MultiZoneOrchestrator:
    """
    Orchestrates all scraping zones running concurrently.
    Manages scheduling, resource allocation, and graceful shutdown.
    """
    
    def __init__(self, proxy_manager: ProxyManager):
        self.proxy_manager = proxy_manager
        self.deduplicator = url_deduplicator
        self.zones: Dict[ZoneType, ZoneRunner] = {}
        self._running = False
    
    def add_zone(self, zone_type: ZoneType):
        """Add a zone to the orchestrator."""
        config = ZONE_CONFIGS[zone_type]
        self.zones[zone_type] = ZoneRunner(config, self.proxy_manager, self.deduplicator)
        log.info(f"Added zone: {config.name}")
    
    async def run_single_pass(self, zones: Optional[List[ZoneType]] = None):
        """Run a single pass of specified zones concurrently."""
        target_zones = zones or list(self.zones.keys())
        
        log.info(f"Starting single pass for zones: {[z.value for z in target_zones]}")
        
        # Run all specified zones concurrently
        tasks = [
            self.zones[zone_type].run_single_pass()
            for zone_type in target_zones
            if zone_type in self.zones
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Save deduplication cache
        await self.deduplicator.save_cache()
        
        # Print final stats
        stats = await self.deduplicator.get_stats()
        counts = await counter.get_counts()
        log.info(f"Single pass complete. Stats: {counts} | Dedup cache: {stats['total_seen']} URLs")
    
    async def run_continuous(self, zones: Optional[List[ZoneType]] = None):
        """
        Run zones continuously with their scheduled intervals.
        Each zone runs independently on its own schedule.
        """
        target_zones = zones or list(self.zones.keys())
        self._running = True
        
        log.info(f"Starting continuous mode for zones: {[z.value for z in target_zones]}")
        
        async def zone_scheduler(zone_type: ZoneType):
            """Run a single zone on its schedule."""
            zone = self.zones[zone_type]
            config = zone.config
            
            while self._running:
                try:
                    log.info(f"[{config.name}] Starting scheduled run...")
                    await zone.run_single_pass()
                    
                    log.info(f"[{config.name}] Pass complete. Next run in {config.interval_seconds}s")
                    
                    # Wait for next interval (check for shutdown every 10s)
                    remaining = config.interval_seconds
                    while remaining > 0 and self._running:
                        await asyncio.sleep(min(10, remaining))
                        remaining -= 10
                        
                except asyncio.CancelledError:
                    log.info(f"[{config.name}] Scheduler cancelled")
                    break
                except Exception as e:
                    log.error(f"[{config.name}] Scheduler error: {e}")
                    await asyncio.sleep(60)
        
        # Start all zone schedulers concurrently
        scheduler_tasks = [
            asyncio.create_task(zone_scheduler(zone_type))
            for zone_type in target_zones
            if zone_type in self.zones
        ]
        
        try:
            await asyncio.gather(*scheduler_tasks)
        except asyncio.CancelledError:
            log.info("Continuous mode cancelled")
        finally:
            self._running = False
            await self.deduplicator.save_cache()
    
    async def stop(self):
        """Stop all zones gracefully."""
        self._running = False
        for zone in self.zones.values():
            await zone.stop()
        await self.deduplicator.save_cache()


# ========================= LEGACY FUNCTIONS (preserved for backward compatibility) =========================
url_queue = asyncio.Queue(maxsize=1000)


async def listing_producer(proxy_manager):
    """Legacy producer - preserved for backward compatibility."""
    log.info("Using legacy listing_producer")
    zone_config = ZoneConfig(
        zone_type=ZoneType.REALTIME,
        start_page=1,
        end_page=None,
        interval_seconds=0,
        max_concurrent_details=MAX_CONCURRENT_DETAILS,
        priority=1,
        throttle_delay=DELAY_BETWEEN_BATCHES
    )
    zone_runner = ZoneRunner(zone_config, proxy_manager, url_deduplicator)
    
    page = 1
    while True:
        urls = await zone_runner._scrape_listing_page(page)
        
        if not urls:
            log.info("No more ads found → stopping producer")
            break
        
        for url in urls:
            await url_queue.put(url)
        
        page += 1
        await asyncio.sleep(DELAY_BETWEEN_BATCHES)
    
    for _ in range(MAX_CONCURRENT_DETAILS):
        await url_queue.put(None)
    print("Producer finished. All pages crawled.")


async def detail_worker(worker_id: int, proxy_manager, counter_obj):
    """Legacy detail worker - preserved for backward compatibility."""
    log.info(f"Detail Worker #{worker_id} started")
    while True:
        url = await url_queue.get()
        if url is None:
            log.info(f"Detail Worker #{worker_id} shutting down")
            url_queue.task_done()
            break

        log.debug(f"Worker #{worker_id} → {url}")
        try:
            await scrape_single_url(url, proxy_manager)
            await counter_obj.increment()
            log.info(f"Worker #{worker_id} saved {url}")
        except Exception as e:
            log.error(f"Worker #{worker_id} failed {url} → {e}")
        finally:
            url_queue.task_done()
            await asyncio.sleep(0.1)


# ========================= MAIN ENTRY POINTS =========================

async def main_legacy():
    """Original main function - preserved for backward compatibility."""
    print("OuedKniss Pipeline Scraper STARTED (Legacy Mode)")
    print("├── Batch size:", BATCH_SIZE)
    print("├── Concurrent listing pages:", MAX_CONCURRENT_LISTING)
    print("└── Concurrent detail scrapers:", MAX_CONCURRENT_DETAILS)

    print("Fetching proxies...")
    proxies = await fetch_proxies()
    print(f"Fetched {len(proxies)} proxies.")
    proxy_manager = ProxyManager(proxies)

    workers = [
        asyncio.create_task(detail_worker(i+1, proxy_manager, counter))
        for i in range(MAX_CONCURRENT_DETAILS)
    ]

    producer = asyncio.create_task(listing_producer(proxy_manager))

    await producer
    await url_queue.join()
    
    print("Queue empty → sending shutdown to workers...")

    for _ in range(MAX_CONCURRENT_DETAILS):
        await url_queue.put(None)

    await asyncio.gather(*workers)

    print("\nFULL SCRAPING COMPLETED!")
    print("Check scraped_ouedkniss.jsonl and your Elasticsearch index")


async def main_multizone():
    """New multi-zone main function."""
    print("=" * 70)
    print("OuedKniss HYBRID MULTI-PASS SCRAPER")
    print("=" * 70)
    
    zone_arg = args.zone.lower()
    continuous = args.continuous
    
    print("Fetching proxies...")
    proxies = await fetch_proxies()
    print(f"Fetched {len(proxies)} proxies.")
    proxy_manager = ProxyManager(proxies)
    
    orchestrator = MultiZoneOrchestrator(proxy_manager)
    
    if zone_arg == "all":
        for zone_type in ZoneType:
            orchestrator.add_zone(zone_type)
        target_zones = list(ZoneType)
    else:
        zone_type = ZoneType(zone_arg)
        orchestrator.add_zone(zone_type)
        target_zones = [zone_type]
    
    print(f"├── Zones: {[z.value for z in target_zones]}")
    print(f"├── Mode: {'Continuous' if continuous else 'Single Pass'}")
    print(f"└── Target URL: {TARGET_URL_BASE}")
    print("=" * 70)
    
    try:
        if continuous:
            await orchestrator.run_continuous(target_zones)
        else:
            await orchestrator.run_single_pass(target_zones)
    except KeyboardInterrupt:
        print("\nInterrupt received, shutting down...")
        await orchestrator.stop()
    finally:
        await url_deduplicator.save_cache()
        
        stats = await url_deduplicator.get_stats()
        counts = await counter.get_counts()
        print("\n" + "=" * 70)
        print("SCRAPING COMPLETED!")
        print(f"├── Total scraped: {counts['total']}")
        print(f"├── Realtime zone: {counts.get('realtime', 0)}")
        print(f"├── Warm zone: {counts.get('warm', 0)}")
        print(f"├── Cold zone: {counts.get('cold', 0)}")
        print(f"└── URLs in dedup cache: {stats['total_seen']}")
        print("=" * 70)


async def main():
    """Main entry point - routes to appropriate mode based on args."""
    if args.single_pass or args.zone != "all" or args.continuous:
        await main_multizone()
    else:
        # Default: use multi-zone single pass for all zones
        await main_multizone()

if __name__ == "__main__":
    asyncio.run(main())