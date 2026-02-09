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
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

from scrape_details import scrape_single_url

# ========================= GLOBAL CONFIG =========================

PROXY_URL = "https://proxyium.com/"

# Base listing URL for immobilier category. You can later extend this
# to include transaction / property filters (vente, location, etc.).
TARGET_URL_BASE = "https://www.ouedkniss.com/immobilier/"

# Where we persist the deduplication cache of already-scraped listing IDs.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEDUP_CACHE_PATH = os.path.join(BASE_DIR, "scraped_urls_cache.json")

# How many listing pages to fetch in one batch per zone cycle.
LISTING_BATCH_SIZE = 10


@dataclass
class ZoneConfig:
    """Static configuration for a single scraping zone."""

    name: str                 # human readable name (e.g. "HOT")
    internal_name: str        # internal tag (e.g. "REALTIME")
    start_page: int           # first listing page to consider
    end_page: Optional[int]   # last page (None = "until empty")
    interval_seconds: int     # delay between runs in continuous mode
    detail_workers: int       # concurrent detail scrapers for this zone
    listing_concurrency: int  # concurrent listing pages per batch
    max_retries: int          # max retries per detail URL
    retry_delay: float        # delay between retries (seconds)
    throttle_delay: float     # delay between detail requests


# Default zone configuration tuned according to the documentation.
ZONES: Dict[str, ZoneConfig] = {
    # 🔥 HOT / REALTIME zone: focus on the very first pages, very frequent.
    "hot": ZoneConfig(
        name="HOT",
        internal_name="REALTIME",
        start_page=1,
        # NOTE: We use pages 1–5 for HOT to aggressively cover fresh content.
        # You can change this to 1 only if you want ultra-lightweight mode.
        end_page=5,
        interval_seconds=600,   # every 10 minutes in continuous mode
        detail_workers=5,
        listing_concurrency=2,
        max_retries=2,
        retry_delay=1.0,
        throttle_delay=0.05,
    ),
    # 🌤 WARM zone: full crawl, moderate pace.
    "warm": ZoneConfig(
        name="WARM",
        internal_name="WARM",
        start_page=1,
        end_page=None,          # full crawl
        interval_seconds=7200,  # every 2 hours
        detail_workers=10,
        listing_concurrency=3,
        max_retries=3,
        retry_delay=3.0,
        throttle_delay=0.2,
    ),
    # ❄ COLD zone: full backfill, slow and patient.
    "cold": ZoneConfig(
        name="COLD",
        internal_name="COLD",
        start_page=1,
        end_page=None,           # full crawl
        interval_seconds=604800, # once per week
        detail_workers=5,
        listing_concurrency=2,
        max_retries=5,
        retry_delay=5.0,
        throttle_delay=0.5,
    ),
}


# Global browser config shared by all listing scrapers.
browser_config = BrowserConfig(
    headless=True,
    text_mode=False,
    browser_type="chromium",
    java_script_enabled=True,
)


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

async def scrape_listing_page(page_number: int) -> List[str]:
    """
    Scrape a single listing page via Proxyium and extract detail URLs.

    Returns a list of absolute detail URLs or an empty list on failure.
    """
    target_url = f"{TARGET_URL_BASE}{page_number}" if page_number > 1 else f"{TARGET_URL_BASE}"

    js_commands = [
        # Give Proxyium time to fully load.
        "await new Promise(resolve => setTimeout(resolve, 10000));",
        "localStorage.setItem('ok-auth-frame', JSON.stringify({ locale: 'fr' }));",
        "document.cookie = 'ok-locale=fr; path=/; domain=.ouedkniss.com';",
        "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",
        # Inject the real Ouedkniss URL into Proxyium form.
        f"document.getElementById('unique-form-control').value = '{target_url}{'&' if '?' in target_url else '?'}lang=fr';",
        "document.querySelector('#web_proxy_form').submit();",
        # Allow proxied page to render.
        "await new Promise(resolve => setTimeout(resolve, 5000));",
        "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",
    ]

    config = CrawlerRunConfig(
        js_code=js_commands,
        delay_before_return_html=30,
        page_timeout=120_000,
        wait_until="domcontentloaded",
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=PROXY_URL, config=config)

    if not result or not result.success:
        print(f"[LISTING] Page {page_number}: crawl failed via Proxyium.")
        return []

    # Extract the JSON-LD block that contains "itemListElement".
    matches = re.findall(r'"itemListElement":(\[.*?\])', result.html, re.DOTALL)
    if len(matches) < 2:
        print(f"[LISTING] Page {page_number}: no JSON-LD itemListElement found.")
        return []

    try:
        data = json.loads(matches[1])
    except Exception as e:
        print(f"[LISTING] Page {page_number}: failed to parse JSON-LD → {e}")
        return []

    urls: List[str] = []
    seen: Set[str] = set()
    for item in data:
        url = item.get("url")
        if url and url.startswith("http") and url not in seen:
            seen.add(url)
            urls.append(url)

    print(f"[LISTING] Page {page_number}: extracted {len(urls)} raw URLs.")
    return urls


