import re
import json
import os
from datetime import datetime
from typing import List

import requests
from bs4 import BeautifulSoup

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
    JsonCssExtractionStrategy,
    LLMExtractionStrategy,
)
from crawl4ai.async_configs import LlmConfig

# ------------------------
# Helpers
# ------------------------

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def validate_wilaya(wilaya_str: str) -> str:
    return wilaya_str

def parse_numero_from_url(url: str) -> str:
    """
    Example: Extract the final slug or numeric portion from the job detail URL.
    Adjust this logic if your detail URL is alphanumeric or more complex.
    e.g. /poste/-OJVQq82kNVXeMa1dtPA
    """
    match = re.search(r"/poste/([^/]+)$", url.strip("/"))
    if match:
        return match.group(1)
    return ""

# ------------------------
# Browser Config
# ------------------------

def get_browser_config() -> BrowserConfig:
    return BrowserConfig(
        browser_type="firefox",
        headless=False,
        verbose=True,
    )

# ------------------------
# LLM Extraction Strategy (HTML Approach)
# ------------------------

def get_llm_strategy() -> LLMExtractionStrategy:
    """
    Adapt your CSS selectors to match the structure on https://globaljob-dz.com/offres.
    For example, if each job is in <div class="col-12 col-md-6 col-xl-4">,
    that’s your baseSelector. Then inside, figure out how to get the title, date, location, etc.
    """
    schema = {
        "name": "Job Listings",
        "baseSelector": "div.col-12.col-md-6.col-xl-4",  # Adjust to real container on globaljob-dz
        "fields": [
            {"name": "title",       "selector": "h5.job-title a",     "type": "text"},
            {"name": "date_depot",  "selector": "span.date",           "type": "text"},
            {"name": "wilaya",      "selector": "span.location",       "type": "text"},
            {"name": "niveau",      "selector": "span.degree",         "type": "text"},
            {"name": "contrat",     "selector": "span.contract-type",  "type": "text"},
            {"name": "experience",  "selector": "span.experience",     "type": "text"},
            {"name": "post",        "selector": "span.post-nbr",       "type": "text"},
            {"name": "image",       "selector": "img.object-contain",  "type": "img"},
            {
                "name": "url",
                "selector": "h5.job-title a",
                "type": "text",
                "attr": "href"
            },
        ]
    }

    return LLMExtractionStrategy(
        llmConfig=LlmConfig(
            provider="deepseek-r1-distill-llama-70b",
            api_token=os.getenv("DEEPSEEK_API_KEY"),
        ),
        extraction_strategy=JsonCssExtractionStrategy(schema, verbose=True),
        instruction=(
            "Extrait la liste des offres d'emploi figurant sur la page. Pour chaque offre, "
            "retourne un objet JSON avec: title, date_depot, wilaya, niveau, contrat, "
            "experience, post, image, et url. Si un champ n'existe pas, renvoie une chaîne vide."
        ),
        input_format="markdown",
        verbose=True,
    )

# ------------------------
# Format the Final JSON
# ------------------------

def format_job_data(job: dict) -> dict:
    now = datetime.now().isoformat()
    url_str = job.get("url", "")

    formatted = {
        "date_crawl": now,
        "url": url_str,
        "site_origine": "globaljob-dz.com",
        "titre": clean_text(job.get("title", "")),
        "niveau": [clean_text(job["niveau"])] if job.get("niveau") else [],
        "numero": parse_numero_from_url(url_str),  # e.g. “-OJVQq82kNVXeMa1dtPA”
        "date_depot": clean_text(job.get("date_depot", "")),
        "transaction": "Offres",
        "contrat": clean_text(job.get("contrat", "")),
        "diplome": [],
        "diplome_src": [],
        "domaine": "",
        "description": clean_text(job.get("experience", "")),
        "employeur": "",
        "poste": clean_text(job.get("post", "")),
        "adresse": "",
        "wilaya": validate_wilaya(clean_text(job.get("wilaya", ""))),
        "status": 200,
        "date_verif": now,
        "images": [job["image"]] if job.get("image") else [],
        "as_photo": "Avec photo" if job.get("image") else "Sans photo",
        "prix": "",
        "prix_unit": "",
        "prix_dec": "",
        "as_prix": "Sans prix",
        "vehicle": "False"
    }
    return formatted

# --------------------------------------------------------
# Approach A: Directly Fetch from the Site's API (if any)
# --------------------------------------------------------

