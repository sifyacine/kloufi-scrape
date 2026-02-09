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
import base64
from urllib.parse import urlparse, parse_qs, unquote
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
parser.add_argument("--no-proxy", action="store_true", default=False,
                    help="Disable proxy usage and run directly (useful for VPS debugging)")
parser.add_argument("--show-browser", action="store_true", default=False,
                    help="Run browser in headful mode (visible UI) for debugging")
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
log.info(f"Targeting Base URL: {TARGET_URL_BASE}")

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


import base64

def get_proxyium_url(url: str) -> str:
    """Encodes a URL for Proxyium's gateway (Direct URL fallback)."""
    encoded = base64.b64encode(url.encode()).decode()
    return f"https://proxyium.com/browse.php?u={encoded}&b=4"

def unproxify_url(url: str) -> str:
    """Decodes a Proxyium-encoded URL back to its original Ouedkniss form."""
    if "proxyium.com" not in url:
        return url
    
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    
    if 'u' in qs:
        try:
            encoded_val = qs['u'][0]
            # Handle base64 padding issues if any
            padding = len(encoded_val) % 4
            if padding:
                encoded_val += "=" * (4 - padding)
            decoded = base64.b64decode(encoded_val.encode()).decode()
            return decoded
        except Exception:
            return url
    return url

