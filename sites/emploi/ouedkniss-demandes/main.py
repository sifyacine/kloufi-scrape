import asyncio
import json
import re
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from scrape_details import scrape_single_url
from bs4 import BeautifulSoup
import sys
sys.setrecursionlimit(10000)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/73.0.3683.103 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.94 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:60.0) Gecko/20100101 Firefox/60.0",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/68.0.3440.106 Safari/537.36"
]

PROXY_URL = "https://proxyium.com/"
TARGET_URL = "https://www.ouedkniss.com/emploi_demandes/"

# Global list to store all results
all_results = []

async def get_browser_config():
    """Setup browser configuration."""
    return BrowserConfig(
        headless=True,
        text_mode=False,
        browser_type="chromium",
    )

async def get_total_pages(max_retries=3):
    """Get the total number of pages by scraping the first page."""
    js_commands = [
        "await new Promise(resolve => setTimeout(resolve, 5000));",  # Wait for page to load
        "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",  # Accept cookies
        "await new Promise(resolve => setTimeout(resolve, 3000));",  # Wait for cookies consent
        f"document.getElementById('unique-form-control').value = '{TARGET_URL}1';",
        "document.querySelector('#web_proxy_form').submit();",
        "await new Promise(resolve => setTimeout(resolve, 5000));"  # Wait for the page to navigate
    ]

    for attempt in range(1, max_retries + 1):
        async with AsyncWebCrawler(config=await get_browser_config()) as crawler:
            result = await crawler.arun(
                url=PROXY_URL,
                config=CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    js_code=js_commands,
                    delay_before_return_html=15
                )
            )

            if result.success:
                print(f"Successfully scraped the first page on attempt {attempt}!")
                soup = BeautifulSoup(result.html, 'html.parser')
                pagination_items = soup.find_all('li', class_='v-pagination__item')

                if pagination_items:
                    # Find last page number based on pagination
                    last_page_button = pagination_items[-1].find('button')
                    if last_page_button:
                        last_page_number = last_page_button.find('span', class_='v-btn__content').get_text(strip=True)
                        return int(re.sub(r'\D', '', last_page_number)) or 1
                    else:
                        print("Failed to find the last page number.")
                else:
                    print("No pagination items found.")
            else:
                print(f"Error scraping the first page: {result.error_message}")

        if attempt < max_retries:
            print(f"Retrying to get the total pages (attempt {attempt + 1})...")
            await asyncio.sleep(5)  # wait a bit before retrying

    print(f"❌ Failed to get total pages after {max_retries} attempts.")
    return 5000

async def scrape_page(page_number, max_retries=3, retry_delay=10):
    """Scrape a single page with retries if data is missing."""
    for attempt in range(1, max_retries + 1):
        print(f"Scraping page {page_number}, attempt {attempt}...")

        js_commands = [
            "await new Promise(resolve => setTimeout(resolve, 5000));",  # Wait for page to load
            "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",  # Accept cookies
            "await new Promise(resolve => setTimeout(resolve, 3000));",  # Wait for cookies consent
            f"document.getElementById('unique-form-control').value = '{TARGET_URL}{page_number}';",
            "document.querySelector('#web_proxy_form').submit();",
            "await new Promise(resolve => setTimeout(resolve, 5000));"  # Wait for the page to navigate
        ]

        async with AsyncWebCrawler(config=await get_browser_config()) as crawler:
            result = await crawler.arun(
                url=PROXY_URL,
                config=CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    js_code=js_commands,
                    delay_before_return_html=30
                )
            )

            if result.success:
                print(f"Successfully scraped page {page_number} on attempt {attempt}!")
                data_found = await process_page(result.html, page_number)

                if data_found:  # ✅ Success! Stop retrying
                    return
                else:
                    print(f"No 'itemListElement' found on page {page_number}. Retrying...")

            else:
                print(f"Error scraping page {page_number}: {result.error_message}")

        if attempt < max_retries:
            print(f"Retrying page {page_number} in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)

    print(f"❌ Failed to scrape page {page_number} after {max_retries} attempts.")

async def process_page(html, page_number):
    """Process and parse the page content. Returns True if data is found, else False."""
    pattern = re.compile(r'"itemListElement":(\[.*?\])', re.DOTALL)
    matches = pattern.findall(html)

    if matches:
        print(f"Found {len(matches)} 'itemListElement' occurrences on page {page_number}!")
        if len(matches) >= 2:
            second_json_str = matches[1]
            try:
                data = json.loads(second_json_str)
                print(f"✅ Found {len(data)} items on page {page_number}.")
                all_results.extend(data)

                # Collect URLs to scrape individual details
                urls = [item.get('url') for item in data if item.get('url')]
                for url in urls:
                    await scrape_single_url(url)

                return True  # ✅ Data found
            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse JSON on page {page_number}: {e}")
        else:
            print(f"⚠️ Second occurrence of 'itemListElement' not found on page {page_number}.")
    else:
        print(f"❌ No 'itemListElement' occurrences found on page {page_number}.")

    return False  # ❌ No data found

async def main():
    """Main function to run the scraping process."""
    total_pages = await get_total_pages()

    print(f"Total pages to scrape: {total_pages}")
    
    for page_number in range(1, total_pages + 1):
        await scrape_page(page_number)

    print(f"✅ Total items collected: {len(all_results)}")
    print(all_results)

if __name__ == "__main__":
    asyncio.run(main())
