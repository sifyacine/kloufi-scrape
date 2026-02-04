
# === Batch size for ES bulk insert ===
BATCH_SIZE = 48  # You can adjust this value as needed

import sys
import os
import json
import asyncio
import re
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from insert2db.insert_scrape import insert_data_to_es, bulk_insert_to_es

# Add project root to path to find 'scraper', 'insert2db', and other modules
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../'))
sys.path.insert(0, PROJECT_ROOT)

from scraper.crawler.crawler_runner import crawl
from scraper.browser.fingerprint import build_context
from utils.immobilier import ImmobilierUtils

try:
    from insert2db.insert_scrape import insert_data_to_es, bulk_insert_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[ES Mock] Elasticsearch module not available. Data not saved to '{index}'")


# ========================= ZONE-AWARE CONFIGURATION =========================
# Retry and delay settings per zone for optimized performance
ZONE_SETTINGS = {
    "realtime": {
        "max_retries": 2,      # Fewer retries for speed (page 1 every 30s)
        "retry_delay": 0.5,    # Quick retry
        "delay_before_html": 1  # Minimal delay for fresh listings
    },
    "warm": {
        "max_retries": 3,
        "retry_delay": 3,
        "delay_before_html": 2
    },
    "cold": {
        "max_retries": 5,      # More retries for reliability
        "retry_delay": 5,
        "delay_before_html": 2.5  # More patience for older pages
    },
    "default": {
        "max_retries": 3,
        "retry_delay": 5,
        "delay_before_html": 2
    }
}


