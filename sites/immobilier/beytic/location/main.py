import asyncio
import json
import re
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from scrape_details import extract_property_details
from bs4 import BeautifulSoup
import sys
sys.setrecursionlimit(10000)

location_results = []
vente_results = []

async def get_total_pages(transaction):
    """Get the total number of pages from the first page."""
    url = f"https://www.beytic.com/annonces-immobilieres?_page=0&productSpecificities.choice_2={transaction}"
    js_commands = [
        "await new Promise(resolve => setTimeout(resolve, 5000));",
        "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",
        "await new Promise(resolve => setTimeout(resolve, 3000));"
    ]

    browser_config = BrowserConfig(
        headless=True,
        text_mode=False,
        browser_type="chromium",
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=url,
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                js_code=js_commands,
                delay_before_return_html=5
            )
        )

        if result.success:
            print("Successfully scraped the first page!")

            soup = BeautifulSoup(result.html, 'html.parser')

            pagination_dots = soup.find(
                'div', class_='raz-pagination-dots')
            last_page_button = pagination_dots.find_next("div", class_="raz-pagination-page")

            if last_page_button:
                last_page_number = last_page_button.get_text(strip=True)
                last_page_number = re.sub(r'\D', '', last_page_number)
                return int(last_page_number)

        else:
            print("Error scraping the first page:", result.error_message)
            return 1


async def scrape_page(page_number, transaction):
    url = f"https://www.beytic.com/annonces-immobilieres?_page={page_number}&productSpecificities.choice_2={transaction}"

    # JavaScript commands to accept cookies (if needed)
    js_commands = [
        # Wait 5 seconds for banner
        "await new Promise(resolve => setTimeout(resolve, 5000));",
        "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",
        "await new Promise(resolve => setTimeout(resolve, 3000));"
    ]

    # Define the browser configuration
    browser_config = BrowserConfig(
        headless=True,
        text_mode=False,
        browser_type="chromium",
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        # Scrape the page for name, location, and URL
        result = await crawler.arun(
            url=url,
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                js_code=js_commands,
                delay_before_return_html=3
            )
        )

        if result.success:
            soup = BeautifulSoup(result.html, 'html.parser')
            
            # Get all cards
            cards = soup.find_all('div', class_='raz-listing-item raz-listing-product elementor-column elementor-col-33 elementor-top-column elementor-element elementor-element-7090851 medialem-listing-item')
            for card in cards:
                url = card.find('a', class_='raz-page-details-link')
                if url:
                    relative_url = url['href']
                    completed_url = f"https://www.beytic.com{relative_url}"
                    bien = card.find('a', class_='raz-element02 elementor-button').get_text(strip=True)
                    await extract_property_details(completed_url, transaction, bien)
            print(f"Successfully scraped page {page_number}!")

async def main():
    location_total_pages = await get_total_pages("Location")
    
    print("Location total pages:", location_total_pages)
        
    for page_number in range(1, location_total_pages):
        print(f"Scraping page {page_number}...")
        await scrape_page(page_number, "Location")

if __name__ == "__main__":
    asyncio.run(main())
