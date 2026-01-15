import asyncio
import json
import re
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from scrape_details import scrape_single_url_with_crawl4ai_and_bs4
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import locale
import sys
sys.setrecursionlimit(10000)

# Global list if needed, but since we insert directly, maybe not necessary
all_results = []

def format_date(date_str):
    locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
    # Normalize apostrophes
    date_str_normalized = date_str.replace("'", "’").strip()

    # Handle special cases
    if date_str_normalized == "Aujourd’hui":
        return datetime.now().strftime('%Y-%m-%d')  # Today
    elif date_str_normalized == 'Hier':
        return (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    else:
        # Handle dates like "14 janvier" (without year)
        if len(date_str_normalized.split()) == 2:  # day month format
            day, month = date_str_normalized.split(' ')
            year = datetime.now().year  # Default to current year
            date_str_normalized = f"{day} {month} {year}"
            return datetime.strptime(date_str_normalized, '%d %B %Y').strftime('%Y-%m-%d')
        elif len(date_str_normalized.split()) == 3:  # day month year format
            return datetime.strptime(date_str, '%d %B %Y').strftime('%Y-%m-%d')
        else:
            raise ValueError(f"Unknown date format: {date_str}")


async def get_total_pages(max_retries=3):
    """Get the total number of pages from the first page with retries."""
    url = "https://emploitic.com/offres-d-emploi?page=1"
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

    for attempt in range(1, max_retries + 1):
        try:
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
                    # Find the last page number more robustly
                    pagination = soup.find('ul', class_='MuiPagination-ul')
                    if pagination:
                        last_li = pagination.find_all('li')[-1]
                        last_page_button = last_li.find('button')
                        if last_page_button:
                            last_page_number = last_page_button.get_text(strip=True)
                            last_page_number = re.sub(r'\D', '', last_page_number)
                            if last_page_number.isdigit():
                                print(f"Total pages: {last_page_number}")
                                return int(last_page_number)
                    print("Pagination not found, assuming 1 page.")
                    return 1
                else:
                    print(f"Error scraping first page (attempt {attempt}): {result.error_message}")
        except Exception as e:
            print(f"Exception getting total pages (attempt {attempt}): {e}")
        
        await asyncio.sleep(5 * attempt)  # Exponential backoff

    print("Failed to get total pages after retries. Defaulting to 1.")
    return 1


async def scrape_page(page_number, max_retries=3):
    url = f"https://emploitic.com/offres-d-emploi?page={page_number}"
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

    for attempt in range(1, max_retries + 1):
        try:
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
                    print(f"Successfully scraped page {page_number}!")
                    soup = BeautifulSoup(result.html, 'html.parser')
                    job_items = soup.find_all("li", class_=re.compile(r"mui-8v06ou"))

                    # Collect job details for parallel scraping
                    job_tasks = []
                    for job in job_items:
                        a_tag = job.find('a', href=True)
                        date_depot_section = job.find(attrs={"data-testid": "TimelapseRoundedIcon"})
                        employeur_section = job.find(attrs={"data-testid": "jobs-item-company"})
                        poste_section = job.find('h2', class_=re.compile(r"mui-1fyowno"))

                        date_depot_text = "N/A"
                        employeur_text = "N/A"
                        poste = "N/A"

                        if date_depot_section:
                            date_depot_parent = date_depot_section.find_parent('div')
                            date_depot_text = date_depot_parent.get_text(strip=True)
                            if date_depot_text:
                                try:
                                    date_depot_text = format_date(date_depot_text)
                                except ValueError as ve:
                                    print(f"Date format error on page {page_number}: {ve}")
                                    date_depot_text = "N/A"

                        if employeur_section:
                            employeur_text = employeur_section.get_text(strip=True)

                        if poste_section:
                            poste = poste_section.get_text(strip=True)

                        if a_tag:
                            relative_url = a_tag['href']
                            full_url = f"https://emploitic.com/{relative_url}"
                            print(f"Found job listing: {full_url}")
                            job_tasks.append(scrape_single_url_with_crawl4ai_and_bs4(full_url, date_depot_text, employeur_text, poste))

                    if job_tasks:
                        # Parallelize detail scraping with concurrency limit
                        semaphore = asyncio.Semaphore(5)  # Limit to 5 concurrent detail scrapes
                        async def sem_task(task):
                            async with semaphore:
                                return await task
                        await asyncio.gather(*[sem_task(t) for t in job_tasks], return_exceptions=True)

                    print(f"Processed {len(job_items)} job listings on page {page_number}")
                    return True  # Success

                else:
                    print(f"Error on page {page_number} (attempt {attempt}): {result.error_message}")
        except Exception as e:
            print(f"Exception scraping page {page_number} (attempt {attempt}): {e}")

        await asyncio.sleep(5 * attempt)  # Backoff

    print(f"Failed to scrape page {page_number} after {max_retries} attempts.")
    return False


async def main():
    total_pages = await get_total_pages()
    print(f"Starting scrape from page 1 to {total_pages} for completeness.")

    # Parallelize page scraping with limited concurrency
    page_tasks = []
    semaphore = asyncio.Semaphore(3)  # Limit to 3 concurrent list pages
    async def sem_scrape_page(page):
        async with semaphore:
            return await scrape_page(page)

    for page_number in range(1, total_pages + 1):
        page_tasks.append(sem_scrape_page(page_number))

    results = await asyncio.gather(*page_tasks, return_exceptions=True)
    
    failed_pages = [i+1 for i, r in enumerate(results) if isinstance(r, Exception) or r is False]
    if failed_pages:
        print(f"Failed pages: {failed_pages}. Consider re-running for these.")
    else:
        print("All pages scraped successfully.")

    print(f"Total items collected: {len(all_results)}")  # If using all_results
    # print(all_results)  # Optional

if __name__ == "__main__":
    asyncio.run(main())