import random

VIEWPORTS = [(1366, 768), (1440, 900), (1536, 864), (1920, 1080)]
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0"
]

def build_context(country="FR"):
    width, height = random.choice(VIEWPORTS)
    ua = random.choice(USER_AGENTS)
    return {
        "user_agent": ua,
        "locale": "fr-FR",
        "timezone_id": "Europe/Paris",
        "viewport": {"width": width, "height": height},
    }