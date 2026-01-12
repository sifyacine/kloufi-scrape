import random

async def apply_stealth(page):
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    """)

async def human_behavior(page):
    await page.mouse.move(300, 300)
    await page.mouse.wheel(0, random.randint(300, 900))
    await page.wait_for_timeout(random.randint(800, 2000))