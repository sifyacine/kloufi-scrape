import asyncio
import json
import re
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from scrape_details import scrape_single_url_with_crawl4ai_and_bs4
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import locale

all_results = []

def format_date(date_str):
    locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
    # Normalize apostrophes
    date_str_normalized = date_str.replace("'", "’").strip()

    # Handle special cases
    if date_str_normalized == "Aujourd’hui":
        return datetime.now().strftime('%Y-%m-%d')  # Today
    elif date_str_normalized == 'Hier':
        return (datetime.now() - timedelta(days=1)).strftime('%d-%m-%Y')
    else:
        if '.' in date_str_normalized and len(date_str_normalized.split('.')) == 3:
            return datetime.strptime(date_str_normalized, '%d.%m.%Y').strftime('%Y-%m-%d')
        
        if len(date_str_normalized.split()) == 2:  # day month format
            day, month = date_str_normalized.split(' ')
            year = datetime.now().year  # Default to current year
            date_str_normalized = f"{day} {month} {year}"
            return datetime.strptime(date_str_normalized, '%d %B %Y').strftime('%d-%m-%Y')
        elif len(date_str_normalized.split()) == 3:  # day month year format
            return datetime.strptime(date_str, '%d %B %Y').strftime('%d-%m-%Y')
        else:
            raise ValueError(f"Unknown date format: {date_str}")


async def get_total_pages():
    """Get the total number of pages from the first page."""
    url = "https://www.algeriejob.com/recherche-jobs-algerie?page=0"
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
                delay_before_return_html=10
            )
        )

        if result.success:
            print("Successfully scraped the first page!")

            soup = BeautifulSoup(result.html, 'html.parser')

            pagination_items = soup.find(
                'li', class_='pager-item breaker pagination-numbers')
            last_page_button = pagination_items.find_next_sibling('li')

            if last_page_button:
                last_page_number = last_page_button.get_text(strip=True)
                last_page_number = re.sub(r'\D', '', last_page_number)
                print(f"Total pages: {last_page_number}")
                return int(last_page_number)

        else:
            print("Error scraping the first page:", result.error_message)
            return 1


async def scrape_page(page_number):
    global all_results
    url = f"https://www.algeriejob.com/recherche-jobs-algerie?page={page_number}"

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
                delay_before_return_html=10
            )
        )

        if result.success:
            print(f"Successfully scraped page {page_number}!")

            soup = BeautifulSoup(result.html, 'html.parser')

            job_items = soup.find_all(
                "div", class_="card card-job")
            
            for job in job_items:
                relative_url = job.get('data-href')
                
                if relative_url:
                    url = f"{relative_url}"
                    poste_section = job.find('h3')
                    titre = poste_section.find('a').text
                    employeur = job.find('a', class_='card-job-company').text
                    date_depot = job.find('time').text
                    date_depot_text = ""
                    
                    if titre:
                        poste = titre.split(' - ')[0]
                    
                    if date_depot:
                        date_depot_text = format_date(date_depot)
                    
                    job = {
                        "titre": poste,
                        "poste": poste,
                        "employeur": employeur,
                        "date_depot": date_depot_text,
                    }
                    
                    await scrape_single_url_with_crawl4ai_and_bs4(url, job)
            
            print(f"Found {len(job_items)} job items on page {page_number}")

async def main():
    total_pages = await get_total_pages()

    for page_number in range(0, total_pages):
        await scrape_page(page_number)

if __name__ == "__main__":
    asyncio.run(main())
