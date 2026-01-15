import asyncio
import re
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from scrape_details import scrape_single_url_with_crawl4ai_and_bs4
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import sys

sys.setrecursionlimit(10000)

# ====================== DATE PARSING ======================

def parse_relative_date(date_str):
    """Convert 'il y a environ 1 heure' → '2025-12-17'"""
    date_str = date_str.strip().lower()
    if "il y a" not in date_str:
        return "N/A"

    date_str = re.sub(r'environ\s*', '', date_str)
    match = re.match(r'il y a (\d+)\s*(heure|heures|jour|jours|semaine|semaines|mois|an|ans)', date_str)
    if not match:
        return "N/A"

    num = int(match.group(1))
    unit = match.group(2).rstrip('s')

    now = datetime.now()
    deltas = {
        "heure": timedelta(hours=num),
        "jour": timedelta(days=num),
        "semaine": timedelta(weeks=num),
        "mois": timedelta(days=num * 30),
        "an": timedelta(days=num * 365),
    }
    past_date = now - deltas.get(unit, timedelta(days=0))
    return past_date.strftime('%Y-%m-%d')


# ====================== INFINITE SCROLL SCRAPING ======================

async def scrape_all_jobs_with_infinite_scroll():
    """Scroll through infinite scroll to load all jobs and extract URLs"""
    url = "https://www.emploipartner.com/fr/jobs/search"
    
    js_commands = [
        """
        // Click cookie consent button if present
        await new Promise(r => setTimeout(r, 3000));
        const cookieBtn = document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button');
        if (cookieBtn) {
            cookieBtn.click();
            await new Promise(r => setTimeout(r, 2000));
        }
        
        // Function to get current job count
        function getJobCount() {
            const cards = document.querySelectorAll('article[data-testid="job-card"]');
            return cards.length;
        }
        
        // Initial job count
        let lastJobCount = getJobCount();
        console.log("Initial job count:", lastJobCount);
        
        // Scroll and load more jobs - SLOW SCROLLING
        let noNewJobsCount = 0;
        const maxNoNewJobs = 3; // Stop if no new jobs for 3 consecutive scrolls
        const scrollAmount = 200; // Scroll in smaller increments
        const scrollDelay = 1000; // 1 second between each small scroll
        
        while (noNewJobsCount < maxNoNewJobs) {
            // Scroll slowly in increments
            const currentScrollTop = window.scrollY;
            const targetScrollTop = document.body.scrollHeight;
            const scrollDistance = targetScrollTop - currentScrollTop;
            const numScrolls = Math.ceil(scrollDistance / scrollAmount);
            
            for (let i = 0; i < numScrolls; i++) {
                window.scrollBy(0, scrollAmount);
                await new Promise(r => setTimeout(r, scrollDelay));
            }
            
            // Wait for lazy loading after scrolling
            await new Promise(r => setTimeout(r, 2500));
            
            // Check if new jobs loaded
            const currentJobCount = getJobCount();
            console.log("Current job count:", currentJobCount);
            
            if (currentJobCount === lastJobCount) {
                noNewJobsCount++;
                console.log("No new jobs, count:", noNewJobsCount);
                
                // Try scrolling a bit up and down to trigger loading
                if (noNewJobsCount < maxNoNewJobs) {
                    // Slow scroll up
                    for (let i = 0; i < 5; i++) {
                        window.scrollBy(0, -100);
                        await new Promise(r => setTimeout(r, 500));
                    }
                    
                    // Slow scroll back down
                    for (let i = 0; i < 10; i++) {
                        window.scrollBy(0, scrollAmount);
                        await new Promise(r => setTimeout(r, 500));
                    }
                    
                    await new Promise(r => setTimeout(r, 2000));
                }
            } else {
                noNewJobsCount = 0; // Reset counter if new jobs found
                lastJobCount = currentJobCount;
            }
            
            // Break if we've scrolled too much (safety)
            if (lastJobCount > 200) {
                console.log("Reached safety limit of 200 jobs");
                break;
            }
        }
        
        console.log("Finished scrolling. Total jobs found:", lastJobCount);
        return lastJobCount;
        """
    ]

    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        verbose=True
    )

    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(
                url=url,
                config=CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    js_code=js_commands,
                    delay_before_return_html=10,
                    verbose=True
                )
            )

            if not result.success:
                print(f"Failed to load page: {result.error_message}")
                return []

            print(f"Successfully loaded page with infinite scroll")
            soup = BeautifulSoup(result.html, 'html.parser')
            
            # Extract all job URLs from the page
            job_links = []
            
            # Find all job cards and get parent <a> tags
            job_cards = soup.find_all("article", {"data-testid": "job-card"})
            print(f"Found {len(job_cards)} job cards")
            
            for card in job_cards:
                # Try multiple ways to find the link
                job_url = None
                
                # Method 1: Find parent <a> tag
                a_tag = card.find_parent('a', href=True)
                if a_tag and a_tag.get('href'):
                    job_url = a_tag['href']
                
                # Method 2: Find <a> tag within the card
                if not job_url:
                    a_tag = card.find('a', href=True)
                    if a_tag and a_tag.get('href'):
                        job_url = a_tag['href']
                
                # Method 3: Look for any href attribute in the card
                if not job_url:
                    all_tags_with_href = card.find_all(href=True)
                    if all_tags_with_href:
                        job_url = all_tags_with_href[0]['href']
                
                if job_url:
                    # Ensure it's a full URL
                    if not job_url.startswith('http'):
                        job_url = "https://www.emploipartner.com" + job_url
                    
                    # Extract basic info from card for logging
                    title_tag = card.find('h3', class_=re.compile(r"text-lg font-semibold"))
                    titre = title_tag.get_text(strip=True) if title_tag else "N/A"
                    
                    # Extract location and date from card
                    loc_date_tag = card.find('p', class_='line-clamp-1')
                    loc_date_text = loc_date_tag.get_text(strip=True) if loc_date_tag else ""
                    
                    # Extract date from the text (assuming format: "Location - date")
                    date_match = re.search(r'il y a.*', loc_date_text)
                    date_str = date_match.group(0) if date_match else ""
                    date_depot = parse_relative_date(date_str)
                    
                    job_links.append({
                        'url': job_url,
                        'titre': titre,
                        'date_depot': date_depot
                    })
                else:
                    print(f"Warning: Could not extract URL from job card")
            
            print(f"Extracted {len(job_links)} unique job URLs")
            return job_links
            
    except Exception as e:
        print(f"Error during infinite scroll scraping: {e}")
        import traceback
        traceback.print_exc()
        return []


