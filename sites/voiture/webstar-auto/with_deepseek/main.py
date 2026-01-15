import json
import os
from typing import List, Set, Tuple
from config import BASE_URL, CSS_SELECTOR, REQUIRED_KEYS
import asyncio
from pydantic import BaseModel

class Car(BaseModel):
    """
    Represents the data structure of a Car.
    """

    # titre: str
    prix: str
    # href: str
    # image: str


from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
    LLMExtractionStrategy,
)

def get_browser_config() -> BrowserConfig:
    """
    Returns the browser configuration for the crawler.

    Returns:
        BrowserConfig: The configuration settings for the browser.
    """
    return BrowserConfig(
        browser_type="chromium",  # Type of browser to simulate
        headless=False,  # Whether to run in headless mode (no GUI)
        verbose=True,  # Enable verbose logging
    )


def get_llm_strategy() -> LLMExtractionStrategy:
    """
    Returns the configuration for the language model extraction strategy.

    Returns:
        LLMExtractionStrategy: The settings for how to extract data using LLM.
    """
    return LLMExtractionStrategy(
        provider="groq/deepseek-r1-distill-llama-70b",
        api_token=os.getenv("GROQ_API_KEY"),
        schema=Car.model_json_schema(),
        extraction_type="schema",  # Type of extraction to perform
        instruction=(
            "Extract all cars with prix from the next content."
        ),  # Instructions for the LLM
        input_format="markdown",  # Format of the input content
        verbose=True,  # Enable verbose logging
    )

async def fetch_and_process_page(
    crawler: AsyncWebCrawler,
    base_url: str,
    css_selector: str,
    llm_strategy: LLMExtractionStrategy,
    session_id: str,
    required_keys: List[str],
    seen_names: Set[str],
) -> Tuple[List[dict], bool]:
    """
    Fetches and processes a single page of car data.
    """
    url = f"{base_url}"
    print(f"Loading the page...")

    # Fetch page content with the extraction strategy
    result = await crawler.arun(
        url=url,
        config=CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,  # Do not use cached data
            extraction_strategy=llm_strategy,  # Strategy for data extraction
            css_selector=css_selector,  # Target specific content on the page
            delay_before_return_html=5
        ),
    )

    if not (result.success and result.extracted_content):
        print(f"Error fetching the page: {result.error_message}")
        return [], False

    # Parse extracted content
    extracted_data = json.loads(result.extracted_content)
    if not extracted_data:
        print(f"No cars found on the page.")
        return [], False

    print("Extracted data:", extracted_data)

    # Process cars
    complete_cars = []
    for car in extracted_data:
        complete_cars.append(car)

    if not complete_cars:
        print(f"No complete cars found.")
        return [], False

    print(f"Extracted {len(complete_cars)} cars from the page.")
    return complete_cars, False  # Only one page, stop here

async def crawl_cars():
    """
    Main function to crawl car data from the website.
    """
    # Initialize configurations
    browser_config = get_browser_config()
    llm_strategy = get_llm_strategy()
    session_id = "car_crawl_session"

    # Initialize state variables
    all_cars = []
    seen_names = set()

    # Start the web crawler context
    async with AsyncWebCrawler(config=browser_config) as crawler:
        # Fetch and process data from the first (and only) page
        cars, no_results_found = await fetch_and_process_page(
            crawler,
            BASE_URL,
            CSS_SELECTOR,
            llm_strategy,
            session_id,
            REQUIRED_KEYS,
            seen_names,
        )

        if no_results_found:
            print("No more cars found. Ending crawl.")
        elif not cars:
            print(f"No cars extracted from the page.")
        else:
            all_cars.extend(cars)

        # Optionally, handle usage stats for LLM
        # llm_strategy.show_usage()

    print(f"Total cars extracted: {len(all_cars)}")
    # Optionally save the data or process it further.

async def main():
    """
    Entry point of the script.
    """
    await crawl_cars()


if __name__ == "__main__":
    asyncio.run(main())
