import json
import asyncio
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
from scrape_details import extract_property_details
import sys
sys.setrecursionlimit(10000)

async def scrape_main_page():
    # 1. Define a refined extraction schema to exclude pagination links
    schema = {
        "name": "Property Listings",
        "baseSelector": "li:has(h3)",  # Selects only listings with a title (h3)
        "fields": [
            {
                "name": "title",
                "selector": "h3",  # Extract the property title
                "type": "text"
            },
            {
                "name": "url",
                "selector": "a",
                "type": "attribute",
                "attribute": "href"  # Extract the property link
            },
            {
                "name": "location",
                "selector": "span.location",  # Extract the location
                "type": "text"
            },
            {
                "name": "price",
                "selector": "strong.price",  # Extract the price
                "type": "text"
            },
            {
                "name": "property_type",
                "selector": "span.views",  # Extract the property type
                "type": "text"
            },
            {
                "name": "date_posted",
                "selector": "em.date",  # Extract the date posted
                "type": "text"
            }
        ]
    }

    # 2. Create the extraction strategy
    extraction_strategy = JsonCssExtractionStrategy(schema, verbose=True)

    # 3. Configure the crawler
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=extraction_strategy,
    )

    async with AsyncWebCrawler(verbose=True) as crawler:
        all_data = []
        base_url = "https://www.algerieannonces.com/categorie/16/Vente-immobilier.html"
        current_page_url = base_url
        page_number = 1

        while True:
            print(f"Scraping page {page_number}: {current_page_url}")

            # 4. Run the crawler
            result = await crawler.arun(url=current_page_url, config=config)

            if not result.success:
                print(f"Failed to scrape {current_page_url}: {result.error_message}")
                break

            # 5. Parse extracted JSON data
            extracted_data = json.loads(result.extracted_content)
            print(f"Extracted {len(extracted_data)} property listings from page {page_number}")

            # 6. Filter out unwanted pagination URLs
            filtered_data = []
            for item in extracted_data:
                if "url" in item and "Vente-immobilier/" in item["url"]:
                    if any(char.isdigit() for char in item["url"].split("/")[-1]):  # Check if URL ends with a number
                        print(f"Skipping pagination link: {item['url']}")
                        continue

                # Normalize the full URL
                item["url"] = (
                    "https://www.algerieannonces.com/" + item["url"]
                    if item["url"].startswith("categorie")
                    else item["url"]
                )

                try:
                    await extract_property_details(item["url"], item)
                    print(f"Extracting details for {item['url']}")
                    filtered_data.append(item)
                except Exception as e:
                    print(f"Error extracting details for {item['url']}: {e}")
                    continue

            all_data.extend(filtered_data)
            print(f"Extracted {len(filtered_data)} valid property listings from page {page_number}")
            print(f"Total properties extracted: {len(all_data)}")

            # 7. Find the next page button
            soup = BeautifulSoup(result.html, "html.parser")
            next_button = soup.find("a", string="Suivant")

            if next_button and "href" in next_button.attrs:
                next_page_url = next_button["href"]

                # Ensure we are following the correct pagination URL
                if next_page_url:
                    next_page_url = "https://www.algerieannonces.com/" + next_page_url

                # Check if the next page is a valid one (not pagination URL)
                if any(char.isdigit() for char in next_page_url.split("/")[-1]):
                    current_page_url = next_page_url
                    page_number += 1
                    print(f"Next page found: {current_page_url}")
                else:
                    print("No more pages to scrape.")
                    break
            else:
                print("No next page found.")
                break

        # 8. Output results
        print(f"Total properties extracted: {len(all_data)}")
        print(json.dumps(all_data, indent=2) if all_data else "No data found")

# Run the scraper
asyncio.run(scrape_main_page())
