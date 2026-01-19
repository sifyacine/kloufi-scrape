# main.py - Unified Informatics scraper (Desktop PCs & Laptops)
import asyncio
import json
from datetime import datetime
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from scrape_details import scrape_product_details

# Configuration - can handle both categories
CATEGORIES = {
    "desktop_pc": "https://www.informatics.dz/pc-de-bureau/",
    "laptops": "https://www.informatics.dz/pc-portable/"
}

async def scrape_category_listing(category_name, category_url):
    """Scrape product listing page for a category"""
    print(f"Scraping {category_name} listing: {category_url}")
    
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        text_mode=False
    )
    
    product_urls = []
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=category_url,
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                delay_before_return_html=5
            )
        )
        
        if not result.success:
            print(f"Failed to scrape {category_name} listing: {result.error_message}")
            return product_urls
        
        soup = BeautifulSoup(result.html, 'html.parser')
        
        # Extract product links
        products = soup.select('div.product-item a.product-link') or \
                   soup.select('div.product a.woocommerce-LoopProduct-link') or \
                   soup.select('a.product-item-link')
        
        print(f"Found {len(products)} products in {category_name}")
        
        for product in products:
            product_url = product.get('href')
            if product_url and product_url.startswith('http'):
                product_urls.append((category_name, product_url))
        
        print(f"Extracted {len(product_urls)} product URLs from {category_name}")
    
    return product_urls


async def main():
    """Main scraper orchestrator"""
    print("Starting Informatics unified scraper (Desktop PCs + Laptops)")
    
    all_products = []
    
    # Scrape all categories
    for category_name, category_url in CATEGORIES.items():
        products = await scrape_category_listing(category_name, category_url)
        all_products.extend(products)
    
    if not all_products:
        print("No products found")
        return
    
    print(f"Total products to scrape: {len(all_products)}")
    
    # Scrape each product detail page
    for category_name, url in all_products:
        try:
            await scrape_product_details(url, category_name)
            await asyncio.sleep(2)  # Be polite
        except Exception as e:
            print(f"Error scraping {url}: {e}")
    
    print(f"Completed scraping {len(all_products)} products")


if __name__ == "__main__":
    asyncio.run(main())
