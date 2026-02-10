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
            # Navigate to page
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
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
            
            # Get final HTML
            html = await page.content()
            
            await browser.close()
            return html, last_count
            
        except Exception as e:
            await browser.close()
            raise Exception(f"Playwright crawl failed: {e}")
