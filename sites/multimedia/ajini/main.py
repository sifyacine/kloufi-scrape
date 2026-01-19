# main.py - Ajini TV listing scraper
import asyncio
import json
from datetime import datetime
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from scrape_details import scrape_product_details

# Configuration
BASE_URL = "https://www.ajini.com/product-category/tv-audio/"
CSS_SELECTOR = "[class^='xs-product-wraper text-center']"

async def scrape_listing_page():
    """Scrape TV listing page and extract product URLs"""
    print(f"Scraping listing page: {BASE_URL}")
    
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        text_mode=False
    )
    
    product_urls = []
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=BASE_URL,
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                delay_before_return_html=5
            )
        )
        
        if not result.success:
            print(f"Failed to scrape listing page: {result.error_message}")
            return product_urls
        
        soup = BeautifulSoup(result.html, 'html.parser')
        
        # Extract product links from listing
        products = soup.select(CSS_SELECTOR)
        print(f"Found {len(products)} products on listing page")
        
        for product in products:
            link = product.find('a', href=True)
            if link:
                product_url = link['href']
                if not product_url.startswith('http'):
                    product_url = f"https://www.ajini.com{product_url}"
                product_urls.append(product_url)
        
        print(f"Extracted {len(product_urls)} product URLs")
    
    return product_urls


async def main():
    """Main scraper orchestrator"""
    print("Starting Ajini TV scraper")
    
    # Get all product URLs from listing
    product_urls = await scrape_listing_page()
    
    if not product_urls:
        print("No product URLs found")
        return
    
    # Scrape each product detail page
    for url in product_urls:
        try:
            await scrape_product_details(url)
            await asyncio.sleep(2)  # Be polite
        except Exception as e:
            print(f"Error scraping {url}: {e}")
    
    print(f"Completed scraping {len(product_urls)} products")


if __name__ == "__main__":
    asyncio.run(main())