def fetch_jobs_via_api() -> List[dict]:
    """
    1) If you see in DevTools → Network that there's an API returning JSON,
       put that endpoint here (with correct query parameters, if needed).
    2) Then parse the JSON to get your job data.
    3) Return a list of dicts with fields 'title', 'wilaya', 'date_depot', etc.
    """
    # Example placeholder. Replace with the real endpoint you see in the Network tab.
    api_url = "https://globaljob-dz.com/api/v1/jobs"  # <--- Adjust to the actual URL

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/80.0.3987.162 Safari/537.36"
        )
    }

    try:
        response = requests.get(api_url, headers=headers)
        if response.status_code != 200:
            print(f"❌ API request failed with status {response.status_code}")
            return []
        data = response.json()

        # Adjust according to the real JSON structure.
        # Suppose the JSON looks like: { "jobs": [ {...}, {...} ] }
        # Or maybe it’s "hydra:member" or something else.
        job_list = data.get("jobs", [])  # or data["results"], etc.

        # Build final job dicts
        final_jobs = []
        for item in job_list:
            # Suppose you see item["slug"] or item["id"] in the JSON
            # The detail link might be: "https://globaljob-dz.com/poste/" + item["slug"]
            slug = item.get("slug", "")
            detail_url = f"https://globaljob-dz.com/poste/{slug}"

            # Gather the fields you need
            job_dict = {
                "title":       item.get("title", ""),
                "date_depot":  item.get("date_depot", ""),  # or "created_at", etc.
                "wilaya":      item.get("wilaya", ""),
                "niveau":      item.get("niveau", ""),
                "contrat":     item.get("contrat", ""),
                "experience":  item.get("experience", ""),
                "post":        item.get("post", ""),
                "image":       item.get("image", ""),       # or "logo_url"
                "url":         detail_url
            }
            final_jobs.append(job_dict)

        return final_jobs

    except Exception as e:
        print(f"❌ Exception while fetching API: {e}")
        return []

# --------------------------------------------------------
# Approach B: Use the Crawler + LLM Strategy (HTML)
# --------------------------------------------------------

async def fetch_and_process_jobs(
    crawler: AsyncWebCrawler,
    base_url: str,
    llm_strategy: LLMExtractionStrategy,
    session_id: str,
) -> List[dict]:
    """
    1) Load the listing page, run JavaScript to scroll fully.
    2) Extract job cards with the LLM strategy.
    3) If the real detail URL is hidden, parse it from the rendered HTML or intercept it via a button’s data-attr.
    4) Format the final data.
    """

    # 1) JavaScript to scroll & load more listings if needed
    js_commands = [
        "await new Promise(resolve => setTimeout(resolve, 6000));",
        # If there's a cookie consent button, adapt the selector:
        "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",
        """
        // Scroll the page slowly to load all job cards
        await new Promise(resolve => setTimeout(resolve, 3000));
        let maxScrollHeight = document.body.scrollHeight;
        let slowFactor = 1;
        let scrollStep = 1000000; // large step to jump to bottom
        let currentScroll = 0;
        while (currentScroll < maxScrollHeight) {
            window.scrollBy(0, scrollStep);
            currentScroll += scrollStep;
            await new Promise(resolve => setTimeout(resolve, 300 * slowFactor));
            maxScrollHeight = document.body.scrollHeight;
        }
        """
    ]

    # 2) Run the crawler on the listing page
    listing_result = await crawler.arun(
        url=base_url,
        config=CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            extraction_strategy=llm_strategy,
            session_id=session_id,
            js_code=js_commands,
        ),
    )

    if not listing_result.success:
        print(f"❌ Error fetching page: {listing_result.error_message}")
        return []

    # 3) Convert the extracted JSON to a Python list
    try:
        extracted_data = json.loads(listing_result.extracted_content)
    except json.JSONDecodeError as e:
        print(f"❌ JSON decoding error: {e}")
        return []

    print(f"[DEBUG] Extracted {len(extracted_data)} job cards (raw)")

    # 4) Check if the “url” is truly missing or partial. If so, see if we can parse
    #    some hidden attribute from the rendered HTML.
    captured_urls = []
    if listing_result.markdown:
        soup = BeautifulSoup(listing_result.markdown, "html.parser")
        
        # EXAMPLE: if the real link is inside <a data-url="https://globaljob-dz.com/poste/...">
        detail_links = soup.select('a[data-url]')
        captured_urls = [link.get("data-url", "") for link in detail_links if link.get("data-url")]
        print(f"[DEBUG] Found {len(captured_urls)} hidden URLs in data-url attributes.")
    else:
        print("[DEBUG] No markdown available to parse hidden attributes.")

    # If the number of captured_urls matches the length of your extracted_data, zip them:
    if captured_urls and len(captured_urls) == len(extracted_data):
        for job, hidden_url in zip(extracted_data, captured_urls):
            job["url"] = hidden_url
    else:
        print("[DEBUG] Could not match hidden URLs to extracted jobs perfectly. Handling partial…")
        for i, job in enumerate(extracted_data):
            if i < len(captured_urls):
                job["url"] = captured_urls[i]

    # 5) (Optional) If you want to actually open each job detail page and extract more fields,
    #    replicate your “detail_strategy” approach from EmploiPartner code. 
    #    For now, we skip that and just finalize.

    # 6) Format each job
    processed_jobs = [format_job_data(job) for job in extracted_data]

    if processed_jobs:
        print("[DEBUG] First job after formatting:")
        print(json.dumps(processed_jobs[0], indent=2, ensure_ascii=False))
    else:
        print("[DEBUG] No job listings after formatting.")

    return processed_jobs
