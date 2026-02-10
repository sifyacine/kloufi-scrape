# main_pipeline.py
"""
Hybrid Multi-Pass Scraping entry point for Ouedkniss immobilier.

This implements the three-zone architecture described in:
  - HOT / REALTIME zone  → very frequent, shallow crawl (first pages)
  - WARM zone           → full crawl at medium frequency
  - COLD zone           → full crawl at low frequency (backfill)

Key ideas:
  - All zones run concurrently, each with its own workers and schedule.
  - All zones share a global URL‑ID deduplication cache stored in
    `scraped_urls_cache.json` in this directory.
  - Detail pages are fetched through Proxyium (see `scrape_details.py`).

The goal is to keep this file very explicit and debuggable, with
plenty of prints and comments so developers can reason about the flow.
"""

import argparse
import asyncio
import json
import os
import re
import random
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

# Add the project root to sys.path
# This script is in sites/immobilier/ouedkniss/, so root is 3 levels up
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from playwright.async_api import async_playwright
try:
    from playwright_stealth import Stealth
except ImportError:
    Stealth = None

from scraper.utils.human_behavior import (
    human_delay, human_scroll, human_mouse_move, 
    simulate_reading, random_mistake, hover_random_elements, random_navigation
)
from scraper.proxy.proxy_sources import fetch_and_validate_proxies
from scraper.proxy.proxy_manager import ProxyManager
from scrape_details import scrape_single_url

# ========================= GLOBAL CONFIG =========================

# Base listing URL for immobilier category.
TARGET_URL_BASE = "https://www.ouedkniss.com/immobilier/"

# Where we persist the deduplication cache
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEDUP_CACHE_PATH = os.path.join(BASE_DIR, "scraped_urls_cache.json")

# How many listing pages to fetch in one batch per zone cycle.
LISTING_BATCH_SIZE = 5

@dataclass
class ZoneConfig:
    """Static configuration for a single scraping zone."""
    name: str                 # human readable name (e.g. "HOT")
    internal_name: str        # internal tag (e.g. "REALTIME")
    start_page: int           # first listing page to consider
    end_page: Optional[int]   # last page (None = "until empty")
    interval_seconds: int     # delay between runs in continuous mode
    detail_workers: int       # concurrent detail scrapers for this zone (unused in behavioral)
    listing_concurrency: int  # (unused in behavioral)
    max_retries: int          # max retries per detail URL
    retry_delay: float        # delay between retries (seconds)
    throttle_delay: float     # delay between detail requests

# Default zone configuration tuned for behavioral scraping.
ZONES: Dict[str, ZoneConfig] = {
    # 🔥 HOT / REALTIME zone: focus on the first page, very frequent.
    "hot": ZoneConfig(
        name="HOT",
        internal_name="REALTIME",
        start_page=1,
        end_page=1,
        interval_seconds=60,
        detail_workers=1,
        listing_concurrency=1,
        max_retries=2,
        retry_delay=1.0,
        throttle_delay=5.0,
    ),
    # 🌤 WARM zone: full crawl, moderate pace.
    "warm": ZoneConfig(
        name="WARM",
        internal_name="WARM",
        start_page=1,
        end_page=None,
        interval_seconds=7200,
        detail_workers=1,
        listing_concurrency=1,
        max_retries=3,
        retry_delay=3.0,
        throttle_delay=10.0,
    ),
    # ❄ COLD zone: full backfill, slow and patient.
    "cold": ZoneConfig(
        name="COLD",
        internal_name="COLD",
        start_page=1,
        end_page=None,
        interval_seconds=604800,
        detail_workers=1,
        listing_concurrency=1,
        max_retries=5,
        retry_delay=5.0,
        throttle_delay=20.0,
    ),
}

