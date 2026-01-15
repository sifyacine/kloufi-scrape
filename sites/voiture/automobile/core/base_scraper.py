import asyncio
import logging
from abc import ABC, abstractmethod
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from .config import Config

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    def __init__(self, base_url):
        self.base_url = base_url
        self.config = Config()
        self.browser_config = BrowserConfig(
            headless=self.config.HEADLESS,
            browser_type=self.config.BROWSER_TYPE,
            user_agent=self.config.USER_AGENT,
            text_mode=False,
            java_script_enabled=True
        )
        self.crawler = None

    async def start_session(self):
        """Starts the crawler session."""
        self.crawler = AsyncWebCrawler(config=self.browser_config)
        await self.crawler.start()

    async def close_session(self):
        """Closes the crawler session."""
        if self.crawler:
            await self.crawler.close()

    async def scrape_page(self, url, css_selector=None, js_code=None, wait_for=None):
        """
        Generic method to scrape a single page.
        
        Args:
            url (str): The URL to scrape.
            css_selector (str, optional): A CSS selector to wait for.
            js_code (str, optional): JavaScript code to execute on the page.
            wait_for (str, optional): CSS selector to wait for before returning.
            
        Returns:
            The result object from crawl4ai.
        """
        if not self.crawler:
            await self.start_session()

        run_config = CrawlerRunConfig(
            cache_mode=getattr(CacheMode, self.config.CACHE_MODE, CacheMode.BYPASS),
            delay_before_return_html=self.config.DELAY_BEFORE_RETURN_HTML / 1000, # Convert to seconds
            js_code=js_code,
            wait_for=wait_for or css_selector
        )

        try:
            result = await self.crawler.arun(
                url=url,
                config=run_config
            )
            return result
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return None

    @abstractmethod
    async def extract_data(self, html_content, url):
        """
        Abstract method to extract data from HTML content.
        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    async def run(self):
        """
        Main execution method for the scraper.
        Must be implemented by subclasses.
        """
        pass

    async def __aenter__(self):
        await self.start_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_session()
