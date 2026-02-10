from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from scraper.detection.captcha_detector import has_captcha

async def crawl(url, proxy, context, config=None, headless=True):
    async with AsyncWebCrawler(
        proxy=proxy,
        browser_context=context,
        headless=headless
    ) as crawler:
        # Use simple delay - this worked reliably before
        if config is None:
            config = CrawlerRunConfig(
                delay_before_return_html=15.0  # 15 seconds for content to load
            )
        
        result = await crawler.arun(
            url=url, 
            config=config, 
            magic=True,
            timeout=120000
        )
        
        html = result.html
        if await has_captcha(html):
            raise Exception("CAPTCHA detected")
        return result

