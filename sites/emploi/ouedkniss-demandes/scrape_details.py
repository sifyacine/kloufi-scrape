from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from datetime import datetime
import os
import json
import asyncio
import sys
sys.path.insert(1, '../../../insert2db')
import re
from insert_scrape import insert_data_to_es

def traitement_prix(prix_dec, prix_unit):
    conversion = {"Millions": 10000, "Milliards": 10000000}
    return float(prix_dec) * conversion.get(prix_unit, 1) if prix_dec and prix_unit else 0


def extract_text_or_default(soup, selector, default=""):
    element = soup.select_one(selector)
    return element.get_text(strip=True) if element else default


def parse_date(date_str):
    try:
        return datetime.strptime(date_str, '%d/%m/%Y %H:%M:%S').isoformat()
    except ValueError:
        return ""


def is_essential_data_empty(data):
    return not data.get("titre")


def normalize_url(url):
    return os.path.splitext(url)[0]

def normalize_diplome(diplome):
    # 'niveau secondaire',
    # 'niveau terminal',
    # 'baccalauréat',
    # 'ts bac +2',
    # 'licence (lmd), bac + 3',
    # 'master 1, licence  bac + 4',
    # 'master 2, ingéniorat, bac + 5',
    # 'magistère bac + 7',
    # 'doctorat',
    # 'non diplômante',
    # 'formation professionnelle',
    # 'universitaire sans diplôme',
    # 'certification'
    if diplome == "niveau secondaire": return "Diplome de collège"
    elif diplome == "baccalauréat": return "Bac"
    elif diplome == "bac": return "Bac"
    elif diplome == "bac +2": return "Diplome universitaire"
    elif diplome == "licence": return "Diplome universitaire"
    elif diplome == "bac + 3": return "Diplome universitaire"
    elif diplome == "bac+3": return "Diplome universitaire"
    elif diplome == "master 1": return "Master"
    elif diplome == "licence bac + 4": return "Diplome universitaire"
    elif diplome == "baster 2": return "Master"
    elif diplome == "ingéniorat": return "Diplome universitaire"
    elif diplome == "bac + 5": return "Diplome universitaire"
    elif diplome == "magistère bac + 7": return "Diplome universitaire"
    elif diplome == "certification": return "Diplôme professionnel / téchnique"
    elif diplome == "formation professionnelle": return "Diplôme professionnel / téchnique"
    elif diplome == "ts bac +2 | Formation Professionnelle": return "Diplôme professionnel / téchnique"
    elif diplome == "universitaire sans diplôme": return "Diplôme professionnel / téchnique"
    elif diplome == "doctorat": return "Doctorat"
    elif diplome == "licence (lmd), bac + 3": return "Diplome universitaire"
    elif diplome == "master 1, licence  bac + 4": return "Diplome universitaire"
    elif diplome == "master 2, ingéniorat, bac + 5": return "Diplome universitaire"
    elif diplome == "non diplômante": return None
    elif diplome == "sans diplôme": return None
    elif diplome == "sans diplome": return None
    else: return diplome





