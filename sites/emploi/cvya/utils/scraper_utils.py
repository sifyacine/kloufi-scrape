import re
import json
import os
from datetime import datetime
from typing import List

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
    JsonCssExtractionStrategy,
    LLMConfig,
    LLMExtractionStrategy,
)
from models.job_listing import JobListing

def normalize_domaine(domaine):
    # Commerce & Vente
    # Commercial & Marketing
    # Industrie & Production
    # Tourisme & Gastronomie
    # Beauté & Esthétique
    # Nettoyage & Hygiène
    # Bureautique & Secretariat
    # Informatique & Internet
    # Couture et Confection
    # Comptabilité & Audit
    # Administration & Management
    # Graphisme & Communication
    # Agents polyvalents
    # Mécanique Auto
    # Eléctronique & Téchnique
    # Artisanat
    # Securité
    # Immobilier
    # Juridique
    # Achat & Logistique
    # Journalisme & Pressente
    # Environnement
    # Recherche & developpement
    # Construction & Travaux
    # Carburants & Mines
    # Transport & Chauffeurs
    # Medecine & Santé
    # Banque
    # Assurance
    # Distribution
    # Industries
    # Services
    # Autre

    mapping = {
        "Achats": "Achat & Logistique",
        "Commercial, vente": "Commerce & Vente",
        "Gestion, comptabilité, finance": "Comptabilité & Audit",
        "Informatique, nouvelles technologies": "Informatique & Internet",
        "Juridique": "Juridique",
        "Management, direction générale": "Administration & Management",
        "Marketing, communication": "Commercial & Marketing",
        "Métiers de la santé et du social": "Medecine & Santé",
        "Métiers des services": "Services",
        "Métiers du BTP": "Construction & Travaux",
        "Production, maintenance, qualité": "Industrie & Production",
        "R&D, gestion de projets": "Recherche & developpement",
        "RH, formation": "Administration & Management",
        "Secrétariat, assistanat":  "Bureautique & Secretariat",
        "Télémarketing, téléassistance": "Commercial & Marketing",
        "Tourisme, hôtellerie, restauration": "Tourisme & Gastronomie",
        "Transport, logistique": "Achat & Logistique",
    }

    return mapping.get(domaine.strip(), domaine.strip())

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
        "niveau secondaire": "Diplome de collège",
        "niveau terminal": "Diplome de collège",
        "baccalauréat": "Bac",
        "bac +2": "Diplome universitaire",
        "ts bac +2": "Diplome universitaire",
        "ts bac +2 | Formation Professionnelle": "Diplôme professionnel / téchnique",
        "licence": "Diplome universitaire",
        "licence (lmd), bac + 3": "Diplome universitaire",
        "licence bac + 4": "Diplome universitaire",
        "bac + 3": "Diplome universitaire",
        "bac+3": "Diplome universitaire",
        "master 1": "Master",
        "master 1, licence  bac + 4": "Diplome universitaire",
        "master 2, ingéniorat, bac + 5": "Diplome universitaire",
        "baster 2": "Master",
        "ingéniorat": "Diplome universitaire",
        "bac + 5": "Diplome universitaire",
        "magistère bac + 7": "Diplome universitaire",
        "doctorat": "Doctorat",
        "certification": "Diplôme professionnel / téchnique",
        "formation professionnelle": "Diplôme professionnel / téchnique",
        "universitaire sans diplôme": "Diplôme professionnel / téchnique",
        "non diplômante": None,
        "sans diplôme": None,
        "sans diplome": None,
    }
    return mapping.get(diplome, diplome)



def get_browser_config() -> BrowserConfig:
    return BrowserConfig(
        browser_type="firefox",
        headless=False,
        verbose=True,
    )

def get_llm_strategy() -> LLMExtractionStrategy:
    """
    Update the LLM instruction to include 'image_url' if present in the page.
    The model_json_schema can be adapted so that 'image_url' is recognized
    or simply appended to your existing schema.
    """
    instruction = (
        "Extrait toutes les offres d'emploi figurant dans la page. "
        "Pour chaque offre, renvoie un objet JSON avec les champs suivants : "
        "'url', 'title', 'employeur', 'wilaya', 'description', 'date_depot', "
        "'image_url'. "  # New field to capture potential image
        "Si un champ n'est pas trouvé, renvoie une chaîne vide."
    )

    return LLMExtractionStrategy(
        llm_config=LLMConfig(
            provider="groq/deepseek-r1-distill-llama-70b",
            api_token=os.getenv("GROQ_API_KEY"),
        ),
        extraction_strategy=JsonCssExtractionStrategy(JobListing.model_json_schema, verbose=True),
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
    numero = parse_numero_from_url(url_str) or ""

    # If 'image_url' is returned by the LLM extraction, we capture it here
    image_url = clean_text(job.get("image_url", ""))

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
        "diplome_src": [],
        "domaine": normalize_domaine(job.get("domaine", "")),
        "description": clean_text(job.get("experience", "")),  # or use job.get("description", "")
        "employeur": clean_text(job.get("employeur", "")),
        "poste": clean_text(job.get("post", "")),
        "adresse": clean_text(job.get("adresse", "")),
        "wilaya": validate_wilaya(clean_text(job.get("wilaya", ""))),
        "status": 200,
        "date_verif": now,
        # If an image is present, put it in the array. Otherwise, it's empty.
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
    # JavaScript commands:
    # 1. Wait for initial load and dismiss cookie consent.
    # 2. Remove the unwanted clients slider widget.
    # 3. Scroll down to trigger lazy-loading.
    # 4. Wait until job cards (".panel.panel-clickable") appear.
    js_commands = [
        "await new Promise(resolve => setTimeout(resolve, 6000));",
        "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",
        "document.querySelectorAll('.elementor-widget-ct_clients_list').forEach(el => el.remove());",
        """
        await new Promise(resolve => {
            let maxScrollHeight = document.body.scrollHeight;
            let currentScroll = 0;
            let scrollStep = 300;
            let interval = setInterval(() => {
                window.scrollBy(0, scrollStep);
                currentScroll += scrollStep;
                if (currentScroll >= maxScrollHeight) {
                    clearInterval(interval);
                    resolve();
                }
            }, 500);
        });
        """,
    
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
    print("Raw extracted content:", result.extracted_content)

    if not result.success:
        print(f"❌ Error fetching page: {result.error_message}")
        return []

    try:
        extracted_data = json.loads(result.extracted_content)
        print("Extracted JSON data:")
        print(json.dumps(extracted_data, indent=2, ensure_ascii=False))
    except json.JSONDecodeError as e:
        print(f"❌ JSON decoding error: {e}")
        return []

    processed_jobs = [format_job_data(job) for job in extracted_data]
    if processed_jobs:
        print("First extracted job (after formatting):")
        print(json.dumps(processed_jobs[0], indent=2, ensure_ascii=False))
    else:
        print("No job listings extracted after formatting.")

    return processed_jobs
