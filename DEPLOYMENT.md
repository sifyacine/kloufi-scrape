# Deployment (Docker)

This file explains how to build and run the project using Docker and Docker Compose on your machine.

## Prerequisites
- Docker Engine (Docker Desktop on Windows recommended)
- (Optional) Docker Compose

## Build the image

From the repository root:

1) Build the default image (no Playwright browsers):

```bash
docker build -t kloufi-scrape:latest .
```

2) Build with Playwright and browsers (if you need Playwright-powered browsing features):

```bash
docker build --build-arg INSTALL_PLAYWRIGHT=true -t kloufi-scrape:playwright .
```

Note: Installing Playwright browsers increases image size and may require additional system libraries. Use only if you rely on Playwright features.

## Run the container (one-off)

Run locally, mounting `data/` and `logs/` so you keep outputs on the host:

Windows PowerShell:

```powershell
docker run --rm -it `
  -v ${PWD}\data:/app/data `
  -v ${PWD}\logs:/app/logs `
  --env-file .env `
  kloufi-scrape:latest
```

## Run with Docker Compose

From the repo root:

```bash
docker-compose up --build -d
```

To rebuild with Playwright browsers using Compose:

```bash
docker-compose build --build-arg INSTALL_PLAYWRIGHT=true && docker-compose up -d
```

To stop and remove:

```bash
docker-compose down
```

## Quick verification (smoke tests)

1. Build and start the container:

```bash
docker-compose up --build -d
```

2. Check the service is running and view logs:

```bash
docker-compose ps
docker-compose logs -f
```

3. Run a quick scrape command inside the container (example):

```bash
# Run the ouedkniss script inside the running image
docker-compose run --rm scraper python immobilier/ouedkniss/main.py
```

4. Inspect `./data` and `./logs` on the host for output and logs.



## Running specific scripts inside the image

You can run other scripts using `docker run` (override the command) or `docker-compose run`:

```bash
# example - run immobilier scraping script
docker-compose run --rm scraper python immobilier/ouedkniss/main.py
```

## Notes and recommended workflow
- Keep your local `.env` file for secrets and pass it via `env_file` in docker-compose. Do NOT commit secrets to git.
- If you change Python dependencies, update `requirements.txt` and rebuild the image:
  ```bash
  python -m pip freeze > requirements.txt
  docker-compose build
  ```
- If you need Playwright-run browsers, set the build-arg `INSTALL_PLAYWRIGHT=true` when building and ensure your host system supports required libraries.

---

If you'd like, I can also add a GitHub Actions workflow to build and publish the image automatically. Let me know which registry you prefer (Docker Hub, GitHub Container Registry, etc.).