async def scrape_single_url(target_url, max_retries=3, retry_delay=5):
    url = "https://proxyium.com/"
    browser_config = BrowserConfig(
        headless=True, text_mode=False, browser_type="chromium")
    js_commands = [
        # Wait for the page to load or settle
        "await new Promise(resolve => setTimeout(resolve, 5000));",
        # Click the 'Autoriser' button to accept cookies
        "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",
        # Assuming you're filling a form with 'target_url'
        f"document.getElementById('unique-form-control').value = '{target_url}';",
        # Submit the form if required
        "document.querySelector('#web_proxy_form').submit();",
        # Wait for a few seconds to let the page settle
        "await new Promise(resolve => setTimeout(resolve, 3000));",
        # Click the 'Autoriser' button to accept cookies
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
        """
    ]
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS, js_code=js_commands, delay_before_return_html=30)

    for attempt in range(max_retries):
        async with AsyncWebCrawler(verbose=True, config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=config)
            if result.success:
                soup = BeautifulSoup(result.html, "html.parser")

                title = extract_text_or_default(
                    soup, "h1.text-h5.text-capitalize")
                # Description: try multiple selectors and preserve line breaks
                desc_elem = soup.select_one("div.__description") or soup.select_one("div.v-card-text.__description")
                if desc_elem:
                    # preserve paragraphs/newlines when present
                    description = desc_elem.get_text(separator="\n", strip=True)
                else:
                    # fallback to previous selector for compatibility
                    description = extract_text_or_default(soup, "div.__description.mb-2", "")

                price_value = extract_text_or_default(
                    soup, "div.mt-1.line-height-2.text-primary.text-h6 div.mr-1").replace(" ", "")
                price_unit = extract_text_or_default(
                    soup, "div.mt-1.line-height-2.text-primary.text-h6 div.mr-1 + div")
                price_dec = traitement_prix(price_value, price_unit)
                niveau_poste_normalized = []

                images = set()
                image_urls = set()
                for picture in soup.find_all("picture", class_="__slide"):
                    print("Found picture element")

                    # Try to find the WebP and JPG sources
                    webp_source = picture.find(
                        "source", {"type": "image/webp"})
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

                address, wilaya, commune = "", "", ""
                contact_container = soup.find(id="announcementUserInfo")
                print('Contact container:', contact_container)
                if contact_container:
                    print('Contact container found')

                    first_item = contact_container.select_one(".v-list-item")

                    if first_item:
                        print("First item found")

                        city_div = first_item.select_one(
                            ".py-2.text-wrap.text-capitalize")

                        if city_div:
                            city_text = city_div.get_text(strip=True)

                            parts = city_text.split('-')
                            if len(parts) == 2:
                                wilaya, commune = parts
                            else:
                                wilaya, commune = city_text, ""
                        else:
                            print("City information not found in the first item.")

                    else:
                        print("No v-list-item found.")

                    address_element = contact_container.find(
                        "div", class_="v-list-item__content")
                    if address_element:
                        address = address_element.get_text(strip=True)
                    else:
                        print('Address not found')
                        
                niveau = extract_text_or_default(
                    soup,
                    'div.v-col-sm-3.v-col-5.spec-name:-soup-contains("Niveau d\'éducation") + div span'
                ).split(" ")[0] if extract_text_or_default(
                    soup,
                    'div.v-col-sm-3.v-col-5.spec-name:-soup-contains("Niveau d\'éducation") + div span'
                ) != "" else ""
                employeur = extract_text_or_default(
                    soup,
                    'div.v-col-sm-3.v-col-5.spec-name:-soup-contains("Societé") + div'
                )
                vehicle = extract_text_or_default(
                    soup,
                    'div.v-col-sm-3.v-col-5.spec-name:-soup-contains("Véhicule") + div'
                )
                
                if "plus ..." in address or "plus ..." in wilaya:
                    address = "Worldwide"
                    wilaya = "Worldwide"
                    commune = "Worldwide"

                emploi_data = {
                    "titre": title,
                    "url": target_url,
                    "site_origine": "Ouedkniss.com",
                    "categorie": "emploi",
                    "category": "emploi",
                    "date_crawl": datetime.now().isoformat(),
                    'niveau': niveau,
                    "numero": extract_text_or_default(soup, "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Numéro') + div"),
                    "date_depot": parse_date(extract_text_or_default(soup, "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Date') + div")),
                    "nombre_vues": extract_text_or_default(soup, "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Vues') + div"),                    "date_depot": parse_date(extract_text_or_default(soup, "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Date') + div")),
                    'transaction': "Demandes",
                    # 'contrat': contrat,
                    # 'diplome': diplome_list_normalized,
                    # 'diplome_src': diplome_list,
                    # 'domaine': domaine,
                    'description': description,
                    'employeur': employeur,
                    # 'poste': poste,
                    "adresse": address or "",
                    "wilaya": wilaya.strip() if wilaya else "",
                    "commune": commune.strip() if commune else "",
                    'status': 200,
                    'date_verif': datetime.now().isoformat(),
                    'images': images,
                    'as_photo': as_photo,
                    'as_prix': "Avec prix" if price_dec else "Sans prix",
                    'vehicle': "True" if vehicle == "Oui" else "False",
                    "prix": f"{price_value} {price_unit}" if price_value and price_unit else "",
                    "prix_unit": "DA",
                    "prix_value": price_value or "",
                    "prix_dec": price_dec if price_value else "",
                    "as_prix": "Avec prix" if price_dec else "Sans prix",
                    "contact": contact,

                }

                if not is_essential_data_empty(emploi_data):
                    print(json.dumps(emploi_data, indent=2))
                    insert_data_to_es(emploi_data, index_name="emploi")
                    return

        await asyncio.sleep(retry_delay)

    print(f"Failed to scrape {target_url} after {max_retries} attempts.")

# Test case
# asyncio.run(scrape_single_url("https://www.ouedkniss.com/appartement-vente-f4-alger-ain-taya-algerie-d45777655"))
