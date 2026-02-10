import asyncio
import random
from playwright.async_api import Page

async def human_delay(min_seconds: float = 0.5, max_seconds: float = 1.5) -> None:
    """
    Sleep for a random amount of time to simulate human processing/reaction time.
    """
    delay = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(delay)

async def human_mouse_move(page: Page, target_x: int = None, target_y: int = None) -> None:
    """
    Simulate human-like mouse movement.
    If target_x/y are None, moves to a random point on screen.
    """
    viewport = page.viewport_size
    if not viewport:
        return

    width = viewport['width']
    height = viewport['height']
    
    if target_x is None:
        target_x = random.randint(0, width)
    if target_y is None:
        target_y = random.randint(0, height)
    
    steps = random.randint(5, 15)
    await page.mouse.move(target_x, target_y, steps=steps)

async def human_scroll(page: Page, max_scrolls: int = None) -> None:
    """
    Scroll the page in a human-like manner:
    - Variable distances
    - Variable speed
    - Occasional pauses
    - Occasional scroll UP (re-reading)
    """
    if max_scrolls is None:
        max_scrolls = random.randint(5, 15)

    for _ in range(max_scrolls):
        # 10% chance to scroll up slightly (behavioral imperfection)
        if random.random() < 0.1:
            scroll_up_amount = random.randint(100, 300)
            await page.mouse.wheel(0, -scroll_up_amount)
            await human_delay(0.5, 1.5)
        
        # Scroll down
        scroll_amount = random.randint(300, 800)
        await page.mouse.wheel(0, scroll_amount)
        
        # Random pause after scroll
        await human_delay(0.5, 2.0)
        
        # 20% chance to move mouse idly after scroll
        if random.random() < 0.2:
            await human_mouse_move(page)

async def simulate_reading(page: Page, min_seconds: float = 2.0) -> None:
    """
    Simulate reading content by waiting and moving the mouse idly.
    """
    reading_time = random.uniform(min_seconds, min_seconds * 2)
    start_time = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start_time) < reading_time:
        if random.random() < 0.3:
            await human_mouse_move(page)
        
        interval = min(0.5, reading_time - (asyncio.get_event_loop().time() - start_time))
        if interval > 0:
            await asyncio.sleep(interval)

async def random_mistake(page: Page) -> None:
    """
    Simulate a user mistake, like clicking mostly empty space or hovering over irrelevant elements.
    """
    if random.random() < 0.05: # 5% chance
        await human_mouse_move(page)
        await human_delay(0.5, 1.0)
