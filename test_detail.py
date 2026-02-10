import asyncio
from playwright.async_api import async_playwright
from scraper.extractor.detail_extractor import DetailExtractor
import json

async def test_extraction():
    url = "https://www.ouedkniss.com/store/14789/sarl-afak-immo/annonce/44585141" # Example URL from previous crawl
    # Or use a known valid one if that one is old. Let's use one from our crawled list if possible.
    # We'll use a generic search result URL if we don't have a specific one handy, or just try to find one.
    # Actually, let's use a real one from the previous run output if available, or just a sample.
    
    # Let's try to get a URL from crawled_urls.json if it exists
    try:
        with open('crawled_urls.json', 'r', encoding='utf-8') as f:
            urls = json.load(f)
            if urls:
                url = urls[0]
                print(f"Testing with crawled URL: {url}")
    except:
        print("No crawled URLs found, using default test URL.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        
        extractor = DetailExtractor(context)
        data = await extractor.extract(url)
        
        print("\n--- Extracted Data ---")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_extraction())