async def scrape_single_url(
    target_url: str, 
    proxy_manager=None, 
    max_retries: int = 3, 
    retry_delay: int = 5,
    zone: Optional[str] = None
):
    """
    Scrape a single property URL and extract all relevant data.
    
    Args:
        target_url: The property listing URL to scrape
        proxy_manager: Optional proxy manager for rotation
        max_retries: Maximum retry attempts (overridden by zone settings if zone provided)
        retry_delay: Delay between retries (overridden by zone settings if zone provided)
        zone: Zone identifier ('hot', 'warm', 'cold') for zone-aware settings
    """
    # Apply zone-specific settings if zone is provided
    zone_config = ZONE_SETTINGS.get(zone, ZONE_SETTINGS["default"])
    effective_max_retries = zone_config["max_retries"]
    effective_retry_delay = zone_config["retry_delay"]
    delay_before_html = zone_config["delay_before_html"]
    
    # Allow explicit overrides to take precedence
    if max_retries != 3:  # Non-default value passed
        effective_max_retries = max_retries
    if retry_delay != 5:  # Non-default value passed
        effective_retry_delay = retry_delay
    
    # JS for scrolling to load dynamic content (User Info)
    js_commands = [
        """
        (async () => {
            // 1. Force French via LocalStorage and Cookies
            localStorage.setItem('ok-auth-frame', JSON.stringify({ locale: 'fr' }));
            document.cookie = "ok-locale=fr; domain=.ouedkniss.com; path=/; max-age=31536000";

            // 2. Detect Arabic and Reload if necessary
            const isRTL = document.body.dir === 'rtl' || document.documentElement.dir === 'rtl';
            const isArabicLang = document.documentElement.lang === 'ar';
            const hasArabicTitle = /[\u0600-\u06FF]/.test(document.title);
            
            if (isRTL || isArabicLang || hasArabicTitle) {
                console.log("Arabic detected! Reloading with forced locale...");
                window.location.reload();
                await new Promise(r => setTimeout(r, 5000));
            }

            // 3. Perform original scroll-to-user-info logic
            let maxScrollHeight = document.body.scrollHeight;
            let scrollStep = 300;
            let currentScroll = 0;

            while (currentScroll <= maxScrollHeight) {
                let targetElement = document.getElementById('announcementUserInfo');
                if (targetElement) {
                    targetElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    break;
                }
                currentScroll += scrollStep;
                window.scrollBy(0, scrollStep);
                await new Promise(resolve => setTimeout(resolve, 500));  
                maxScrollHeight = document.body.scrollHeight;
            }

            // 4. Click Menu if found (extra safety)
            const menuBtn = document.querySelector('button[aria-label="Menu"], button[aria-label="القائمة"], button[aria-label="قائمة"]');
            if (menuBtn) {
                menuBtn.click();
                await new Promise(r => setTimeout(r, 1000));
            }

            // 5. Click FR button directly
            const frBtn = Array.from(document.querySelectorAll('button')).find(b => 
                b.textContent.trim() === 'FR' || 
                b.getAttribute('aria-label') === 'Français'
            );
            if (frBtn) {
                frBtn.click();
                await new Promise(r => setTimeout(r, 2000));
            }
        })();
        """,
        "await new Promise(resolve => setTimeout(resolve, 1000));"
    ]

    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS, 
        js_code=js_commands, 
        delay_before_return_html=delay_before_html,
        page_timeout=60000, 
        wait_until="domcontentloaded"
    )

    zone_prefix = f"[{zone.upper()}] " if zone else ""

    for attempt in range(effective_max_retries):
        proxy = None
        if proxy_manager:
            try:
                proxy = proxy_manager.get_proxy("ouedkniss.com")
            except Exception:
                print(f"{zone_prefix}No proxies available.")
        
        context = build_context()
        print(f"{zone_prefix}[{datetime.now().time()}] Scraping {target_url} | Proxy: {proxy} (Attempt {attempt+1}/{effective_max_retries})")

        # Append locale=fr to ensure French
        sep = "&" if "?" in target_url else "?"
        url_with_locale = f"{target_url}{sep}locale=fr"

        try:
            # Direct crawl using the new scraper runner
            result = await crawl(url_with_locale, proxy, context, config=config, headless=True)
            
            if result.success:
                if proxy_manager and proxy:
                    proxy_manager.report_success(proxy)
                soup = BeautifulSoup(result.html, "html.parser")

                title = ImmobilierUtils.extract_text_or_default(
                    soup, "h1.text-h5.text-capitalize")
                
                # Try the correct primary selector first
                desc_elem = soup.select_one("div.v-card-text.__description")

                if desc_elem:
                    description = desc_elem.get_text(separator="\n", strip=True)
                else:
                    description = ImmobilierUtils.extract_text_or_default(soup, "div.__description.mb-2", "")
                
                print(f"Description extracted (length: {len(description)}): {description[:100]}...")

                price_value = ImmobilierUtils.extract_text_or_default(
                    soup, "div.mt-1.line-height-2.text-primary.text-h6 div.mr-1").replace(" ", "")
                price_unit = ImmobilierUtils.extract_text_or_default(
                    soup, "div.mt-1.line-height-2.text-primary.text-h6 div.mr-1 + div")
                price_dec = ImmobilierUtils.traitement_prix(price_value, price_unit)
                
                # === NEW: Detect transaction type from title ===
                transaction_from_title = ImmobilierUtils.detect_transaction_from_title(title)

                # Get transaction from chips (existing logic)
                transaction_chips = [chip.get_text(strip=True) for chip in soup.select(
                    "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Conditions de paiement') + div .v-chip__content")]

                # Priority: title detection > chips (because title is more reliable on Ouedkniss)
                final_transaction = transaction_from_title or ", ".join(transaction_chips) or "Non spécifié"

                images = set()
                image_urls = set()
                for picture in soup.find_all("picture", class_="__slide"):
                    # print("Found picture element")

                    webp_source = picture.find(
                        "source", {"type": "image/webp"})
                    jpg_source = picture.find("source", {"type": "image/jpg"})

                    if webp_source and "srcset" in webp_source.attrs:
                        # print("Found WebP source")
                        normalized_url = ImmobilierUtils.normalize_url(webp_source["srcset"])
                        if normalized_url not in image_urls:
                            images.add(webp_source["srcset"])
                            image_urls.add(normalized_url)

                    elif jpg_source and "srcset" in jpg_source.attrs:
                        # print("Found JPG source")
                        normalized_url = ImmobilierUtils.normalize_url(jpg_source["srcset"])
                        if normalized_url not in image_urls:
                            images.add(jpg_source["srcset"])
                            image_urls.add(normalized_url)

                    else:
                        # print("No source found, checking img tag")
                        img = picture.find("img")
                        if img and "src" in img.attrs:
                            normalized_url = ImmobilierUtils.normalize_url(img["src"])
                            if normalized_url not in image_urls:
                                images.add(img["src"])
                                image_urls.add(normalized_url)

                images = list(images)
                as_photo = "Avec photo" if images else "Sans photo"

                # --- NEW & FINAL LOCATION EXTRACTION (ONLY THIS ONE!) ---
                address = ""
                wilaya = ""
                commune = ""

                # Primary strategy: parse the ok-list entries using the icon markers
                # Example structure (map marker => "Alger - El achour", home marker => "Oued Romane")
                try:
                    # Find the list container if present
                    for li in soup.select("ul.ok-list li"):
                        # Wilaya + Commune typically shown with the map marker icon
                        if li.select_one(".__prepend i.mdi-map-marker"):
                            content = li.select_one(".__content .__title .text-wrap") or li.select_one(".__content .__title")
                            if content:
                                full = content.get_text(" ", strip=True)
                                # "Alger - El achour" or "Alger -El achour" variants
                                if " - " in full:
                                    w, c = map(str.strip, full.split(" - ", 1))
                                    wilaya, commune = w, c
                                elif "-" in full:
                                    w, c = map(str.strip, full.split("-", 1))
                                    wilaya, commune = w, c
                                else:
                                    wilaya = full.strip()
                            break

                    # Address shown with the home-map-marker icon (e.g. "Oued Romane")
                    for li in soup.select("ul.ok-list li"):
                        if li.select_one(".__prepend i.mdi-home-map-marker"):
                            content = li.select_one(".__content .__title .text-wrap") or li.select_one(".__content .__title")
                            if content:
                                address = content.get_text(" ", strip=True)
                            break

                except Exception:
                    # Fallback: try some generic selectors if ok-list isn't present
                    loc = soup.select_one("div.text-wrap.text-capitalize.d-flex.flex-wrap")
                    if loc:
                        txt = loc.get_text(" ", strip=True)
                        if " - " in txt:
                            wilaya, commune = map(str.strip, txt.split(" - ", 1))
                        else:
                            wilaya = txt

                    addr = soup.select_one("div.v-list-item__content") or soup.select_one("span.__title div.text-wrap.text-capitalize")
                    if addr:
                        address = addr.get_text(" ", strip=True)

                # Preserve extracted values as-is (only trim surrounding whitespace)
                if wilaya:
                    wilaya = wilaya.strip()
                if commune:
                    commune = commune.strip()
                if address:
                    address = address.strip()

                print(f"Extracted → Wilaya: '{wilaya}' | Commune: '{commune}' | Adresse: '{address}'")
                contact_container = soup.find(id="announcementUserInfo")
                # print('Contact container:', contact_container)
                if contact_container:
                    # print('Contact container found')

                    # CHANGE: Moved the city extraction logic inside the if contact_container block and added fallbacks.
                    # This consolidates location extraction and uses more robust checks to ensure wilaya/commune are pulled
                    # even if the primary location_block failed earlier.
                    first_item = contact_container.select_one(".v-list-item")

                    if first_item:
                        # print("First item found")

                        city_div = first_item.select_one(
                            ".py-2.text-wrap.text-capitalize")

                        if city_div:
                            city_text = city_div.get_text(strip=True)

                            parts = city_text.split('-')
                            if len(parts) == 2:
                                wilaya, commune = parts
                            else:
                                wilaya, commune = city_text, ""
                        # else:
                        #    print("City information not found in the first item.")

                    # else:
                    #    print("No v-list-item found.")

                    address_element = contact_container.find(
                        "div", class_="v-list-item__content")
                    if address_element:
                        address = address_element.get_text(strip=True)
                    # else:
                    #    print('Address not found')


                # ==================== CONTACT EXTRACTION START ====================
                contact = {
                    "name": None,
                    "profile_link": None,
                    "email": [],
                    "phones": [],
                    "whatsapp": [],
                    "telegram": [],
                    "viber": []
                }

                # ----------------- 1. NAME EXTRACTION (Refined) -----------------
                # CHANGE: Added more fallback selectors for name, including within contact_container and broader classes.
                # This increases the chance of capturing the name if the primary selector misses due to page variations.
                name_elem = soup.select_one("a.ok-list-item .__title") or \
                            soup.select_one("ul.ok-list .__title") or \
                            (contact_container.select_one("a.ok-list-item .__title") if contact_container else None) or \
                            soup.select_one(".ok-list-item .__title")  # Broader fallback
                if name_elem:
                    contact["name"] = name_elem.get_text(strip=True)

                # ----------------- 2. PROFILE LINK (Dynamic Handling) -----------------
                # Since the link is dynamic, we must extract the User ID from the raw HTML/JS state
                # and construct the link manually.
                user_id = None
                
                # Regex patterns to find User ID in the raw HTML (Vue State/JSON-LD)
                # Ouedkniss often stores it as "user": { "id": 12345 } or "userId": 12345
                id_patterns = [
                    r'"userId"\s*:\s*"?(\d+)"?',
                    r'"user"\s*:\s*\{[^}]*?"id"\s*:\s*(\d+)',
                    r'store\.user\.id\s*=\s*(\d+)',
                    r'https://www\.ouedkniss\.com/membre/(\d+)',
                    r'"@id":\s*"https://www\.ouedkniss\.com/membre/(\d+)"'
                ]

                # Search in the full raw HTML first (most reliable for Vue/Nuxt apps)
                for pattern in id_patterns:
                    match = re.search(pattern, result.html)
                    if match:
                        user_id = match.group(1)
                        break
                
                if user_id:
                    contact["profile_link"] = f"https://www.ouedkniss.com/membre/{user_id}"
                
                # ----------------- 3. EMAIL -----------------
                for a in soup.select('a[href^="mailto:"]'):
                    email = a["href"].replace("mailto:", "").strip().lower()
                    if email and email not in contact["email"]:
                        contact["email"].append(email)
                
                # ----------------- 4. PHONES (Standard & Chips) -----------------
                seen_phones = set()
                
                # A. From standard tel: links
                for a in soup.select('a[href^="tel:"]'):
                    phone = re.sub(r'\D', '', a["href"])
                    if len(phone) >= 9 and phone not in seen_phones:
                        seen_phones.add(phone)
                        contact["phones"].append(phone)

                # B. From Button Text (sometimes the href is hidden but text is visible)
                for btn in soup.select('#announcementUserInfo a.v-btn, #announcementUserInfo a.ok-list-item'):
                    txt = btn.get_text(strip=True)
                    # Look for phone format in text
                    phones_in_text = re.findall(r'(?:0|\+213)\s?[567]\d{1}\s?\d{2}\s?\d{2}\s?\d{2}', txt)
                    for p in phones_in_text:
                        clean = re.sub(r'\D', '', p)
                        if len(clean) >= 9 and clean not in seen_phones:
                            seen_phones.add(clean)
                            contact["phones"].append(clean)

                # ----------------- 5. SOCIAL MEDIA -----------------
                # WhatsApp
                for a in soup.select('a[href*="wa.me"], a[href*="whatsapp.com"]'):
                    href = a.get("href", "")
                    match = re.search(r'wa\.me/(\+?\d+)', href)
                    if match:
                        clean_link = f"https://wa.me/{match.group(1)}"
                        if clean_link not in contact["whatsapp"]:
                            contact["whatsapp"].append(clean_link)
                            
                # Telegram
                for a in soup.select('a[href*="t.me"]'):
                    href = a.get("href", "")
                    match = re.search(r't\.me/(\+?\d+)', href)
                    if match:
                        clean_link = f"https://t.me/{match.group(1)}"
                        if clean_link not in contact["telegram"]:
                            contact["telegram"].append(clean_link)

                # Viber
                for a in soup.select('a[href^="viber://"]'):
                    href = a.get("href", "").strip()
                    if href and href not in contact["viber"]:
                        contact["viber"].append(href)

                # ----------------- 6. Fallback Phones from Social Links -----------------
                if not contact["phones"]:
                    for link in contact["whatsapp"] + contact["telegram"] + contact["viber"]:
                        nums = re.findall(r'(\+?\d{9,15})', link)
                        for n in nums:
                            cleaned = re.sub(r'\D', '', n)
                            # Remove 213 prefix for cleaner standardizing if preferred, or keep it
                            if len(cleaned) >= 9 and cleaned not in seen_phones:
                                seen_phones.add(cleaned)
                                contact["phones"].append(cleaned)
                
                # Clean up empty lists
                for k in ["email", "phones", "whatsapp", "telegram", "viber"]:
                    if not contact[k]:
                        contact[k] = []

                # ==================== CONTACT EXTRACTION END ====================

                property_data = {
                    "titre": title,
                    "url": target_url,
                    "site_origine": "Ouedkniss.com",
                    "categorie": "immobilier",
                    "category": "immobilier",
                    "date_crawl": datetime.now().isoformat(),
                    "prix": f"{price_value} {price_unit}" if price_value and price_unit else "",
                    "prix_unit": "DA",
                    "prix_value": price_value or "",
                    "prix_dec": price_dec if price_value else "",
                    "description": description,
                    "bien": ImmobilierUtils.convert_property_type(ImmobilierUtils.extract_text_or_default(soup, "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Type') + div")),
                    "numero": ImmobilierUtils.extract_text_or_default(soup, "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Numéro') + div"),
                    "date_depot": ImmobilierUtils.parse_date(ImmobilierUtils.extract_text_or_default(soup, "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Date') + div")),
                    "nombre_vues": ImmobilierUtils.extract_text_or_default(soup, "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Vues') + div"),
                    "nb_pieces": ImmobilierUtils.parse_float_or_none(
                        ImmobilierUtils.extract_text_or_default(
                            soup, "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Pièces') + div")
                    ),
                    "superficie": ImmobilierUtils.extract_text_or_default(soup, "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Superficie') + div span").split(" ")[0] if ImmobilierUtils.extract_text_or_default(soup, "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Superficie') + div span") != "" else "",
                    "superficie_unit": ImmobilierUtils.extract_text_or_default(soup, "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Superficie') + div span").split(" ")[-1] if ImmobilierUtils.extract_text_or_default(soup, "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Superficie') + div span") != "" else "",
                    "papiers": [chip.get_text(strip=True) for chip in soup.select("div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Papiers') + div .v-chip__content")],
                    "specifications": [chip.get_text(strip=True) for chip in soup.select("div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Spécifications') + div .v-chip__content")],
                    "images": images,
                    "etage": ImmobilierUtils.extract_text_or_default(soup, "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Etage(s)') + div"),
                    "transaction": transaction_from_title,                 
                    "payment": [chip.get_text(strip=True) for chip in soup.select("div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Conditions de paiement') + div .v-chip__content")],
                    "adresse": address or "",
                    "wilaya": wilaya.strip() if wilaya else "",
                    "commune": commune.strip() if commune else "",
                    "status": "200",
                    "contact": contact,
                    "as_photo": as_photo,
                    "date_verif": datetime.now().isoformat(),
                    "as_prix": "Avec prix" if price_value else "Sans prix"
                }

                property_data["id"] = property_data["url"] + "_" + property_data["date_crawl"]

                global batch_buffer
                property_data["id"] = property_data["url"] + "_" + property_data["date_crawl"]

                if not ImmobilierUtils.is_essential_data_empty(property_data):
                    print(json.dumps(property_data, indent=2, ensure_ascii=False))

                    # Save each listing as a separate JSON file for manual inspection
                    try:
                        ImmobilierUtils.save_listing_file(property_data)
                    except Exception as e:
                        print(f"{zone_prefix}[SAVE] Failed to write listing file: {e}")

                    # Optionally append to JSONL
                    # ImmobilierUtils.save_to_json(property_data)

                    # Add to batch buffer for bulk insert
                    batch_buffer.append(property_data)
                    if len(batch_buffer) >= BATCH_SIZE:
                        try:
                            bulk_insert_to_es(batch_buffer, "immobilier")
                            print(f"{zone_prefix}[ES] Bulk inserted {len(batch_buffer)} docs.")
                            batch_buffer.clear()
                        except Exception as e:
                            print(f"{zone_prefix}[ES] Bulk insert failed: {e}")
                    else:
                        print(f"{zone_prefix}[ES] Buffered: {len(batch_buffer)}/{BATCH_SIZE}")

                    return property_data  # Return data on success

        except Exception as e:
            print(f"{zone_prefix}Internal Crawl Error for {target_url}: {e}")
            if proxy_manager:
                if proxy:
                    proxy_manager.report_failure(proxy)
                proxy_manager.rotate("ouedkniss.com")

        # Zone-aware retry delay
        await asyncio.sleep(effective_retry_delay)

    print(f"{zone_prefix}Failed to scrape {target_url} after {effective_max_retries} attempts.")
    return None


# Test
# asyncio.run(scrape_single_url("https://www.ouedkniss.com/appartement-location-f3-oran-algerie-d48254269"))