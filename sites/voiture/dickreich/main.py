import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from scrape_details import extract_car_details

MAX_CONCURRENT = 5   # do NOT exceed (Chrome/Firefox dies)
LISTING_PAGES = 20   # or detect automatically


async def fetch_listing_page(crawler, page_num):
    url = f"https://dickreich.com/fahrzeugbestand/?location=&post_id=6908&set_last_search=1&wpcsp={page_num}&orderby=price&order=desc&make=&fuel=PETROL%2CELECTRICITY%2CHYBRID&category=&model=&gearbox=&first_registration_min=%23&mileage_max=%23&price_max=%23#wpcs_vehicles"
    
    run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, delay_before_return_html=10)
    result = await crawler.arun(url=url, config=run_config)

    if not result.success:
        print(f"❌ Listing page {page_num} failed: {result.error_message}")
        return []

    soup = BeautifulSoup(result.html, "html.parser")
    vehicles = soup.find_all("article", class_="vehicle-on-archive")

    urls = []
    for v in vehicles:
        div = v.find("div", class_="dxim_grid_image")
        if not div: continue
        a = div.find("a")
        if not a or not a.get("href"): continue
        car_url = urljoin("https://dickreich.com", a["href"])
        urls.append(car_url)

    print(f"📄 Page {page_num}: Found {len(urls)} vehicles")
    return urls


async def scrape_all_listings():
    browser_config = BrowserConfig(headless=True, browser_type="firefox", text_mode=False)

    async with AsyncWebCrawler(config=browser_config) as crawler:
        tasks = [
            fetch_listing_page(crawler, page)
            for page in range(1, LISTING_PAGES + 1)
        ]
        results = await asyncio.gather(*tasks)

    # Flatten list
    all_urls = {url for sublist in results for url in sublist}
    print(f"🔎 TOTAL URLs collected: {len(all_urls)}")
    return list(all_urls)


async def scrape_all_details(urls):
    # limit concurrency
    sem = asyncio.Semaphore(MAX_CONCURRENT)

    async def bounded_extract(url):
        async with sem:
            return await extract_car_details(url)

    tasks = [bounded_extract(url) for url in urls]
    results = await asyncio.gather(*tasks)

    # Filter out None (filtered or failed)
    return [r for r in results if r]


async def main():
    urls = await scrape_all_listings()
    cars = await scrape_all_details(urls)

    print(f"🚗 TOTAL CARS SCRAPED: {len(cars)}")


if __name__ == "__main__":
    asyncio.run(main())
