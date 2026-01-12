import random

VIEWPORTS = [(1366,768), (1440,900), (1536,864), (1920,1080)]


def build_context(country="FR"):
    width, height = random.choice(VIEWPORTS)
    return {
        "locale": "fr-FR",
        "timezone_id": "Europe/Paris",
        "viewport": {"width": width, "height": height},
    }