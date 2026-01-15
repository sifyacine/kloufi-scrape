from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from datetime import datetime
import sys, os, json, asyncio

try:
    sys.path.insert(1, '../../global')
    from insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] there is a problem in saving data'{index}'")
import re


# ------------------- [NEW] JSON saver helper -------------------
def save_to_json(data: dict, filename: str = "scraped_ouedkniss.jsonl"):
    """Append one scraped item as a JSON line to the file (creates file if missing)."""
    with open(filename, "a", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        f.write("\n")          # JSON Lines format – one object per line
# ---------------------------------------------------------------


def normalize_energie(value: str) -> str:
        """
        Normalize fuel type/energy source.
        """
        if not value:
            return ""
            
        mapping = {
            # Essence
            "Essence": "Essence",
            "Petrol": "Essence",
            "Gasoline": "Essence",
            "Essence, Compatible E-10": "Essence",

            # Diesel
            "Diesel": "Diesel",
            "Diesel, Compatible E-10": "Diesel",

            # GPL
            "GPL": "GPL",
            "GPL, Compatible E-10": "GPL",
            "Essence / GPL": "GPL",

            # Electrique
            "Electrique": "Electrique",

            # Hybride
            "Hybride": "Hybride",
            "Hybrid": "Hybride",
            "Hybrid (gasoline/electric)": "Hybride",
            "Hybride (essence/électrique)": "Hybride",
            "Hybride (diesel/électrique)": "Hybride",

            # Hybride Rechargeable
            "Hybride (essence/électrique), Hybride rechargeable": "Hybride Rechargeable",
            "Hybride (essence/électrique), Compatible E-10, Hybride rechargeable": "Hybride Rechargeable",

            # Multi-énergie
            "Essence / Hybride": "Multi-énergie",
            "Essence / Hybride / Electrique": "Multi-énergie",

            # Unknown entries mapped as requested
            "energie-1": "Essence",
            "energie-2": "Diesel",
            "energie-3": "GPL",
        }

        return mapping.get(value.strip(), "Multi-énergie")
    
def normalize_transmission(value: str) -> str:
        """
        Normalize transmission type.
        """
        if not value:
            return ""

        val_upper = value.strip().upper()
        
        # Checking for specific keywords
        if val_upper in ["AT", "DCT", "CVT", "E-CVT", "DHT", "AMT", "TCT", "E-CVT+AT", "ISR"]:
            return "Automatique"
            
        if "SEMI" in val_upper:
            return "Semi-Automatique"
            
        if "AUTOMATIQUE" in val_upper or "AUTOMATIC" in val_upper:
            return "Automatique"
            
        if "MANUELLE" in val_upper or "MANUAL" in val_upper or "MÉCANIQUE" in val_upper or "MT" == val_upper:
            return "Manuelle"
            
        return value.strip()

def traitement_prix(prix_dec, prix_unit):
    """Convert price to its final value if unit is in millions or billions."""
    if prix_dec and prix_unit:
        conversion = {"Millions": 10000, "Milliards": 10000000}
        return float(prix_dec) * conversion.get(prix_unit, 1)
    return 0

def extract_text_or_default(soup, selector, default=""):
    """Extract text from a given selector or return a default value."""
    element = soup.select_one(selector)
    if element:
        return element.get_text(strip=True)
    else:
        print(f"Element not found for selector: {selector}")
        return default

def parse_date(date_str):
    """Try to parse a date string into a datetime object."""
    if date_str and date_str != "Date":
        try:
            return datetime.strptime(date_str, '%d/%m/%Y %H:%M:%S').isoformat()
        except ValueError:
            print(f"Invalid date format: {date_str}")
            return ""
    return ""

def is_essential_data_empty(vehicle_data):
    """Check if essential fields are empty (title)."""
    return not vehicle_data["titre"]

def normalize_url(url):
    return os.path.splitext(url)[0]




async def scrape_single_url(target_url):
    """Main scraping function to scrape the data from a URL with infinite retries."""
    url = f"https://proxyium.com/"
    print(f"Scraping URL: {target_url}")

    browser_config = BrowserConfig(headless=True, text_mode=False, browser_type="chromium")

    js_commands = [
        "await new Promise(resolve => setTimeout(resolve, 10000));",
        # Force French locale in LocalStorage and Cookies (Best Effort)
        "localStorage.setItem('ok-auth-frame', JSON.stringify({ locale: 'fr' }));",
        "document.cookie = 'ok-locale=fr; path=/; domain=.ouedkniss.com';",
        # Click the 'Autoriser' button to accept cookies
        "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",
        # Force French language via URL
        f"document.getElementById('unique-form-control').value = '{target_url}{'&' if '?' in target_url else '?'}lang=fr';",
        # Submit the form if required
        "document.querySelector('#web_proxy_form').submit();",
        "await new Promise(resolve => setTimeout(resolve, 5000));",
        # Click the 'Autoriser' button again if it appears
        "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",
        """
        (async () => {
            let maxScrollHeight = document.body.scrollHeight;
            let scrollStep = 300;
            let currentScroll = 0;

            while (currentScroll <= maxScrollHeight) {
                let targetElement = document.getElementById('announcementUserInfo');
                if (targetElement) {
                    targetElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    console.log('Element found and scrolled into view');
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
        """,
        "await new Promise(resolve => setTimeout(resolve, 5000));",
    ]

    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS, 
        js_code=js_commands, 
        delay_before_return_html=30,
        page_timeout=120000, 
        wait_until="domcontentloaded"  # Avoid networkidle timeouts on initial proxy load
    )

    attempt = 1
    while True:
        print(f"--- Attempt #{attempt} for {target_url} ---")
        async with AsyncWebCrawler(verbose=True, config=browser_config) as crawler:
            try:
                result = await crawler.arun(url=url, config=config, timeout=120_000)
            except Exception as e:
                print(f"Crawler engine error for {target_url}: {e}")
                result = None

            if result and result.success:
                print(f"Successfully scraped {target_url} on attempt {attempt + 1}!")
                soup = BeautifulSoup(result.html, "html.parser")
                
                # Extract data
                title = extract_text_or_default(soup, "h1.text-h5.text-capitalize")
                # Description: try multiple selectors and preserve line breaks
                desc_elem = soup.select_one("div.__description") or soup.select_one("div.v-card-text.__description")
                if desc_elem:
                    # preserve paragraphs/newlines when present
                    description = desc_elem.get_text(separator="\n", strip=True)
                else:
                    # fallback to previous selector for compatibility
                    description = extract_text_or_default(soup, "div.__description.mb-2", "")
                price_section = soup.select_one("div.mt-1.line-height-2.text-primary.text-h6")
                category_section = soup.select_one("li.v-breadcrumbs-item")

                price = ""
                price_value = ""
                price_unit = ""
                price_condition = ""

                if price_section:
                    price_value = extract_text_or_default(price_section, "div.mr-1").replace(" ", "")
                    price_unit = extract_text_or_default(price_section, "div.mr-1 + div")
                    price_condition = extract_text_or_default(price_section, "span.mx-1")
                    price = " ".join(filter(None, [price_value, price_unit, price_condition]))

                images = set()
                image_urls = set()
                for picture in soup.find_all("picture", class_="__slide"):
                    print("Found picture element")
                    
                    # Try to find the WebP and JPG sources
                    webp_source = picture.find("source", {"type": "image/webp"})
                    jpg_source = picture.find("source", {"type": "image/jpg"})
                    
                    # Check if the WebP source exists and extract the URL
                    if webp_source and "srcset" in webp_source.attrs:
                        print("Found WebP source")
                        normalized_url = normalize_url(webp_source["srcset"])
                        # Only add if the base URL hasn't been added before
                        if normalized_url not in image_urls:
                            images.add(webp_source["srcset"])
                            image_urls.add(normalized_url)

                    # Fallback to JPG source if WebP is not available
                    elif jpg_source and "srcset" in jpg_source.attrs:
                        print("Found JPG source")
                        normalized_url = normalize_url(jpg_source["srcset"])
                        # Only add if the base URL hasn't been added before
                        if normalized_url not in image_urls:
                            images.add(jpg_source["srcset"])
                            image_urls.add(normalized_url)

                    else:
                        # If neither source exists, check the img tag for the src URL
                        print("No source found, checking img tag")
                        img = picture.find("img")
                        if img and "src" in img.attrs:
                            normalized_url = normalize_url(img["src"])
                            # Only add if the base URL hasn't been added before
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

                # ----------------- 1. NAME EXTRACTION (Refined) -----------------
                contact_container = soup.select_one("#announcementUserInfo")
                # Refined selectors as per reference
                name_elem = soup.select_one("a.ok-list-item .__title") or \
                            soup.select_one("ul.ok-list .__title") or \
                            (contact_container.select_one("a.ok-list-item .__title") if contact_container else None) or \
                            soup.select_one(".ok-list-item .__title") or \
                            soup.select_one(".__title")
                
                if name_elem:
                    contact["name"] = name_elem.get_text(strip=True)

                # ----------------- 2. PROFILE LINK (Dynamic Handling) -----------------
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

                # B. From Button Text (Regex from reference)
                for btn in soup.select('#announcementUserInfo a.v-btn, #announcementUserInfo a.ok-list-item'):
                    txt = btn.get_text(strip=True)
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

                # --- NEW & FINAL LOCATION EXTRACTION (Refined icon priority) ---
                address = ""
                wilaya = ""
                commune = ""

                # Primary: parse the ok-list entries using icon markers (Reference pattern)
                try:
                    # Wilaya + Commune typically shown with the map marker icon
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

                    # Address shown with the home-map-marker icon
                    for li in soup.select("ul.ok-list li"):
                        if li.select_one(".__prepend i.mdi-home-map-marker"):
                            content = li.select_one(".__content .__title .text-wrap") or li.select_one(".__content .__title")
                            if content:
                                address = content.get_text(" ", strip=True)
                            break

                except Exception:
                    # Fallback to older container-based logic if icon list fails
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

                if wilaya:
                    wilaya = wilaya.strip()
                if commune:
                    commune = commune.strip()
                if address:
                    address = address.strip()

                print(f"Extracted → Wilaya: '{wilaya}' | Commune: '{commune}' | Adresse: '{address}'")

                print(f"Extracted → Wilaya: '{wilaya}' | Commune: '{commune}' | Adresse: '{address}'")

                options = [chip.get_text(strip=True) for chip in soup.select("div.spec-name:-soup-contains('Options') + div v-chip")]

                vehicle_views = extract_text_or_default(soup, "div.spec-name:-soup-contains('Vues') + div")
                vehicle_number = extract_text_or_default(soup, "div.spec-name:-soup-contains('Numéro') + div")
                vehicle_date = extract_text_or_default(soup, "div.spec-name:-soup-contains('Date') + div")
                vehicle_brand = extract_text_or_default(soup, "div.spec-name:-soup-contains('Marque') + div")
                vehicle_model = extract_text_or_default(soup, "div.spec-name:-soup-contains('Modèle') + div")
                vehicle_finish = extract_text_or_default(soup, "div.spec-name:-soup-contains('Finition') + div")
                vehicle_year = extract_text_or_default(soup, "div.spec-name:-soup-contains('Année') + div")
                kms_section = soup.select_one("div.spec-name:-soup-contains('Kilométrage') + div")
                vehicle_motor = extract_text_or_default(soup, "div.spec-name:-soup-contains('Moteur') + div")
                papers = extract_text_or_default(soup, "div.spec-name:-soup-contains('Papiers') + div")
                vehicle_color = extract_text_or_default(soup, "div.spec-name:-soup-contains('Couleur') + div")
                energy = extract_text_or_default(soup, "div.spec-name:-soup-contains('Energie') + div")
                transmission = extract_text_or_default(soup, "div.spec-name:-soup-contains('Boite') + div") or \
                               extract_text_or_default(soup, "div.spec-name:-soup-contains('Transmission') + div")
                
                kms_value, kms_unit = "", ""
                if kms_section:
                    kms = kms_section.get_text(strip=True)
                    if " " in kms:
                        kms_value = kms.split(" ")[-1]
                        kms_unit = kms.split(" ")[0]
                    else:
                        kms_value = ''.join(filter(str.isdigit, kms))
                        kms_unit = ''.join(filter(str.isalpha, kms))

                vehicle_data = {
                    "titre": title,
                    "description": description,
                    "numero": vehicle_number,
                    "nombre_vues": vehicle_views,
                    "date_depot": parse_date(vehicle_date) if vehicle_date else "",
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
                    "prix_unit": "DA",
                    "prix_value": price_value,
                    "prix_condition": price_condition,
                    "prix_dec": traitement_prix(price_value, price_unit) if price_value and price_unit else 0,
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
                    "energie": normalize_energie(energy),
                    "transmission": normalize_transmission(transmission),
                    "contact": contact,

                }

                if not is_essential_data_empty(vehicle_data):
                    print(json.dumps(vehicle_data, indent=2))



                    # Save to JSONL (Back in use)
                    save_to_json(vehicle_data)

                    insert_data_to_es(vehicle_data, index_name="voiture")
                    return
                else:
                    print("Essential fields are empty. Retrying...")

        # If reaching here, it means success=False or essential data empty
        print(f"Retrying {target_url} in 12 seconds...")
        await asyncio.sleep(12)
        attempt += 1

# Run the function (uncomment to test)
# asyncio.run(scrape_single_url("https://www.ouedkniss.com/voitures-suzuki-maruti-800-2011-bab-el-oued-alger-algerie-d47059732"))
