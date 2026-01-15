import asyncio
from datetime import datetime
from crawl4ai import AsyncWebCrawler
from dotenv import load_dotenv
from config import BASE_URL
from utils.data_utils import save_jobs_to_json
from utils.scraper_utils import fetch_and_process_jobs, get_browser_config, get_llm_strategy

load_dotenv()

async def crawl_jobs():
    """Main function to crawl job listings from the website and save results."""
    browser_config = get_browser_config()
    llm_strategy = get_llm_strategy()
    session_id = f"job_crawl_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    all_jobs = []

    async with AsyncWebCrawler(config=browser_config) as crawler:
        # Fetch job cards from the listing page and process each one
        jobs = await fetch_and_process_jobs(
            crawler,
            BASE_URL,
            llm_strategy,
            session_id,

        )
        all_jobs.extend(jobs)

    if all_jobs:
        save_jobs_to_json(all_jobs, r"emploi\globaljob\data\complete_jobs.json")
    else:
        print("⚠️ No job listings found.")

    llm_strategy.show_usage()

async def main():
    await crawl_jobs()

if __name__ == "__main__":
    asyncio.run(main())
