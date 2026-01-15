import json
import os
from typing import List, Set
from dotenv import load_dotenv
from bs4 import BeautifulSoup

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
    LLMExtractionStrategy,
)
from crawl4ai.async_configs import LlmConfig

from models.tv import Tv
from utils.data_utils import is_complete_tv, is_duplicate_tv

load_dotenv()


def get_browser_config() -> BrowserConfig:
    return BrowserConfig(
        browser_type="chromium",
        headless=True,
        verbose=True,
    )


def get_llm_strategy() -> LLMExtractionStrategy:
    return LLMExtractionStrategy(
        llmConfig=LlmConfig(
            provider="groq/deepseek-r1-distill-llama-70b",
            api_token=os.getenv("DEEPSEEK_API_KEY"),
        ),
        schema=Tv.model_json_schema(),
        extraction_type="schema",
        instruction=(
            "Extrait tous les téléviseurs avec les champs suivants : 'titre' (nom), "
            "'prix_dec' (prix en valeur numérique), 'prix_unit' (monnaie), 'stock', 'etat', "
            "'description', 'resolution', 'type_ecran', 'modele', 'taille_ecran', 'marque', "
            "'img' (liste des URLs des images réelles du produit, pas de placeholders), "
            "'categorie', 'couleur', 'url', 'livraison', et toutes les autres spécifications disponibles. "
            "Tout champ non trouvé doit être inclus en tant que chaîne vide. "
        ),
        input_format="markdown",
        verbose=True,
    )

async def fetch_and_process_page(
    crawler: AsyncWebCrawler,
    base_url: str,
    css_selector: str,
    llm_strategy: LLMExtractionStrategy,
    session_id: str,

) -> List[dict]:
    result = await crawler.arun(
        url=base_url,
        config=CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            extraction_strategy=llm_strategy,
            css_selector=css_selector,
            session_id=session_id,
        ),
    )

    if not (result.success and result.extracted_content):
        print(f"❌ Error fetching page: {result.error_message}")
        return []

    try:
        extracted_data = json.loads(result.extracted_content)
    except json.JSONDecodeError as e:
        print(f"❌ JSON decoding error: {e}")
        return []

    complete_tvs = extracted_data

    return complete_tvs

async def crawl_tv_product_page(url: str) -> dict:
    """Crawl a single TV product page and extract the image and other data."""
    browser_config = get_browser_config()

    async with AsyncWebCrawler(config=browser_config) as crawler:
        # Adjust the CSS_SELECTOR_PRODUCT to match the image URL extraction
        result = await crawler.arun(
            url=url,
            javascript_enabled=True,
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                delay_before_return_html=3
            ),
        )

        if not result.success:
            raise Exception("Failed to crawl the page")

        soup = BeautifulSoup(result.html, 'html.parser')
        product_image = soup.find("img", class_="zoomImg")
        images = []
        if product_image is not None:
            images.append(product_image.get("src"))
        print(f"Images found: {images}")
        return images