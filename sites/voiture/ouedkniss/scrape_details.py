from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from datetime import datetime
import sys, os, json, asyncio
import re

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from scraper.crawler.crawler_runner import crawl
from scraper.browser.fingerprint import build_context
from scraper.utils.logger import get_logger
from utils.voiture import VoitureUtils

try:
    sys.path.insert(1, '../../../insert2db')
    from insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] there is a problem in saving data'{index}'")


# ------------------- [NEW] JSON saver helper -------------------
def save_to_json(data: dict, filename: str = "scraped_ouedkniss.jsonl"):
    """Append one scraped item as a JSON line to the file (creates file if missing)."""
    with open(filename, "a", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        f.write("\n")          # JSON Lines format – one object per line
# ---------------------------------------------------------------

def is_essential_data_empty(vehicle_data):
    """Check if essential fields are empty (title)."""
    return not vehicle_data["titre"]

def normalize_url(url):
    return os.path.splitext(url)[0]

async def scrape_single_url(target_url, proxy_manager=None, max_retries=3):
    """Main scraping function to scrape the data from a URL with infinite retries."""
    
    # JS for scrolling to load dynamic content (User Info)
    js_commands = [
        """
        (async () => {
            // 1. Force French via LocalStorage and Cookies
            localStorage.setItem('ok-auth-frame', JSON.stringify({ locale: 'fr' }));
            document.cookie = "ok-locale=fr; domain=.ouedkniss.com; path=/; max-age=31536000";

            // 2. Click Menu if found (extra safety)
            const menuBtn = document.querySelector('button[aria-label="Menu"], button[aria-label="القائمة"], button[aria-label="قائمة"]');
            if (menuBtn) {
                menuBtn.click();
                await new Promise(r => setTimeout(r, 1000));
            }

            // 3. Click FR button directly
            const frBtn = Array.from(document.querySelectorAll('button')).find(b => 
                b.textContent.trim() === 'FR' || 
                b.getAttribute('aria-label') === 'Français'
            );
            if (frBtn) {
                frBtn.click();
                await new Promise(r => setTimeout(r, 2000));
            }
            
            // 4. Perform original scroll-to-user-info logic
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

            if (!document.getElementById('announcementUserInfo')) {
                console.log('Element not found after scrolling to the bottom of the page');
            }
        })();
        """
    ]

    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS, 
        js_code=js_commands, 
        delay_before_return_html=5,
        page_timeout=60000, 
        wait_until="domcontentloaded"
    )

    for attempt in range(max_retries):
        proxy = None
        if proxy_manager:
            try:
                proxy = proxy_manager.get_proxy("ouedkniss.com")
            except Exception:
                pass # No proxies, try direct
        
        context = build_context()
        print(f"Scraping {target_url} | Proxy: {proxy} (Attempt {attempt+1}/{max_retries})")

        # Append locale=fr to ensure French
        sep = "&" if "?" in target_url else "?"
        url_with_locale = f"{target_url}{sep}locale=fr"

        try:
            result = await crawl(url_with_locale, proxy, context, config=config, headless=True)
            
            if result.success:
                if proxy_manager and proxy:
                    proxy_manager.report_success(proxy)
                
                soup = BeautifulSoup(result.html, "html.parser")
                
                # Extract data
                title = VoitureUtils.extract_text(soup, "h1.text-h5.text-capitalize")
                
                # Description
                desc_elem = soup.select_one("div.__description") or soup.select_one("div.v-card-text.__description")
                if desc_elem:
                    description = desc_elem.get_text(separator="\n", strip=True)
                else:
                    description = VoitureUtils.extract_text(soup, "div.__description.mb-2")
                
                # Price extraction
                price_section = soup.select_one("div.mt-1.line-height-2.text-primary.text-h6")
                category_section = soup.select_one("li.v-breadcrumbs-item")

                price = ""
                price_value = ""
                price_unit = ""
                price_condition = ""
                price_decimal = 0

                if price_section:
                    raw_val = VoitureUtils.extract_text(price_section, "div.mr-1")
                    raw_unit = VoitureUtils.extract_text(price_section, "div.mr-1 + div")
                    price_condition = VoitureUtils.extract_text(price_section, "span.mx-1")
                    
                    # Use centralized parser
                    price_disp, price_value, price_decimal, price_unit = VoitureUtils.parse_price(raw_val, raw_unit)
                    
                    # Reconstruct price string with condition if present
                    price = f"{price_disp} {price_condition}".strip()
                
                # Images
                images = set()
                image_urls = set()
                for picture in soup.find_all("picture", class_="__slide"):
                    webp_source = picture.find("source", {"type": "image/webp"})
                    jpg_source = picture.find("source", {"type": "image/jpg"})
                    
                    if webp_source and "srcset" in webp_source.attrs:
                        normalized_url = normalize_url(webp_source["srcset"])
                        if normalized_url not in image_urls:
                            images.add(webp_source["srcset"])
                            image_urls.add(normalized_url)
                    elif jpg_source and "srcset" in jpg_source.attrs:
                        normalized_url = normalize_url(jpg_source["srcset"])
                        if normalized_url not in image_urls:
                            images.add(jpg_source["srcset"])
                            image_urls.add(normalized_url)
                    else:
                        img = picture.find("img")
                        if img and "src" in img.attrs:
                            normalized_url = normalize_url(img["src"])
                            if normalized_url not in image_urls:
                                images.add(img["src"])
                                image_urls.add(normalized_url)

                images = list(images)
                as_photo = "Avec photo" if images else "Sans photo"

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

                contact_container = soup.select_one("#announcementUserInfo")
                name_elem = soup.select_one("a.ok-list-item .__title") or \
                            soup.select_one("ul.ok-list .__title") or \
                            (contact_container.select_one("a.ok-list-item .__title") if contact_container else None) or \
                            soup.select_one(".ok-list-item .__title") or \
                            soup.select_one(".__title")
                
                if name_elem:
                    contact["name"] = name_elem.get_text(strip=True)

                user_id = None
                id_patterns = [
                    r'"userId"\s*:\s*"?(\d+)"?',
                    r'"user"\s*:\s*\{[^}]*?"id"\s*:\s*(\d+)',
                    r'store\.user\.id\s*=\s*(\d+)',
                    r'https://www\.ouedkniss\.com/membre/(\d+)',
                    r'"@id":\s*"https://www\.ouedkniss\.com/membre/(\d+)"'
                ]

                for pattern in id_patterns:
                    match = re.search(pattern, result.html)
                    if match:
                        user_id = match.group(1)
                        break
                
                if user_id:
                    contact["profile_link"] = f"https://www.ouedkniss.com/membre/{user_id}"
                
                for a in soup.select('a[href^="mailto:"]'):
                    email = a["href"].replace("mailto:", "").strip().lower()
                    if email and email not in contact["email"]:
                        contact["email"].append(email)
                
                seen_phones = set()
                for a in soup.select('a[href^="tel:"]'):
                    phone = re.sub(r'\D', '', a["href"])
                    if len(phone) >= 9 and phone not in seen_phones:
                        seen_phones.add(phone)
                        contact["phones"].append(phone)

                for btn in soup.select('#announcementUserInfo a.v-btn, #announcementUserInfo a.ok-list-item'):
                    txt = btn.get_text(strip=True)
                    phones_in_text = re.findall(r'(?:0|\+213)\s?[567]\d{1}\s?\d{2}\s?\d{2}\s?\d{2}', txt)
                    for p in phones_in_text:
                        clean = re.sub(r'\D', '', p)
                        if len(clean) >= 9 and clean not in seen_phones:
                            seen_phones.add(clean)
                            contact["phones"].append(clean)

                for a in soup.select('a[href*="wa.me"], a[href*="whatsapp.com"]'):
                    href = a.get("href", "")
                    match = re.search(r'wa\.me/(\+?\d+)', href)
                    if match:
                        clean_link = f"https://wa.me/{match.group(1)}"
                        if clean_link not in contact["whatsapp"]:
                            contact["whatsapp"].append(clean_link)
                            
                for a in soup.select('a[href*="t.me"]'):
                    href = a.get("href", "")
                    match = re.search(r't\.me/(\+?\d+)', href)
                    if match:
                        clean_link = f"https://t.me/{match.group(1)}"
                        if clean_link not in contact["telegram"]:
                            contact["telegram"].append(clean_link)

                for a in soup.select('a[href^="viber://"]'):
                    href = a.get("href", "").strip()
                    if href and href not in contact["viber"]:
                        contact["viber"].append(href)

                if not contact["phones"]:
                    for link in contact["whatsapp"] + contact["telegram"] + contact["viber"]:
                        nums = re.findall(r'(\+?\d{9,15})', link)
                        for n in nums:
                            cleaned = re.sub(r'\D', '', n)
                            if len(cleaned) >= 9 and cleaned not in seen_phones:
                                seen_phones.add(cleaned)
                                contact["phones"].append(cleaned)
                
                # ==================== CONTACT EXTRACTION END ====================

                # Location Extraction
                address = ""
                wilaya = ""
                commune = ""

                try:
                    for li in soup.select("ul.ok-list li"):
                        if li.select_one(".__prepend i.mdi-map-marker"):
                            content = li.select_one(".__content .__title .text-wrap") or li.select_one(".__content .__title")
                            if content:
                                full = content.get_text(" ", strip=True)
                                if " - " in full:
                                    w, c = map(str.strip, full.split(" - ", 1))
                                    wilaya, commune = w, c
                                elif "-" in full:
                                    w, c = map(str.strip, full.split("-", 1))
                                    wilaya, commune = w, c
                                else:
                                    wilaya = full.strip()
                            break

                    for li in soup.select("ul.ok-list li"):
                        if li.select_one(".__prepend i.mdi-home-map-marker"):
                            content = li.select_one(".__content .__title .text-wrap") or li.select_one(".__content .__title")
                            if content:
                                address = content.get_text(" ", strip=True)
                            break

                except Exception:
                    if contact_container:
                        first_item = contact_container.select_one(".v-list-item")
                        if first_item:
                            city_div = first_item.select_one(".py-2.text-wrap.text-capitalize")
                            if city_div:
                                city_text = city_div.get_text(strip=True)
                                parts = city_text.split('-')
                                if len(parts) == 2:
                                    wilaya, commune = parts
                                else:
                                    wilaya, commune = city_text, ""
                        
                        address_element = contact_container.find("div", class_="v-list-item__content")
                        if address_element:
                            address = address_element.get_text(strip=True)

                if wilaya: wilaya = wilaya.strip()
                if commune: commune = commune.strip()
                if address: address = address.strip()

                print(f"Extracted → Wilaya: '{wilaya}' | Commune: '{commune}' | Adresse: '{address}'")

                options = [chip.get_text(strip=True) for chip in soup.select("div.spec-name:-soup-contains('Options') + div v-chip")]

                vehicle_views = VoitureUtils.extract_text(soup, "div.spec-name:-soup-contains('Vues') + div")
                vehicle_number = VoitureUtils.extract_text(soup, "div.spec-name:-soup-contains('Numéro') + div")
                vehicle_date = VoitureUtils.extract_text(soup, "div.spec-name:-soup-contains('Date') + div")
                vehicle_brand = VoitureUtils.extract_text(soup, "div.spec-name:-soup-contains('Marque') + div")
                vehicle_model = VoitureUtils.extract_text(soup, "div.spec-name:-soup-contains('Modèle') + div")
                vehicle_finish = VoitureUtils.extract_text(soup, "div.spec-name:-soup-contains('Finition') + div")
                vehicle_year = VoitureUtils.extract_text(soup, "div.spec-name:-soup-contains('Année') + div")
                kms_section = soup.select_one("div.spec-name:-soup-contains('Kilométrage') + div")
                vehicle_motor = VoitureUtils.extract_text(soup, "div.spec-name:-soup-contains('Moteur') + div")
                papers = VoitureUtils.extract_text(soup, "div.spec-name:-soup-contains('Papiers') + div")
                vehicle_color = VoitureUtils.extract_text(soup, "div.spec-name:-soup-contains('Couleur') + div")
                energy = VoitureUtils.extract_text(soup, "div.spec-name:-soup-contains('Energie') + div")
                transmission = VoitureUtils.extract_text(soup, "div.spec-name:-soup-contains('Boite') + div") or \
                               VoitureUtils.extract_text(soup, "div.spec-name:-soup-contains('Transmission') + div")
                
                kms_value, kms_unit = VoitureUtils.normalize_mileage(kms_section.get_text(strip=True) if kms_section else "")

                vehicle_data = {
                    "titre": title,
                    "description": description,
                    "numero": vehicle_number,
                    "nombre_vues": vehicle_views,
                    "date_depot": VoitureUtils.parse_date(vehicle_date),
                    "site_origine": "Ouedkniss.com",
                    "categorie": category_section.get_text(strip=True) if category_section else "",
                    "category": category_section.get_text(strip=True) if category_section else "",
                    "images": images,
                    'url': target_url,
                    "annee": vehicle_year,
                    "marque": vehicle_brand,
                    "model": vehicle_model,
                    "finition": vehicle_finish,
                    "prix": price,
                    "prix_unit": price_unit,
                    "prix_value": price_value,
                    "prix_condition": price_condition,
                    "prix_dec": price_decimal,
                    "adresse": address,
                    "wilaya": wilaya,
                    "commune": commune,
                    "etat": "Occasion",
                    "date_crawl": datetime.now().isoformat(),
                    "status": "200",
                    "as_photo": as_photo,
                    "as_prix": "Avec prix" if price else "Sans prix",
                    "km": kms_value,
                    "km_unit": kms_unit,
                    "moteur": vehicle_motor,
                    "papers": papers,
                    "couleur": vehicle_color,
                    "options": options,
                    "energie": VoitureUtils.normalize_fuel(energy),
                    "transmission": VoitureUtils.normalize_transmission(transmission),
                    "contact": contact,

                }

                if not is_essential_data_empty(vehicle_data):
                    print(json.dumps(vehicle_data, indent=2, ensure_ascii=False))

                    # Save to JSONL
                    save_to_json(vehicle_data)

                    insert_data_to_es(vehicle_data, index_name="voiture")
                    return
                else:
                    print("Essential fields are empty. Retrying...")

        except Exception as e:
            print(f"Crawler engine error for {target_url}: {e}")
            if proxy_manager and proxy:
                proxy_manager.report_failure(proxy)
                proxy_manager.rotate("ouedkniss.com")

        # Retry delay
        await asyncio.sleep(2)
        
    print(f"Failed to scrape {target_url} after {max_retries} attempts.")

# Run the function (uncomment to test)
# asyncio.run(scrape_single_url("https://www.ouedkniss.com/voitures-suzuki-maruti-800-2011-bab-el-oued-alger-algerie-d47059732"))