async def listing_producer_for_zone(
    zone: ZoneConfig,
    url_queue: asyncio.Queue,
    global_seen_ids: Set[str],
) -> int:
    """
    Producer for a specific zone.

    - Iterates over listing pages according to zone's page range.
    - Fetches pages in small batches with limited concurrency.
    - Applies global deduplication before enqueuing URLs.

    Returns the number of NEW unique listing IDs that were queued.
    """
    pages_processed = 0
    new_ids_count = 0

    current_page = zone.start_page
    batch_index = 0

    while True:
        # Stop if we reached the configured end_page (for HOT zone).
        if zone.end_page is not None and current_page > zone.end_page:
            break

        batch_pages: List[int] = []
        for _ in range(LISTING_BATCH_SIZE):
            if zone.end_page is not None and current_page > zone.end_page:
                break
            batch_pages.append(current_page)
            current_page += 1

        if not batch_pages:
            break

        batch_index += 1
        print(
            f"[{zone.name}] Listing batch #{batch_index} → pages "
            f"{batch_pages[0]} to {batch_pages[-1]}"
        )

        sem = asyncio.Semaphore(zone.listing_concurrency)

        async def _run_single(page_no: int) -> Tuple[int, List[str]]:
            async with sem:
                urls = await scrape_listing_page(page_no)
                return page_no, urls

        tasks = [asyncio.create_task(_run_single(p)) for p in batch_pages]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        batch_new_ids = 0
        empty_pages_in_batch = 0

        for res in results:
            if isinstance(res, Exception):
                print(f"[{zone.name}] Error while scraping listing page: {res}")
                continue

            page_no, urls = res
            pages_processed += 1

            if not urls:
                empty_pages_in_batch += 1
                continue

            for url in urls:
                listing_id = extract_listing_id_from_url(url)
                if not listing_id:
                    # If we cannot extract an ID, we still process it but we log it.
                    print(f"[{zone.name}] WARNING: Could not extract ID from URL → {url}")
                    await url_queue.put(url)
                    continue

                if listing_id in global_seen_ids:
                    # Already processed in any zone / previous run.
                    continue

                global_seen_ids.add(listing_id)
                batch_new_ids += 1
                new_ids_count += 1
                await url_queue.put(url)

        print(
            f"[{zone.name}] Batch #{batch_index}: "
            f"{batch_new_ids} NEW IDs queued "
            f"(dedup size: {len(global_seen_ids)}, queue size: {url_queue.qsize()})"
        )

        # Heuristic: if every page in this batch returned zero URLs,
        # we assume we reached the end of available listings.
        if empty_pages_in_batch == len(batch_pages):
            print(f"[{zone.name}] Reached empty pages → stopping listing producer.")
            break

    print(
        f"[{zone.name}] Listing producer finished. "
        f"Pages processed: {pages_processed}, new IDs: {new_ids_count}"
    )
    return new_ids_count


# ========================= DETAIL WORKERS =========================

async def detail_worker_for_zone(
    zone: ZoneConfig,
    worker_id: int,
    url_queue: asyncio.Queue,
):
    """
    Worker that pulls URLs from a queue and delegates to `scrape_single_url`.
    """
    print(f"[{zone.name}] Detail Worker #{worker_id} started.")

    while True:
        url = await url_queue.get()
        if url is None:
            # Shutdown signal for this worker.
            print(f"[{zone.name}] Detail Worker #{worker_id} shutting down.")
            url_queue.task_done()
            break

        print(f"[{zone.name}] Worker #{worker_id} → {url}")

        try:
            # Zone-specific retry strategy is passed down to the detail scraper.
            await scrape_single_url(
                url,
                max_retries=zone.max_retries,
                retry_delay=zone.retry_delay,
                zone_name=zone.name,
            )
            print(f"[{zone.name}] Worker #{worker_id} successfully scraped.")
        except Exception as e:
            print(f"[{zone.name}] Worker #{worker_id} FAILED {url} → {e}")
        finally:
            url_queue.task_done()
            # Throttle between detail pages to avoid hammering Proxyium / Ouedkniss.
            await asyncio.sleep(zone.throttle_delay)


# ========================= ZONE RUNNER =========================

async def run_zone(
    zone_key: str,
    global_seen_ids: Set[str],
    continuous: bool,
) -> None:
    """
    Execute a single zone either once (single-pass) or forever (continuous).
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

        url_queue: asyncio.Queue = asyncio.Queue(maxsize=2000)

        # Start detail workers for this zone.
        workers = [
            asyncio.create_task(detail_worker_for_zone(zone, i + 1, url_queue))
            for i in range(zone.detail_workers)
        ]

        # Produce listing URLs for this zone.
        new_ids = await listing_producer_for_zone(zone, url_queue, global_seen_ids)

        # Wait until all queued URLs are processed.
        await url_queue.join()

        # Send shutdown signal to each worker.
        for _ in range(zone.detail_workers):
            await url_queue.put(None)

        await asyncio.gather(*workers)

        run_ended_at = datetime.now()
        elapsed = (run_ended_at - run_started_at).total_seconds()
        print(
            f"========== [{zone.name}] RUN #{run_index} FINISHED "
            f"in {elapsed:.1f}s (new IDs: {new_ids}) =========="
        )

        # Persist dedup cache after each run for safety.
        save_scraped_ids(global_seen_ids)

        if not continuous:
            # Single-pass mode → exit after one run.
            break

        # Continuous mode → sleep until next scheduled run.
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
    print(f"Proxy gateway  : {PROXY_URL}")
    print(f"Execution mode : {'CONTINUOUS' if args.continuous else 'SINGLE-PASS'}")

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
        asyncio.create_task(run_zone(zone_key, global_seen_ids, args.continuous))
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
