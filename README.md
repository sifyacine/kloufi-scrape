# Kloufi Scrape (kloufi-scrape)

A Python web-scraping project with components for crawling, scraping, proxy management, and detection helpers.

## 🔧 Quick start

Prerequisites:
- Python 3.11+ (recommended)
- git

Setup:

1. Clone the repository

   ```bash
   git clone <your-repo-url>
   cd kloufi-scrape
   ```

2. Create and activate a virtual environment

   Windows (PowerShell):
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Run a component

   Example (crawler):
   ```bash
   python scraper/main.py
   ```

   Or run other scripts directly, e.g. `python immobilier/ouedkniss/main.py`.

## 🧾 Files added
- `.gitignore` — common Python ignores (virtualenv, caches, logs, env files)
- `requirements.txt` — pinned dependencies from the current environment
- `README.md` — this file

## 📝 Notes
- If you want to track dataset files under `data/`, remove or adjust any matching lines in `.gitignore`.
- To regenerate `requirements.txt` after changing environment packages, run:

  ```bash
  python -m pip freeze > requirements.txt
  ```

## Contributing
Open issues or pull requests with proposed changes. Keep changes focused and include tests where possible.

---

## 🐳 Docker deployment
A convenient way to run the project is with Docker and Docker Compose. See `DEPLOYMENT.md` for step-by-step build and run instructions, including an option to install Playwright browsers if needed.

If you want, I can add a simple CI workflow, license file, or a CONTRIBUTING guide next. 👇

