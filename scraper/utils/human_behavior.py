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

async def hover_random_elements(page: Page, selector: str) -> None:
    """
    Find elements matching selector and hover over some of them randomly.
    """
    elements = await page.locator(selector).all()
    if not elements:
        return
    
    # Hover over 1-3 random elements
    to_hover = random.sample(elements, min(len(elements), random.randint(1, 3)))
    for el in to_hover:
        try:
            # Scroll into view naturally if needed
            await el.scroll_into_view_if_needed()
            await human_delay(0.5, 1.5)
            
            # Get bounding box to hover within it
            box = await el.bounding_box()
            if box:
                target_x = box['x'] + random.randint(5, int(box['width']) - 5)
                target_y = box['y'] + random.randint(5, int(box['height']) - 5)
                await human_mouse_move(page, target_x, target_y)
                await human_delay(1, 3) # "Thinking" while hovering
        except:
            continue

async def random_navigation(page: Page, base_domain: str = "ouedkniss.com") -> bool:
    """
    Perform a random navigation action:
    - 40% Go back (if possible)
    - 40% Click a random internal link
    - 20% Just stay and scroll more
    Returns True if navigation happened, False otherwise.
    """
    action = random.random()
    
    if action < 0.4: # Go back
        print("  [Human] Decided to go back...")
        try:
            await page.go_back(wait_until='domcontentloaded')
            await human_delay(2, 5)
            return True
        except:
            return False
            
    elif action < 0.8: # Click random internal link
        print("  [Human] Looking for something else to click...")
        try:
            # Find all internal links that look like category or other sections
            links = await page.locator(f'a[href*="{base_domain}"], a[href^="/"]').all()
            if links:
                target = random.choice(links)
                href = await target.get_attribute('href')
                # Avoid common non-navigational links
                if href and not any(x in href for x in ['tel:', 'mailto:', '#', 'javascript:']):
                    await target.scroll_into_view_if_needed()
                    await human_delay(1, 2)
                    await target.click()
                    await human_delay(3, 7)
                    return True
        except:
            pass
            
    return False
