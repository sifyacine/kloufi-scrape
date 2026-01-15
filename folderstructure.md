Kloufi Scraper: New Project Structure
This document outlines the architecture of the reorganized scraping project. It is designed to be modular, scalable, and easy to maintain by multiple developers.

📂 Folder Structure
kloufi-scrape/
├── scraper/              # Core Engines (Shared)
│   ├── browser/         # Browser fingerprinting & context (Playwright)
│   ├── crawler/         # Async crawler implementation
│   ├── proxy/           # Proxy fetching, scoring, and rotation
│   ├── detection/       # Cloudflare/Bot detection helpers
│   └── utils/           # Shared logging and configuration
├── models/               # Data Layer
│   ├── schemas/         # Pydantic models for each category
│   └── normalization_and_utils.py # Unified cleaning & parsing logic
├── sites/                # Site-Specific Logic (Organized by Category)
│   ├── immobilier/       # Sites: Ouedkniss, Krello, Beytic, Darrna, Essekna, Algeriahome, Lkeria, etc.
│   │   ├── ouedkniss/
│   │   └── krello/
│   ├── voiture/          # Sites: Ouedkniss, Tonobiles, ardias.fr, Autobessah, Djcar, Easyexport, etc.
│   │   └── ouedkniss/
│   ├── emploi/           # Sites: Ouedkniss, Emploipartner, Emploitic, Clicjob, Algeriejob, etc.
│   │   └── ouedkniss/
│   ├── electromenager/   # Sites: Ouedkniss, Websoog, Diardzair, Jumia, etc.
│   │   └── ouedkniss/
│   └── multimedia/       # Sites: Ouedkniss, Jumia, Ajini, Homecenterdz, Starmania, etc.
│       └── ouedkniss/
├── dispatcher.py         # Main entry point (Orchestrator)
├── scripts/              # VM & Docker control scripts (.sh)
├── Dockerfile            # Container definition
└── docker-compose.yml    # Service orchestration
🛠️ The scraper/ Core
The scraper/ folder contains the lower-level "engines" that handle the heavy lifting of web interaction.

1. Browser & Fingerprinting
Located in scraper/browser/, this module uses build_context to create a Playwright browser context that mimics a real user. It randomizes user-agents, viewports, and other browser fingerprints to minimize bot detection.

2. Crawler Runner
The scraper/crawler/ module provides a high-level crawl() function. It takes a URL, a proxy, and a browser context, then returns the HTML content after handling timeouts and basic retries.

3. Proxy Management (scraper/proxy/)
This is a critical part of the system, designed to handle high-volume scraping without being blocked.

How it works (The Strategy)
Multi-Source Fetching: proxy_sources.py aggregates proxies from public lists and your provided sources.
Dynamic Scoring: Every proxy is assigned a score. Successes increase the score; timeouts or "403 Forbidden" results decrease it significantly.
Sticky Domain Rotation: To avoid triggering anti-bot measures, we use a "sticky" rotation. A single worker will use the same high-performing proxy for a specific domain (e.g., ouedkniss.com) until it encounters a failure.
Automatic Blacklisting: If a proxy fails multiple times or is identified as a "Cloudflare Challenge" trigger, it is temporarily blacklisted.
Integration Logic
The ProxyManager is integrated at the worker level. It ensures that every request is routed through the best available proxy for that specific site's domain.

# Integration Example in Parser/Worker
domain = "ouedkniss.com"
proxy = proxy_manager.get_proxy(domain)
try:
    result = await crawl(url, proxy, context)
    if "blocked" in result.html:
        proxy_manager.report_failure(proxy) # Domain-specific block
    else:
        proxy_manager.report_success(proxy) # Success!
except TimeoutError:
    proxy_manager.report_failure(proxy)     # Network failure
🧹 Data Normalization
All extraction results must pass through models/normalization_and_utils.py. This ensures that data from different sites looks the same.

Prices: Converted to floats/integers safely.
Dates: Always returned in ISO format.
Types: Categories like "Villa" or "Diesel" are mapped to a standard set of values.
🚀 How to Add a New Site
Create a folder in sites/<site_name>.
Implement a crawler.py to find listing URLs.
Implement a parser.py using the selectors for that site.
Import the site in dispatcher.py to allow execution via CLI.
Use existing utilities in normalization_and_utils.py to clean the data.
🐳 Deployment & Control
Docker: The entire app is containerized. Use docker-compose up -d for production.
Scripts:
start.sh: Starts the scraping service.
stop.sh: Gracefully stops all workers.
status.sh: Shows current scraping progress and logs.
