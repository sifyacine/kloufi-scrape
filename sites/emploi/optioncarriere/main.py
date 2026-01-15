import asyncio
import json
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from bs4 import BeautifulSoup
from scrape_details import extract_job_details

# Global list to collect {url, location} dicts
job_entries = []

async def scrape_listing_pages():
    page = 1
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        text_mode=False
    )
    
    while True:
        listing_url = f"https://www.optioncarriere.dz/emploi?s=&l=Alg%C3%A9rie&p={page}"
        print(f"Loading listing page: {listing_url}")
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(
                url=listing_url,
                config=CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    delay_before_return_html=5
                )
            )
        
        if not result.success:
            print(f"Error loading page {page}: {result.error_message}")
            break

        soup = BeautifulSoup(result.html, "html.parser")
        
        # Find all job articles on this page
        job_articles = soup.find_all("article", class_="job")
        if not job_articles:
            print(f"No job listings found on page {page}. Stopping pagination.")
            break
        
        for article in job_articles:
            # Extract the job detail URL from the data-url attribute
            if 'data-url' in article.attrs:
                relative_url = article['data-url']
                detail_url = f"https://www.optioncarriere.dz{relative_url}"
                
                # Extract job title
                title_tag = article.find("h2")
                job_title = title_tag.find("a").get_text(strip=True) if title_tag and title_tag.find("a") else None
                
                # Extract company name
                company_tag = article.find("p", class_="company")
                company = company_tag.find("a").get_text(strip=True) if company_tag and company_tag.find("a") else None
                
                # Extract location
                location_tag = article.find("ul", class_="location")
                location = location_tag.find("li").get_text(strip=True) if location_tag and location_tag.find("li") else None
                
                # Extract description snippet
                desc_tag = article.find("div", class_="desc")
                description_snippet = desc_tag.get_text(strip=True) if desc_tag else None
                
                # Extract posted date
                footer = article.find("footer")
                posted_date = None
                if footer:
                    badge = footer.find("span", class_="badge")
                    posted_date = badge.get_text(strip=True) if badge else None
                
                # Store the entry with additional metadata
                entry = {
                    "url": detail_url,
                    "title": job_title,
                    "company": company,
                    "location": location,
                    "posted_date": posted_date,
                    "description_snippet": description_snippet
                }
                
                # Dedupe
                if not any(existing_entry["url"] == detail_url for existing_entry in job_entries):
                    job_entries.append(entry)

        print(f"Page {page}: found {len(job_articles)} jobs, total entries so far: {len(job_entries)}")
        page += 1
        if page == 25: break

async def main():
    await scrape_listing_pages()
    print(f"Total job entries found: {len(job_entries)}")
    
    jobs = []
    for entry in job_entries:
        url = entry["url"]
        try:
            # Pass the entry data to extract_job_details to enhance with scraped data
            details = await extract_job_details(url, entry)
            jobs.append(details)
        except Exception as e:
            print(f"Error extracting details for {url}: {e}")
            continue

    # Save the collected jobs into a JSON file
    out_path = r"emploi\optioncarriere\data\optioncarriere_jobs.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=4)
    print(f"Jobs data saved to {out_path}")

if __name__ == "__main__":
    asyncio.run(main())