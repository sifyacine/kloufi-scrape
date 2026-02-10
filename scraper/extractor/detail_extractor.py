from playwright.async_api import Page
import re
import random
from scraper.utils.human_behavior import human_delay, simulate_reading, human_scroll, human_mouse_move

class DetailExtractor:
    """Extracts detailed information from a single Ouedkniss announcement page."""
    
    def __init__(self, page: Page):
        self.page = page

    async def extract(self, url: str) -> dict:
        """
        Navigates to the URL and extracts announcement details.
        Returns a dictionary with the extracted data, or None if failed.
        """
        page = self.page # Use the injected page
        try:
            # Block heavy resources to speed up loading
            # await page.route("**/*.{png,jpg,jpeg,webp,gif,css,woff,woff2}", lambda route: route.abort())
            
            print(f"  Fetching details: {url}")
            await page.goto(url, wait_until='domcontentloaded', timeout=45000)
            
            # Human behavior: Simulate reading the ad before extracting
            print(f"  [Human] Reading advertisement...")
            await simulate_reading(page, min_seconds=4)
            
            # Maybe scroll a bit to see the whole ad
            if random.random() < 0.5:
                await human_scroll(page, max_scrolls=2)

            data = await self._scrape_data(page)
            data['url'] = url
            # Extract ID from URL (last segment after dash)
            if '-' in url:
                data['id'] = url.split('-')[-1].split('?')[0] # Handle query params if any
            
            return data
            
        except Exception as e:
            print(f"  [ERROR] Extracting {url}: {e}")
            try:
                # Save debug info
                import time
                ts = int(time.time())
                # await page.screenshot(path=f"debug_detail_fail_{ts}.png")
                content = await page.content()
                with open(f"debug_detail_fail_{ts}.html", "w", encoding="utf-8") as f:
                    f.write(content)
                
                # VPS LOGGING
                try:
                    title = await page.title()
                    print(f"  [DEBUG_LOG] Page Title: {title}")
                except:
                    print(f"  [DEBUG_LOG] Could not get page title.")
                
                print(f"  [DEBUG_LOG] HTML Length: {len(content)}")
                if "Just a moment" in title or "Cloudflare" in content:
                    print(f"  [DEBUG_LOG] BLOCK DETECTED: Cloudflare Challenge")
                
            except:
                pass
            return None
        # Finally block removed: we do NOT close the page here, the caller does.

    async def _scrape_data(self, page: Page) -> dict:
        """Internal method to extract data from the page object."""
        
        # 1. Title
        title = await page.locator('h1').first.text_content()
        title = title.strip() if title else "No Title"

        # 2. Price
        price_text = "Price on request"
        try:
            # Look for price in: .text-primary.text-h6 [dir="ltr"] or similar
            price_el = page.locator('.text-primary.text-h6 [dir="ltr"]').first
            if await price_el.count() > 0:
                price_text = await price_el.text_content()
                price_text = price_text.strip()
            else:
                # Fallback: sometimes price is just in .text-primary.text-h6
                full_price = await page.locator('.text-primary.text-h6').first.text_content()
                if full_price:
                     price_text = full_price.strip()
        except:
            pass

        # 3. Description
        description = ""
        try:
            desc_el = page.locator('.announcement-details .__description').first
            if await desc_el.count() > 0:
                description = await desc_el.text_content()
                description = description.strip()
        except:
            pass

        # 4. Specifications
        specs = {}
        try:
            # Locate all spec rows: .v-row.v-row--dense inside .o-announ-specs
            # We need to iterate carefully. A robust way is to find keys (.spec-name) and their values
            spec_names = await page.locator('.o-announ-specs .spec-name').all()
            
            for name_el in spec_names:
                key = await name_el.text_content()
                key = key.strip().replace(':', '')
                
                # Value is usually the next sibling div
                # We can try to use XPath to find the following sibling
                # or get parent row and find the value col
                
                # Approach: Get the parent row of the name, then find the value div (usually .v-col-sm-9 or similar)
                parent = name_el.locator('xpath=..')
                value_el = parent.locator('.v-col-sm-9, .v-col-7').first
                
                if await value_el.count() > 0:
                    val = await value_el.text_content()
                    specs[key] = val.strip()
        except Exception as e:
            print(f"  [WARN] Spec extraction error: {e}")

        # 5. Date
        # Often inside specs, but let's check specifically for it
        if 'التاريخ' in specs:
             date = specs['التاريخ']
        else:
             date = "Unknown"

        # 6. Phone Numbers (from buttons)
        phones = []
        try:
            # Phones are in href="tel:..."
            phone_links = await page.locator('a[href^="tel:"]').all()
            for link in phone_links:
                href = await link.get_attribute('href')
                if href:
                    phone = href.replace('tel:', '').strip()
                    if phone not in phones:
                        phones.append(phone)
        except:
            pass
            
        # 7. Images
        images = []
        try:
            # Slide images usually in .swiper-slide img or picture source
            # Let's try to get large image sources
            imgs = await page.locator('.swiper-slide img.ok-img').all() 
            # Note: This might only get loaded images. 
            # Better to find: meta property="og:image"
            meta_img = await page.locator('meta[property="og:image"]').get_attribute('content')
            if meta_img:
                images.append(meta_img)
        except:
            pass

        return {
            "title": title,
            "price": price_text,
            "description": description,
            "specs": specs,
            "date": date,
            "phones": phones,
            "images": images
        }
