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
from scraper.utils.human_behavior import (
    human_delay, human_scroll, human_mouse_move, 
    simulate_reading, random_mistake, hover_random_elements, random_navigation
)

# Auto-install stealth if missing
try:
    from playwright_stealth import Stealth
except ImportError:
    print("WARNING: playwright-stealth not installed. Attempting auto-install...")
    import subprocess
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright-stealth"])
        from playwright_stealth import Stealth
        print("Successfully installed playwright-stealth.")
    except Exception as e:
        print(f"CRITICAL ERROR: Could not install playwright-stealth: {e}")
        print("Please run: pip install playwright-stealth")
        sys.exit(1)

# Configuration
BASE_URL = "https://www.ouedkniss.com/immobilier"
CONCURRENCY = 1 
MAX_TARGET_ADS = 15 # Goal for the session

class BrowsingSession:
    def __init__(self, manager: ProxyManager):
        self.manager = manager
        self.announcements = []
        self.visited_urls = set()
        self.target_ads_reached = 0

    async def run(self):
        print(f"\n{'='*60}")
        print(f"STARTING BEHAVIORAL BROWSING SESSION")
        print(f"{'='*60}")

        # Check for existing progress
        if os.path.exists('announcements.json'):
            try:
                with open('announcements.json', 'r', encoding='utf-8') as f:
                    self.announcements = json.load(f)
                    self.visited_urls = {item['url'] for item in self.announcements if 'url' in item}
                    print(f"Loaded {len(self.announcements)} existing ads.")
            except: pass

        async with Stealth().use_async(async_playwright()) as p:
            browser_args = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            browser = await p.chromium.launch(headless=True, args=browser_args)
            
            # Select proxy
            proxy = self.manager.get_proxy("ouedkniss.com", rotate=True)
            context_options = {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "viewport": {"width": 1920, "height": 1080}
            }
            if proxy:
                context_options["proxy"] = {"server": proxy}
            
            context = await browser.new_context(**context_options)
            page = await context.new_page()
            
            try:
                # 1. Start at the category page
                print(f"  [Session] Navigating to category: {BASE_URL}")
                await page.goto(BASE_URL, wait_until='domcontentloaded')
                await simulate_reading(page, 3)
                
                while self.target_ads_reached < MAX_TARGET_ADS:
                    # Random behavior: Scroll and look around
                    await human_scroll(page, max_scrolls=random.randint(2, 5))
                    
                    # Occasionally hover over some cards
                    if random.random() < 0.7:
                        print("  [Human] Checking out some interesting titles...")
                        await hover_random_elements(page, 'a.o-announ-card-content')

                    # Extract all currently visible cards
                    cards = await page.locator('a.o-announ-card-content').all()
                    if not cards:
                        print("  [WARN] No cards found. Scrolling more...")
                        await human_scroll(page, 3)
                        continue

                    # Pick a card to click
                    # Prefer one we haven't visited
                    eligible_cards = []
                    for card in cards:
                        href = await card.get_attribute('href')
                        if href:
                            full_url = f"https://www.ouedkniss.com{href}" if href.startswith('/') else href
                            if full_url not in self.visited_urls:
                                eligible_cards.append((card, full_url))
                    
                    if not eligible_cards:
                        print("  [Human] Nothing interesting here. Moving to next page or navigating...")
                        if not await random_navigation(page):
                            # Fallback: just scroll more
                            await human_scroll(page, 5)
                        continue

                    # Select an ad to "click"
                    target_card, target_url = random.choice(eligible_cards[:5]) # Pick from top ones
                    
                    print(f"  [Human] This looks interesting: {target_url}")
                    await target_card.scroll_into_view_if_needed()
                    await human_delay(1, 2)
                    await target_card.click()
                    
                    # Now on detail page
                    await simulate_reading(page, 5)
                    
                    # Extract Data
                    extractor = DetailExtractor(page)
                    data = await extractor.extract(target_url)
                    if data:
                        self.announcements.append(data)
                        self.visited_urls.add(target_url)
                        self.target_ads_reached += 1
                        print(f"  [SUCCESS] Scraped ad {self.target_ads_reached}/{MAX_TARGET_ADS}")
                        
                        # Save progress
                        with open('announcements.json', 'w', encoding='utf-8') as f:
                            json.dump(self.announcements, f, indent=4, ensure_ascii=False)
                    
                    # After reading, DECIDE: go back or click something else?
                    if random.random() < 0.8:
                        print("  [Human] Going back to the search results...")
                        await page.go_back(wait_until='domcontentloaded')
                        await human_delay(2, 4)
                    else:
                        print("  [Human] Oh, let's see where this internal link goes...")
                        await random_navigation(page)

                    # Occasionally take a "long break" as if distracted
                    if random.random() < 0.1:
                        distracted_time = random.randint(20, 60)
                        print(f"  [Human] Distracted for {distracted_time} seconds (getting coffee?)...")
                        await asyncio.sleep(distracted_time)

            except Exception as e:
                print(f"  [CRITICAL] Session failed: {e}")
            finally:
                await browser.close()
                print(f"\nSession Complete. Total Ads Scraped: {self.target_ads_reached}")

async def main():
    # Initialize Proxy Manager
    proxies = await fetch_and_validate_proxies()
    if not proxies:
        print("CRITICAL: No valid proxies found. Exiting.")
        return
        
    manager = ProxyManager(proxies)
    
    session = BrowsingSession(manager)
    await session.run()

if __name__ == "__main__":
    asyncio.run(main())
