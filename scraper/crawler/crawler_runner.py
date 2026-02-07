from crawl4ai import AsyncWebCrawler
from scraper.detection.captcha_detector import has_captcha

async def crawl(url, proxy, context, config=None, headless=True):
    async with AsyncWebCrawler(
        proxy=proxy,
        browser_context=context,
        headless=headless
    ) as crawler:
        # Enable 'magic' mode for advanced anti-bot evasion
        # This handles navigator.webdriver, stealth args, and more
        result = await crawler.arun(url=url, config=config, magic=True)
        html = result.html
        if await has_captcha(html):
            raise Exception("CAPTCHA detected")
        return result  # Return full result to access .success, etc if needed, or html