# ====================== PROCESS ALL JOBS ======================

async def process_all_jobs():
    """Main function to scrape all jobs with infinite scroll and process them"""
    print("\nStarting crawl of emploipartner.com with infinite scroll...\n")
    
    # Step 1: Scrape all job URLs with infinite scroll
    job_data_list = await scrape_all_jobs_with_infinite_scroll()
    
    if not job_data_list:
        print("No jobs found. Exiting.")
        return
    
    print(f"\nFound {len(job_data_list)} jobs to process\n")
    
    # Step 2: Process each job (with concurrency limit)
    semaphore = asyncio.Semaphore(5)  # Reduced concurrency to avoid overwhelming
    
    async def process_job(job_data):
        async with semaphore:
            try:
                print(f"Processing: {job_data['titre']} - {job_data['url']}")
                await scrape_single_url_with_crawl4ai_and_bs4(job_data['url'])
                await asyncio.sleep(1)  # Small delay between requests
            except Exception as e:
                print(f"Error processing {job_data['url']}: {e}")
    
    # Process jobs in batches to avoid timeout
    batch_size = 20
    for i in range(0, len(job_data_list), batch_size):
        batch = job_data_list[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(job_data_list) - 1) // batch_size + 1
        print(f"\nProcessing batch {batch_num}/{total_batches} ({len(batch)} jobs)")
        
        tasks = [process_job(job_data) for job_data in batch]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Wait between batches
        if i + batch_size < len(job_data_list):
            print(f"Waiting 5 seconds before next batch...")
            await asyncio.sleep(5)
    
    print(f"\nAll {len(job_data_list)} jobs processed. Scraping complete!")


# ====================== MAIN ======================

async def main():
    await process_all_jobs()


if __name__ == "__main__":
    asyncio.run(main())