class BehavioralBrowsingSession:
    """Encapsulates a human-like browsing session for a specific zone run."""
    def __init__(self, zone: ZoneConfig, global_seen_ids: Set[str], proxy_manager: ProxyManager):
        self.zone = zone
        self.global_seen_ids = global_seen_ids
        self.proxy_manager = proxy_manager
        self.new_ads_scraped = 0
        self.max_ads_per_session = 15 if zone.name == "HOT" else 30

    async def run(self):
        print(f"\n  [{self.zone.name}] Starting Behavioral Browsing Session...")
        
        async with async_playwright() as p:
            browser_args = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            browser = await p.chromium.launch(headless=True, args=browser_args)
            
            # Select proxy
            proxy = self.proxy_manager.get_proxy("ouedkniss.com", rotate=True)
            
            context_options = {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "viewport": {"width": 1920, "height": 1080}
            }
            if proxy:
                context_options["proxy"] = {"server": proxy}
                print(f"  [{self.zone.name}] Using proxy: {proxy}")
            
            # Use stealth if available
            if Stealth:
                context = await Stealth().use_async(browser.new_context(**context_options))
            else:
                context = await browser.new_context(**context_options)
            
            page = await context.new_page()
            
            try:
                # 1. Direct Navigation
                target_url = TARGET_URL_BASE if self.zone.start_page == 1 else f"{TARGET_URL_BASE}{self.zone.start_page}"
                print(f"  [{self.zone.name}] Navigating directly to {target_url}...")
                
                await page.goto(f"{target_url}{'&' if '?' in target_url else '?'}lang=fr", wait_until='domcontentloaded')
                
                # Locale handling
                await page.evaluate("""() => {
                    localStorage.setItem('ok-auth-frame', JSON.stringify({ locale: 'fr' }));
                    document.cookie = 'ok-locale=fr; path=/; domain=.ouedkniss.com';
                }""")
                
                # Check for consent banner
                try:
                    await page.locator('button.fc-button.fc-cta-consent.fc-primary-button').click(timeout=5000)
                except: pass
                
                await simulate_reading(page, 3)
                
                ads_in_this_session = 0
                while ads_in_this_session < self.max_ads_per_session:
                    # Random behavior: Scroll and look around
                    await human_scroll(page, max_scrolls=random.randint(1, 4))
                    
                    # Occasionally hover over some cards
                    if random.random() < 0.6:
                        await hover_random_elements(page, 'a.o-announ-card-content')

                    # Extract visible cards
                    cards = await page.locator('a.o-announ-card-content').all()
                    if not cards:
                        if await page.locator('text=Aucune annonce trouvée').is_visible():
                            print(f"  [{self.zone.name}] No more ads found on this page.")
                            break
                        await human_scroll(page, 3)
                        continue

                    # Find an interesting NEW ad
                    eligible_cards = []
                    for card in cards:
                        href = await card.get_attribute('href')
                        if href:
                            listing_id = extract_listing_id_from_url(href)
                            if listing_id and listing_id not in self.global_seen_ids:
                                eligible_cards.append((card, href, listing_id))
                    
                    if not eligible_cards:
                        print(f"  [{self.zone.name}] All visible ads are already scraped. Navigating forward...")
                        if not await random_navigation(page):
                           await human_scroll(page, 5)
                           break
                        continue

                    # Pick an ad
                    target_card, target_href, target_id = random.choice(eligible_cards[:5])
                    
                    print(f"  [{self.zone.name}] [Human] Interesting ad found: {target_id}")
                    await target_card.scroll_into_view_if_needed()
                    await human_delay(1, 2)
                    await target_card.click()
                    
                    # Now on detail page
                    await simulate_reading(page, random.randint(4, 9))
                    
                    real_ad_url = f"https://www.ouedkniss.com{target_href}" if target_href.startswith('/') else target_href
                    
                    # Call the detail scraper
                    await scrape_single_url(
                        real_ad_url,
                        zone_name=self.zone.name,
                        page=page,
                        proxy_manager=self.proxy_manager # Pass it down
                    )
                    
                    self.global_seen_ids.add(target_id)
                    self.new_ads_scraped += 1
                    ads_in_this_session += 1
                    
                    # Go back
                    if random.random() < 0.9:
                        print(f"  [{self.zone.name}] [Human] Done reading. Going back...")
                        await page.go_back(wait_until='domcontentloaded')
                        await human_delay(2, 5)
                    else:
                        print(f"  [{self.zone.name}] [Human] Let's look at something else here...")
                        await random_navigation(page)

                    # Distraction break
                    if random.random() < 0.15:
                        await human_delay(15, 40)

            except Exception as e:
                print(f"  [{self.zone.name}] Session Error: {e}")
            finally:
                await browser.close()
                print(f"  [{self.zone.name}] Session closed. Scraped {self.new_ads_scraped} new ads.")

        return self.new_ads_scraped


# ========================= DEDUPLICATION =========================

def extract_listing_id_from_url(url: str) -> Optional[str]:
    """
    Extract the unique numeric listing ID from an Ouedkniss URL.

    Examples:
      https://www.ouedkniss.com/appartement-vente-f3-alger-algerie-d48254269
                                                        └──── 48254269
    """
    if not url:
        return None

    # First try the canonical "d12345678" pattern at the end of the URL.
    m = re.search(r"d(\d+)$", url)
    if m:
        return m.group(1)

    # Fallback: last run of digits at the end.
    m = re.search(r"(\d+)$", url)
    if m:
        return m.group(1)

    return None


