import asyncio
import json
from datetime import datetime
from crawl4ai import AsyncWebCrawler
from dotenv import load_dotenv
from config import BASE_URL, CSS_SELECTOR, REQUIRED_KEYS
from utils.data_utils import save_tvs_to_csv, save_tvs_to_json, format_tv_data
from utils.scraper_utils import fetch_and_process_page, get_browser_config, get_llm_strategy, crawl_tv_product_page
import sys
sys.path.insert(1, '../../global')
from insert_scrape import insert_data_to_es

load_dotenv()

async def crawl_tvs():
    """Main function to crawl TVs from the website and save results."""
    browser_config = get_browser_config()
    llm_strategy = get_llm_strategy()
    session_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    all_tvs = []
    seen_names = set()  # Still needed for tracking within the same crawl

    async with AsyncWebCrawler(config=browser_config) as crawler:
        tvs = await fetch_and_process_page(
            crawler,
            BASE_URL,
            CSS_SELECTOR,
            llm_strategy,
            session_id,

        )
        
        all_tvs.extend(tvs)

    if all_tvs:
        for tv in all_tvs:
            tv_data = format_tv_data(tv)
            images = await crawl_tv_product_page(tv_data["url"])
            tv_data["images"] = images
            tv_data["as_photo"] = "Avec photo" if len(images) > 0 else "Sans photo"
            insert_data_to_es(tv_data, "multimedia")
    else:
        print("⚠️ No TVs found.")

    llm_strategy.show_usage()

async def main():
    await crawl_tvs()

if __name__ == "__main__":
    asyncio.run(main())
