import asyncio
import json
import os
import re
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from bs4 import BeautifulSoup
from scrape_details import extract_product_details
from urllib.parse import urljoin
import uuid

# Global lists to collect URLs
category_urls_list = []
product_urls_list = []
seller_urls_dict = {}  # Dictionary to store product URL -> list of seller URLs

async def scrape_category_pages():
    """
    Scrapes the category page to collect category URLs and saves them to a JSON file.
    """
    base_url = "https://webstar-electro.com/gammes/?gamme=electroniques-algerie&position=1&id_gamme=3746"
    browser_config = BrowserConfig(
        headless=True,
        browser_type="firefox",
        text_mode=False,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    
    print(f"▶ Loading category page: {base_url}")
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=base_url,
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                delay_before_return_html=40,
                magic=True,
                simulate_user=True,
                override_navigator=True,
            )
        )
    
    if not result.success:
        print(f"✖ Error loading category page: {result.error_message}")
        return []
    
    soup = BeautifulSoup(result.html, "html.parser")
    
    # Select category links
    links = soup.select("div.produit_logo_small > a, div.card-body > h3.produit_titre > a")
    
    for a in links:
        href = a.get("href")
        if not href:
            continue
        full_url = urljoin("https://webstar-electro.com", href)
        if full_url not in category_urls_list:
            category_urls_list.append(full_url)
    
    print(f"✔ Found {len(category_urls_list)} category URLs.")
    
    # Save category URLs to JSON
    output_dir = r"multimedia\webstar-electro\data"
    os.makedirs(output_dir, exist_ok=True)
    category_output_path = os.path.join(output_dir, "categories.json")
    with open(category_output_path, "w", encoding="utf-8") as f:
        json.dump(category_urls_list, f, ensure_ascii=False, indent=4)
    print(f"✅ Saved {len(category_urls_list)} category URLs to {category_output_path}")
    
    return category_urls_list

async def scrape_listing_pages(category_urls):
    """
    Scrapes product listing pages to collect product URLs and saves them to a JSON file.
    """
    browser_config = BrowserConfig(
        headless=True,
        browser_type="firefox",
        text_mode=False,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    
    for url in category_urls:
        print(f"▶ Loading listing page: {url}")
        
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(
                url=url,
                config=CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    delay_before_return_html=40,
                    magic=True,
                    simulate_user=True,
                    override_navigator=True,
                )
            )
        
        if not result.success:
            print(f"✖ Error loading page {url}: {result.error_message}")
            continue
        
        soup = BeautifulSoup(result.html, "html.parser")
        
        # Select product links
        links = soup.select("div.produit_logo_small > a[href*='produit='], div.card-body > h3.produit_titre > a[href*='produit=']")
        
        if not links:
            print(f"ℹ No product links found on page {url}, skipping.")
            continue
        
        new_links = []
        for a in links:
            href = a.get("href")
            if not href:
                continue
            full_url = urljoin("https://webstar-electro.com", href)
            if full_url not in product_urls_list:
                product_urls_list.append(full_url)
                new_links.append(full_url)
        
        print(f"✔ Found {len(new_links)} product links on page {url}.")
        
        # Save product URLs to JSON
        output_dir = r"multimedia\webstar-electro\data"
        product_output_path = os.path.join(output_dir, "products.json")
        with open(product_output_path, "w", encoding="utf-8") as f:
            json.dump(product_urls_list, f, ensure_ascii=False, indent=4)
        print(f"✅ Saved {len(product_urls_list)} product URLs to {product_output_path}")
        
        await asyncio.sleep(2)

async def scrape_seller_urls(product_urls):
    """
    Scrapes each product page to collect seller offer URLs and saves them to a master JSON file.
    """
    browser_config = BrowserConfig(
        headless=True,
        browser_type="firefox",
        text_mode=False,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )
    
    output_dir = r"multimedia\webstar-electro\data"
    os.makedirs(output_dir, exist_ok=True)
    
    for url in product_urls:
        print(f"▶ Loading product page for seller URLs: {url}")
        
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(
                url=url,
                config=CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    delay_before_return_html=40,
                    magic=True,
                    simulate_user=True,
                    override_navigator=True,
                )
            )
        
        if not result.success:
            print(f"✖ Error loading product page {url}: {result.error_message}")
            continue
        
        soup = BeautifulSoup(result.html, "html.parser")
        
        # Select seller offer links
        seller_links = soup.select("div.card.box_offre a[href*='store='][href*='id_annonce=']")
        
        seller_urls = []
        for a in seller_links:
            href = a.get("href")
            if not href:
                continue
            full_url = urljoin("https://webstar-electro.com", href)
            if full_url not in seller_urls:
                seller_urls.append(full_url)
        
        seller_urls_dict[url] = seller_urls
        print(f"✔ Found {len(seller_urls)} seller URLs for product {url}.")
        
        await asyncio.sleep(1)
    
    # Save all seller URLs to a master JSON file
    master_output_path = os.path.join(output_dir, "seller_urls.json")
    with open(master_output_path, "w", encoding="utf-8") as f:
        json.dump(seller_urls_dict, f, ensure_ascii=False, indent=4)
    print(f"✅ Saved seller URLs for {len(seller_urls_dict)} products to {master_output_path}")

async def main():
    """
    Main function to orchestrate the scraping process and generate structured product data.
    """
    print("Starting category page scraping...")
    category_urls = await scrape_category_pages()
    print(f"\nTotal category URLs found: {len(category_urls)}\n")
    
    if not category_urls:
        print("⚠ No category URLs found, exiting.")
        return
    
    print("Starting listing page scraping...")
    await scrape_listing_pages(category_urls)
    print(f"\nTotal product URLs found: {len(product_urls_list)}\n")
    
    if not product_urls_list:
        print("⚠ No product URLs found, exiting.")
        return
    
    print("Starting seller URLs scraping...")
    await scrape_seller_urls(product_urls_list)
    print(f"\nTotal products with seller URLs: {len(seller_urls_dict)}\n")
    
    # Collect product details with store links
    products = []
    for product_url, seller_urls in seller_urls_dict.items():
        store_links = []
        for seller_url in seller_urls:
            print(f"Extracting details from: {seller_url}")
            try:
                details = await extract_product_details(seller_url)
                if details:
                    # Ensure required fields are present, provide defaults if missing
                    store_link = {
                        "store_name": details.get("store_name", "Unknown Store"),
                        "location": details.get("location", "Unknown Location"),
                        "price": details.get("price", "N/A"),
                        "condition": details.get("condition", "N/A"),
                        "phone": details.get("phone", "N/A"),
                        "delivery": details.get("delivery", "N/A"),
                        "payment": details.get("payment", "N/A"),
                        "date": details.get("date", "2025-06-04"),
                        "url": seller_url
                    }
                    store_links.append(store_link)
                else:
                    print(f"⚠ No details extracted for {seller_url}")
            except Exception as e:
                print(f"⚠ Error extracting details for {seller_url}: {e}")
                continue
            await asyncio.sleep(1)
        
        if store_links:
            products.append({
                "original_url": product_url,
                "store_links": store_links
            })
    
    # Save structured product data
    output_dir = r"multimedia\webstar-electro\data"
    output_path = os.path.join(output_dir, "products_with_stores.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"products": products}, f, ensure_ascii=False, indent=4)
    print(f"✅ Saved {len(products)} products with store links to {output_path}")

if __name__ == "__main__":
    asyncio.run(main())