def load_scraped_ids() -> Set[str]:
    """Load previously scraped listing IDs from disk into a set."""
    if not os.path.exists(DEDUP_CACHE_PATH):
        print(f"[DEDUPE] No existing cache found at {DEDUP_CACHE_PATH} → starting fresh.")
        return set()

    try:
        with open(DEDUP_CACHE_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        ids = {str(x) for x in raw}
        print(f"[DEDUPE] Loaded {len(ids)} IDs from cache.")
        return ids
    except Exception as e:
        print(f"[DEDUPE] Failed to load cache ({e}) → starting with empty set.")
        return set()


def save_scraped_ids(ids: Set[str]) -> None:
    """Persist the dedup cache to disk as a JSON array of IDs."""
    try:
        tmp_path = DEDUP_CACHE_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(sorted(ids), f, ensure_ascii=False)
        os.replace(tmp_path, DEDUP_CACHE_PATH)
        print(f"[DEDUPE] Saved {len(ids)} IDs to cache at {DEDUP_CACHE_PATH}.")
    except Exception as e:
        print(f"[DEDUPE] Failed to save cache: {e}")


# ========================= LISTING SCRAPING =========================

async def run_zone(
    zone_key: str,
    global_seen_ids: Set[str],
    proxy_manager: ProxyManager,
    continuous: bool,
) -> None:
    """
    Execute a single zone using a human-like behavioral session.
    """
    zone = ZONES[zone_key]
    run_index = 0

    while True:
        run_index += 1
        run_started_at = datetime.now()
        print(
            f"\n========== [{zone.name}] RUN #{run_index} STARTED "
            f"at {run_started_at.isoformat()} =========="
        )

        session = BehavioralBrowsingSession(zone, global_seen_ids, proxy_manager)
        new_ids = await session.run()

        run_ended_at = datetime.now()
        elapsed = (run_ended_at - run_started_at).total_seconds()
        print(
            f"========== [{zone.name}] RUN #{run_index} FINISHED "
            f"in {elapsed:.1f}s (new ads scraped: {new_ids}) =========="
        )

        # Persist dedup cache after each run
        save_scraped_ids(global_seen_ids)

        if not continuous:
            break

        sleep_for = max(zone.interval_seconds - elapsed, 0)
        print(f"[{zone.name}] Sleeping {sleep_for:.1f}s before next run...")
        await asyncio.sleep(sleep_for)


# ========================= CLI & ENTRYPOINT =========================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hybrid Multi-Pass Scraper for Ouedkniss immobilier (Proxyium-based)."
    )
    parser.add_argument(
        "--zone",
        type=str,
        default="all",
        help=(
            "Which zone(s) to run: 'hot', 'warm', 'cold', or 'all'. "
            "You can also use 'realtime' as an alias for 'hot'."
        ),
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run zones in continuous mode according to their internal schedules.",
    )
    return parser.parse_args()


def resolve_zone_keys(zone_arg: str) -> List[str]:
    """Normalize the --zone argument into a list of internal keys."""
    zone_arg = (zone_arg or "").lower().strip()
    if zone_arg in ("all", ""):
        return list(ZONES.keys())

    if zone_arg in ("realtime", "real-time"):
        zone_arg = "hot"

    if zone_arg not in ZONES:
        raise ValueError(
            f"Unknown zone '{zone_arg}'. Expected one of: hot, warm, cold, all."
        )

    return [zone_arg]


async def async_main(args: argparse.Namespace) -> None:
    print("OuedKniss Hybrid Multi-Pass Scraper STARTED")
    print(f"Base URL       : {TARGET_URL_BASE}")
    print(f"Execution mode : {'CONTINUOUS' if args.continuous else 'SINGLE-PASS'}")

    # Initialize Proxy Manager
    proxies = await fetch_and_validate_proxies()
    if not proxies:
        print("CRITICAL: No valid proxies found. Exiting.")
        return
    manager = ProxyManager(proxies)

    selected_zone_keys = resolve_zone_keys(args.zone)
    print("Zones selected :")
    for key in selected_zone_keys:
        z = ZONES[key]
        pages_desc = (
            f"{z.start_page}-{z.end_page}" if z.end_page is not None else f"{z.start_page}-∞"
        )
        print(
            f"  - {z.name} "
            f"(internal={z.internal_name}, pages={pages_desc}, "
            f"workers={z.detail_workers}, interval={z.interval_seconds}s)"
        )

    # Load dedup cache shared across all zones.
    global_seen_ids = load_scraped_ids()

    # Launch each selected zone as its own async task.
    zone_tasks = [
        asyncio.create_task(run_zone(zone_key, global_seen_ids, manager, args.continuous))
        for zone_key in selected_zone_keys
    ]

    try:
        await asyncio.gather(*zone_tasks)
    except asyncio.CancelledError:
        # Propagate cancellation so KeyboardInterrupt can bubble up correctly.
        raise
    finally:
        # Attempt one last save of dedup cache on shutdown.
        save_scraped_ids(global_seen_ids)
        print("OuedKniss Hybrid Multi-Pass Scraper STOPPED.")


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        # Graceful shutdown on Ctrl+C – async_main() already attempts to save cache.
        print("\n[MAIN] KeyboardInterrupt received. Shutting down gracefully...")


if __name__ == "__main__":
    main()
