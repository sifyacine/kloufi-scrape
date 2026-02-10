from playwright.async_api import async_playwright
import asyncio

async def crawl_with_playwright(url, proxy=None, headless=True):
    """
    Crawl a URL using Playwright with automatic scrolling to load all lazy-loaded content.
    
    Args:
        url: URL to crawl
        proxy: Proxy string (e.g., "http://proxy:port")
        headless: Run browser in headless mode
    
    Returns:
        tuple: (html_content, card_count)
    """
    async with async_playwright() as p:
        # Launch browser with options
        launch_options = {'headless': headless}
        if proxy:
            launch_options['proxy'] = {'server': proxy}
        
        browser = await p.chromium.launch(**launch_options)
        
        # Create new page with stealth settings
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        page = await context.new_page()
        
        try:
            print(f"  Loading {url}...")
            # Navigate to page (increased timeout for slow proxies)
            await page.goto(url, wait_until='domcontentloaded', timeout=90000)
            
            # Initial wait for Vue.js to initialize
            await asyncio.sleep(5)
            print(f"  Page loaded, starting scroll...")
            
            # Scroll to load ALL lazy-loaded content
            last_count = 0
            stable_checks = 0
            scroll_attempt = 0
            max_scrolls = 40  # Increased to ensure we get all content
            
            while scroll_attempt < max_scrolls and stable_checks < 3:
                # Scroll down by viewport height
                await page.evaluate('window.scrollBy(0, window.innerHeight)')
                
                # Wait for lazy loading to trigger
                await asyncio.sleep(2)
                
                # Count announcement cards
                count = await page.locator('.o-announ-card-column').count()
                
                if count == last_count:
                    stable_checks += 1
                    print(f"  Scroll {scroll_attempt + 1}: {count} cards (stable {stable_checks}/3)")
                else:
                    stable_checks = 0
                    print(f"  Scroll {scroll_attempt + 1}: {last_count} → {count} cards")
                
                last_count = count
                scroll_attempt += 1
            
            print(f"  [OK] Scrolling complete: {last_count} announcement cards loaded")
            
            # DEBUG: If 0 cards, capture info to see why
            if last_count == 0:
                print(f"  [WARN] Found 0 cards. Capturing debug info...")
                timestamp = int(asyncio.get_event_loop().time())
                try:
                    # await page.screenshot(path=f"debug_zero_cards_{timestamp}.png")
                    content = await page.content()
                    with open(f"debug_zero_cards_{timestamp}.html", "w", encoding="utf-8") as f:
                        f.write(content)
                    
                    title = await page.title()
                    print(f"  [DEBUG_LOG] Page Title: {title}")
                    print(f"  [DEBUG_LOG] HTML Length: {len(content)}")
                    
                    if "Just a moment" in title or "Cloudflare" in content:
                        print(f"  [DEBUG_LOG] BLOCK DETECTED: Cloudflare Challenge")
                except Exception as e:
                    print(f"  [ERROR] Failed to save debug info: {e}")

            # Get final HTML
            html = await page.content()
            
            await browser.close()
            return html, last_count
            
        except Exception as e:
            print(f"  [ERROR] Crawl failed for {url}. Capturing debug info...")
            try:
                timestamp = asyncio.get_event_loop().time()
                # await page.screenshot(path=f"debug_crawl_fail_{int(timestamp)}.png")
                content = await page.content()
                with open(f"debug_crawl_fail_{int(timestamp)}.html", "w", encoding="utf-8") as f:
                    f.write(content)
                
                # VPS LOGGING
                try:
                    title = await page.title()
                    print(f"  [DEBUG_LOG] Page Title: {title}")
                except:
                    print(f"  [DEBUG_LOG] Could not get page title.")
                
                print(f"  [DEBUG_LOG] HTML Length: {len(content)}")
                if "Just a moment" in title or "Cloudflare" in content:
                    print(f"  [DEBUG_LOG] BLOCK DETECTED: Cloudflare Challenge")
                elif "403 Forbidden" in content:
                     print(f"  [DEBUG_LOG] BLOCK DETECTED: 403 Forbidden")
                
            except Exception as inner_e:
                print(f"  [ERROR] Could not capture debug info: {inner_e}")
            
            await browser.close()
            raise Exception(f"Playwright crawl failed: {e}")