# ========================= ZONE RUNNER CLASS =========================
class ZoneRunner:
    """
    Manages scraping for a specific zone with its own queue and workers.
    Each zone operates independently with its own concurrency settings.
    """
    
    def __init__(self, config: ZoneConfig, proxy_manager=None, deduplicator=None):
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
        """Scrape a single listing page via Proxyium Interaction."""
        target_url = f"{TARGET_URL_BASE}{page_number}" if page_number > 1 else TARGET_URL_BASE
        
        # We start at Proxyium homepage
        proxy_gateway = "https://proxyium.com/"
        
        log.info(f"[{self.config.name}] PROXYIUM INTERACTION: {target_url} via {proxy_gateway}")

        js_commands = [
            """
            (async () => {
                const wait = ms => new Promise(r => setTimeout(r, ms));
                
                console.log('Bypassing Proxyium Consent...');
                document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();
                await wait(1000);

                console.log('Typing URL...');
                const input = document.getElementById('unique-form-control');
                if (input) {
                    input.value = '""" + target_url + ("&" if "?" in target_url else "?") + """locale=fr';
                }

                console.log('Submitting Proxyium Form...');
                const form = document.querySelector('#web_proxy_form');
                if (form) {
                    form.submit();
                }
                
                // Wait for redirect and for the proxied page to become readable
                await wait(10000);
                
                // Force French inside the proxied page
                localStorage.setItem('ok-auth-frame', JSON.stringify({ locale: 'fr' }));
                document.cookie = "ok-locale=fr; domain=.ouedkniss.com; path=/; max-age=31536000";

                // Stepped Scroll to trigger all lazy loads
                for (let i = 0; i < 15; i++) {
                    window.scrollBy(0, 800);
                    await wait(300);
                }
                window.scrollTo(0, document.body.scrollHeight);
                await wait(2000);
            })();
            """
        ]

        config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            page_timeout=120000,
            wait_until="domcontentloaded",
            js_code=js_commands,
            delay_before_return_html=30
        )

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            context = build_context()

            try:
                log.info(f"[{self.config.name}] Page {page_number} (Attempt {attempt}) - Using PROXYIUM Gateway")
                # Navigate to Proxyium homepage first
                result = await crawl(proxy_gateway, None, context, config=config, headless=True)
                
                if not result.success:
                    log.warning(f"[{self.config.name}] Failed Page {page_number} (Status: {result.status_code})")
                    raise Exception(f"Crawl failed status {result.status_code}")

                log.info(f"[{self.config.name}] Page {page_number} Crawl SUCCESS. HTML Length: {len(result.html)}")
                
                urls = []
                seen = set()

                # --- JSON-LD DEBUGGING ---
                matches = re.findall(r'"itemListElement":(\[.*?\])', result.html, re.DOTALL)
                log.debug(f"[{self.config.name}] found {len(matches)} JSON-LD matches")
                
                if len(matches) >= 1:
                    try:
                        json_str = matches[-1] 
                        data = json.loads(json_str)
                        log.debug(f"[{self.config.name}] JSON-LD Data Items count: {len(data)}")
                        for item in data:
                            url = item.get("url")
                            if url and url not in seen and url.startswith("http"):
                                seen.add(url)
                                urls.append(url)
                        log.info(f"[{self.config.name}] Extracted {len(urls)} URLs via JSON-LD")
                    except Exception as e:
                        log.error(f"[{self.config.name}] JSON-LD parsing error: {e}")
                        pass
                else:
                    log.warning(f"[{self.config.name}] No JSON-LD 'itemListElement' found in HTML")

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
                for marker in no_results_markers:
                    if marker in page_text:
                        log.info(f"[{self.config.name}] Page {page_number} -> Marker found: '{marker}' -> stopping")
                        return []


                # Comprehensive list of selectors for Ouedkniss listing links
                selectors = [
                    "a.o-announ-card-content", 
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
                    else:
                        log.debug(f"[{self.config.name}] No links found with selector '{sel}'")
                
                html_count = 0
                for link in links:
                    href = link.get("href")
                    if href:
                        # Un-proxify if URL was rewritten by Proxyium
                        href = unproxify_url(href)

                        # Skip social or auth links
                        if any(x in href for x in ["/membre/", "/login", "/register", "facebook.com", "google.com"]):
                            continue
                        
                        full_url = ""
                        if href.startswith("/"):
                            # Filter for actual ad links (usually follow a pattern)
                            if not re.search(r'/[^/]+-d\d+$', href):
                                if "/immobilier-" in href: continue 
                            
                            full_url = f"https://www.ouedkniss.com{href}"
                        elif "ouedkniss.com" in href:
                            full_url = href
                        else:
                            continue

                        if full_url and full_url not in seen:
                            seen.add(full_url)
                            urls.append(full_url)
                            html_count += 1
                
                # Check if extraction succeeded
                if html_count == 0 and len(urls) == 0:
                    log.error(f"[{self.config.name}] ZERO LISTINGS CRITICAL FAILURE on Page {page_number}")
                    
                    # No listings extracted at all - this is a failure
                    # Note: We check specifically for Cloudflare or Challenge in the body content
                    content_lower = result.html.lower()
                    if ("challenge" in content_lower or "cloudflare" in content_lower):
                        log.warning(f"[{self.config.name}] Blocked by Cloudflare on page {page_number}")
                        if self.proxy_manager and proxy:
                            self.proxy_manager.report_failure(proxy)
                    
                    # Log the page title for clearer debugging
                    try:
                        soup_fail = BeautifulSoup(result.html, 'html.parser')
                        page_title = soup_fail.title.string.strip() if soup_fail.title else "No Title"
                        # If the title is still Proxyium, the terms weren't bypassed
                        if "Proxyium" in page_title:
                            log.error(f"[{self.config.name}] STUCK ON PROXYIUM LANDING PAGE.")
                        
                        log.error(f"[{self.config.name}] FAILED PAGE TITLE: '{page_title}' (Size: {len(result.html)} bytes)")
                    except Exception:
                        pass

                    # Diagnostic: Save HTML on extraction failure
                    diag_path = Path(__file__).parent / "logs" / f"failed_page_{page_number}_{int(time.time())}.html"
                    diag_path.parent.mkdir(exist_ok=True)
                    with open(diag_path, "w", encoding="utf-8") as f:
                        f.write(result.html)
                    log.error(f"[{self.config.name}] HTML saved to {diag_path} for inspection")
                    
                    raise Exception(f"Zero listings. Page Title: {page_title}")
                
                if html_count > 0:
                    log.debug(f"[{self.config.name}] Extracted {html_count} UNIQUE URLs via HTML Parsing")
                
                log.info(f"[{self.config.name}] Page {page_number} COMPLETE SUCCESS → Found {len(urls)} ads total")
                return urls

            except Exception as e:
                log.error(f"[{self.config.name}] Error scraping page {page_number}: {e}", exc_info=True)
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
    
    def __init__(self, proxy_manager=None):
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


async def verify_proxy_subsystem(proxy_manager):
    """Verifies that the proxy subsystem is working by fetching IP from httpbin."""
    log.info("Verifying proxy subsystem...")
    check_url = "https://httpbin.org/ip"
    try:
        if args.no_proxy:
            log.info("Skipping proxy verification (running with --no-proxy)")
            return

        # Try up to 3 times to verify
        for i in range(3):
            proxy = proxy_manager.get_proxy("httpbin.org")
            context = build_context()
            log.info(f"Testing proxy connection via {proxy} (Attempt {i+1})...")
            
            try:
                result = await crawl(check_url, proxy, context, headless=not args.show_browser)
                
                if result.success:
                    # Parse JSON to confirm masking
                    raw = result.html
                    origin_ip = "Unknown"
                    try:
                        if "<html" in raw or "<pre>" in raw:
                            soup = BeautifulSoup(raw, "html.parser")
                            text = soup.get_text(strip=True)
                            s = text.find('{')
                            e = text.rfind('}') + 1
                            if s != -1:
                                data = json.loads(text[s:e])
                                origin_ip = data.get("origin", "Unknown")
                        else:
                            data = json.loads(raw)
                            origin_ip = data.get("origin", "Unknown")
                    except Exception as e:
                         log.debug(f"JSON parse error during verify: {e}")

                    log.info(f"✅ PROXY VERIFICATION SUCCESS. External IP seen: {origin_ip}")
                    return True
                else:
                    log.warning(f"⚠️ Proxy verification request failed (Status {result.status_code})")
                    proxy_manager.report_failure(proxy)
                    proxy_manager.rotate("httpbin.org")
            except Exception as e:
                 log.warning(f"⚠️ Proxy verification attempt failed: {e}")
                 proxy_manager.rotate("httpbin.org")
        
        log.error("❌ All proxy verification attempts failed. Scraper might be blocked or proxies unhealthy.")
        return False
        
    except Exception as e:
        log.error(f"❌ Proxy verification exception: {e}")
        return False


async def main_multizone():
    """New multi-zone main function."""
    print("=" * 70)
    print("OuedKniss HYBRID MULTI-PASS SCRAPER")
    print("=" * 70)
    
    zone_arg = args.zone.lower()
    continuous = args.continuous
    
    orchestrator = MultiZoneOrchestrator(None)
    
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