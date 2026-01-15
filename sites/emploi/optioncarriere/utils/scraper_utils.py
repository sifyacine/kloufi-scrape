import re
import json
import os
import requests
from datetime import datetime, timedelta
from typing import List
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
from model.job_listing import JobListing


def parse_french_relative_date(date_str: str) -> datetime:
    now = datetime.now()

    # Match "Il y a 17 heures"
    match = re.search(
        r"Il y a (\d+)\s*(minute|minutes|heure|heures|jour|jours)", date_str.lower())
    if not match:
        return now  # Default: return now if it doesn't match

    value = int(match.group(1))
    unit = match.group(2)

    if unit in ["minute", "minutes"]:
        return now - timedelta(minutes=value)
    elif unit in ["heure", "heures"]:
        return now - timedelta(hours=value)
    elif unit in ["jour", "jours"]:
        return now - timedelta(days=value)

    return now


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def validate_wilaya(wilaya_str: str) -> str:
    return wilaya_str


def parse_numero_from_url(url: str) -> str:
    match = re.search(r"/(\d+)$", url.strip("/"))
    if match:
        return match.group(1)
    return ""


def map_diplome(diplome):
    mapping = {
        "Bac": "Baccalauréat",
        "Bac+2": "Baccalauréat + 2",
    }
    if isinstance(diplome, list):
        return [mapping.get(item, item) for item in diplome]
    return mapping.get(diplome, diplome)


def get_browser_config() -> BrowserConfig:
    return BrowserConfig(
        browser_type="firefox",
        headless=True,
        verbose=True,
    )


def get_llm_strategy() -> LLMExtractionStrategy:

    instruction = (
        "Extrait toutes les offres d'emploi figurant dans la page. "
        "Pour chaque offre, renvoie un objet JSON avec les champs suivants : "
        "'url', 'title', 'employeur', 'wilaya', 'description', 'date_depot'. "
        "Si un champ n'est pas trouvé, renvoie une chaîne vide."
    )

    return LLMExtractionStrategy(
        llmConfig=LlmConfig(
            provider="groq/llama-3.1-8b-instant",
            api_token=os.getenv("DEEPSEEK_API_KEY"),
        ),
        extraction_strategy=JsonCssExtractionStrategy(
            JobListing.model_json_schema, verbose=True),
        instruction=instruction,
        input_format="markdown",
        verbose=True,
        chunk_token_threshold=1000,
        overlap_rate=0.0,
        apply_chunking=True,
    )


def format_job_data(job: dict) -> dict:
    now = datetime.now().isoformat()
    url_str = job.get("url", "")
    # Parse a job "numero" from the URL if possible; otherwise, use empty string.
    # (If your job IDs are alphanumeric, you might need a different approach.)
    numero = parse_numero_from_url(url_str) or ""

    # Retrieve image URL if available
    image_url = ""
    if "image" in job and job["image"]:
        image_url = job["image"]

    formatted = {
        "date_crawl": now,
        "url": url_str,
        "site_origine": job.get("site_origine", "Optioncarriere.dz"),
        "titre": clean_text(job.get("title", "")),
        "niveau": [clean_text(job.get("niveau", ""))] if job.get("niveau") else [],
        "numero": numero,
        "date_depot": clean_text(job.get("date_depot", "")),
        "transaction": "Offres",
        "contrat": clean_text(job.get("contrat", "")),
        "diplome": map_diplome(job.get("diplome", "")) if job.get("diplome") else [],
        "diplome_src": [],  # Populate if you have a secondary source; otherwise empty list
        "domaine": clean_text(job.get("domaine", "")),
        # or job.get("description", "") if available
        "description": clean_text(job.get("experience", "")),
        "employeur": clean_text(job.get("employeur", "")),
        "poste": clean_text(job.get("post", "")),
        "adresse": clean_text(job.get("adresse", "")),
        "wilaya": validate_wilaya(clean_text(job.get("wilaya", ""))),
        "status": 200,
        "date_verif": now,
        "images": [image_url] if image_url else [],
        "as_photo": "Avec photo" if image_url else "Sans photo",
        "prix": "",
        "prix_unit": "",
        "prix_dec": "",
        "as_prix": "Sans prix",
        "vehicle": "False"
    }
    return formatted


async def fetch_and_process_jobs(
    crawler: AsyncWebCrawler,
    base_url: str,
    llm_strategy: LLMExtractionStrategy,
    session_id: str,
) -> List[dict]:

    # 1) Run JavaScript commands to load the page (scroll, dismiss consent, etc.)
    js_commands = [
        "await new Promise(resolve => setTimeout(resolve, 6000));",
        "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",
        """
        await new Promise(resolve => setTimeout(resolve, 3000));
        let maxScrollHeight = document.body.scrollHeight;
        let slowFactor = 2;
        let scrollStep = 400 / slowFactor;
        let currentScroll = 0;
        while (currentScroll < maxScrollHeight) {
            window.scrollBy(0, scrollStep);
            currentScroll += scrollStep;
            await new Promise(resolve => setTimeout(resolve, 400 * slowFactor));
            maxScrollHeight = document.body.scrollHeight;
        }
        """
    ]

    result = await crawler.arun(
        url=base_url,
        config=CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            extraction_strategy=llm_strategy,
            session_id=session_id,
            js_code=js_commands,
        ),
    )
    print(f"[DEBUG] Extraction completed. Success: {result.success}")

    if not result.success:
        print(f"❌ Error fetching page: {result.error_message}")
        return []

    try:
        extracted_data = json.loads(result.extracted_content)
    except json.JSONDecodeError as e:
        print(f"❌ JSON decoding error: {e}")
        return []

    # 2) Parse rendered HTML using 'markdown' to extract data-url from detail buttons
    captured_urls = []
    if result.markdown:
        soup = BeautifulSoup(result.markdown, "html.parser")
        detail_buttons = soup.select('button[aria-label="Mettre à jour"]')
        captured_urls = [btn.get("data-url", "") for btn in detail_buttons]
        print(f"[DEBUG] Found {len(captured_urls)} data-urls in rendered HTML")
    else:
        print("❌ No markdown available in the result")

    # 4) Format the final job data
    processed_jobs = [format_job_data(job) for job in extracted_data]
    if processed_jobs:
        print("First extracted job (after formatting):")
        print(json.dumps(processed_jobs[0], indent=2, ensure_ascii=False))
    else:
        print("No job listings extracted after formatting.")

    return processed_jobs
