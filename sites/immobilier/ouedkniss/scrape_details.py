from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from datetime import datetime
import sys
import os
import json
import asyncio
import re

"""
Detail-page scraper for Ouedkniss immobilier via Proxyium.

This module is intentionally verbose and heavily commented to make
debugging easier for developers:
  - Each crawl attempt logs the target URL, zone (HOT/WARM/COLD), and attempt number.
  - Key extraction steps (description, price, location, contact, images) print
    short summaries so you can quickly see what worked and where data is missing.
"""

#
# LOCAL DEBUG OUTPUT TO `junk_test/`
# ----------------------------------
# Set this flag to False once you're confident in the scraper, or whenever you
# don't want to generate local debug JSON files under the `junk_test` folder.
# When True:
#   - One JSONL line per listing is appended to `junk_test/scraped_ouedkniss.jsonl`
#   - One pretty JSON file per listing is created in `junk_test/`
#
DEBUG_SAVE_LOCAL = True

try:
    # Ensure project root is on sys.path, then import the shared insert2db module.
    from pathlib import Path

    ROOT_DIR = Path(__file__).resolve().parents[2]
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))

    from insert2db.insert_scrape import insert_data_to_es
except ImportError:

    def insert_data_to_es(data, index):
        print(f"[Mock] there is a problem in saving data '{index}'")

try:
    # Shared real-estate helpers (normalization, saving, etc.).
    from utils.immobilier import ImmobilierUtils
except ImportError:
    ImmobilierUtils = None


# ------------------- JSON saver helper -------------------
def save_to_json(data: dict, filename: str = "scraped_ouedkniss.jsonl"):
    """
    Append one scraped item as a JSON line to the file (creates file if missing).

    This is mainly for debugging / offline inspection alongside Elasticsearch.
    """
    # Prefer the shared utility if available so everything lands under junk_test/
    if ImmobilierUtils is not None:
        ImmobilierUtils.save_to_json(data, filename)
    else:
        with open(filename, "a", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.write("\n")  # JSON Lines format – one object per line


def parse_float_or_none(text):
    try:
        return float(text.strip())
    except (ValueError, AttributeError):
        return ""


def normalize_pieces(text):
    if not text:
        return ""
    match = re.search(r'[Ff]?\s*(\d+)', text)
    if match:
        return int(match.group(1))
    return ""


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


def convert_property_type(raw_key):
    valid_types = {
        "Appartement", "Villa", "Local", "Terrain", "Studio", "Hangar",
        "Niveau de villa", "Immeuble", "Duplex", "Carcasse", "Autre",
        "Bungalow", "Terrain agricole", "Usine", "Chalet", "Commerce",
        "Locaux", "Bureau", "Autres", "Salle", "Hostel", "Dortoir",
        "Ferme", "Hotel", "Triplex", "Maison", "Pavillon", "Auberge", "Résidence"
    }

    normalization_map = {
        "bungalow": "Bungalow",
        "bungalows": "Bungalow",
        "niveau": "Niveau de villa",
        "niveau de villa": "Niveau de villa",
        "terrain-agricole": "Terrain agricole",
        "terrain agricole": "Terrain agricole",
        "appartements": "Appartement",
        "immeubles": "Immeuble",
        "commerce, local": "Commerce",
        "bureaux": "Bureau",
        "ferme, terrain": "Ferme",
        "residence": "Résidence",
        "résidence": "Résidence"
    }

    if not raw_key or not isinstance(raw_key, str):
        return ""

    cleaned = raw_key.strip().lower()

    normalized = normalization_map.get(cleaned, cleaned).capitalize()
    if normalized in valid_types:
        return normalized

    lowered = raw_key.lower()
    for key, value in normalization_map.items():
        if key in lowered:
            normalized_candidate = value
            if normalized_candidate in valid_types:
                return normalized_candidate

    for valid in valid_types:
        if valid.lower() in lowered:
            return valid

    return ""

def detect_transaction_from_title(title: str) -> str:
    """
    Detects the transaction type from the ad title, with priority order.
    Returns one of: Vente, Location, Location-vacances, Cherche-location, Cherche-achat
    """
    if not title:
        return ""

    t = title.lower()

    if "location vacances" in t or "location vacance" in t:
        return "Location-vacances"
    if "cherche location" in t or "recherche location" in t or "je cherche à louer" in t:
        return "Cherche-location"
    if "cherche achat" in t or "recherche achat" in t or "cherche à acheter" in t:
        return "Cherche-achat"
    if "location" in t or "louer" in t or "à louer" in t:
        return "Location"
    if "vente" in t or "vendre" in t or "à vendre" in t:
        return "Vente"

    return ""  # Unknown / fallback

def extract_bien_transaction_from_breadcrumbs(soup):
    """
    Extracts 'bien' (property type) and 'transaction' from breadcrumb elements.
    Example HTML for bien: <li class="v-breadcrumbs-item ..." name="Villa">...</li>
    Example HTML for transaction: <a aria-label="Vente">Vente</a>
    """
    bien = ""
    transaction = ""
    
    # All breadcrumb items
    breadcrumb_items = soup.select("li.v-breadcrumbs-item")
    
    for item in breadcrumb_items:
        # Check for 'name' attribute which often contains the property type (bien)
        name_attr = item.get("name")
        if name_attr:
            normalized_bien = convert_property_type(name_attr)
            if normalized_bien:
                bien = normalized_bien
        
        # Check for links or aria-label that indicate transaction
        link = item.find("a")
        if link:
            text = (link.get("aria-label") or link.get_text(strip=True)).capitalize()
            # Use same categories as in detect_transaction_from_title
            if text in ["Vente", "Location", "Location-vacances", "Location vacances", "Echange", "Cherche-achat", "Cherche-location", "Cherche achat", "Cherche location"]:
                # Standardize hyphenated vs space-separated
                transaction = text.replace(" ", "-")
                
    return bien, transaction

async def scrape_single_url(
    target_url: str,
    max_retries: int = 3,
    retry_delay: float = 5,
    zone_name: str = "UNKNOWN",
) -> None:
    """
    Scrape a single Ouedkniss detail page through Proxyium.

    Parameters
    ----------
    target_url : str
        The real Ouedkniss listing URL.
    max_retries : int
        How many times to retry on failures. This is controlled per-zone
        by `main.py` (e.g. HOT=2, WARM=3, COLD=5).
    retry_delay : float
        Seconds to wait between retries (per-zone).
    zone_name : str
        Just for logging (e.g. "HOT", "WARM", "COLD") so you see which
        pipeline the request belongs to.
    """
    proxy_url = "https://proxyium.com/"

    browser_config = BrowserConfig(
        headless=True,
        text_mode=False,
        browser_type="chromium",
    )

    js_commands = [
        # Give Proxyium time to load and stabilize – kept moderate so we
        # don't hold connections for too long.
        "await new Promise(resolve => setTimeout(resolve, 7000));",
        # Force French locale in LocalStorage and Cookies (best effort).
        "localStorage.setItem('ok-auth-frame', JSON.stringify({ locale: 'fr' }));",
        "document.cookie = 'ok-locale=fr; path=/; domain=.ouedkniss.com';",
        # Accept cookies if the Quantcast / FC banner appears.
        "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",
        # Fill in Proxyium form with the final Ouedkniss URL (force lang=fr).
        f"document.getElementById('unique-form-control').value = '{target_url}{'&' if '?' in target_url else '?'}lang=fr';",
        "document.querySelector('#web_proxy_form').submit();",
        # Allow proxied page to render.
        "await new Promise(resolve => setTimeout(resolve, 4000));",
        "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",
        # Scroll to contact block so that lazy-loaded content has a chance to appear.
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
        # Final wait to ensure lazy-loaded pieces are rendered.
        "await new Promise(resolve => setTimeout(resolve, 4000));",
    ]

    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        js_code=js_commands,
        # Slightly lower delay/timeout to reduce long-lived sessions on Proxyium,
        # while still being generous for slow pages.
        delay_before_return_html=20,
        page_timeout=110_000,
        wait_until="domcontentloaded",
    )

    for attempt in range(1, max_retries + 1):
        print(
            f"[DETAIL][{zone_name}] Attempt {attempt}/{max_retries} → {target_url}"
        )
        async with AsyncWebCrawler(verbose=True, config=browser_config) as crawler:
            try:
                result = await crawler.arun(url=proxy_url, config=config, timeout=120_000)
            except Exception as e:
                print(
                    f"[DETAIL][{zone_name}] Crawl engine error for {target_url}: {e}"
                )
                result = None

        if result and result.success:
            soup = BeautifulSoup(result.html, "html.parser")

            title = extract_text_or_default(soup, "h1.text-h5.text-capitalize")

            # Try the preferred description selector first.
            desc_elem = soup.select_one("div.v-card-text.__description")
            if desc_elem:
                description = desc_elem.get_text(separator="\n", strip=True)
            else:
                description = extract_text_or_default(
                    soup, "div.__description.mb-2", ""
                )

            print(
                f"[DETAIL][{zone_name}] Description length={len(description)} "
                f"preview={description[:100]!r}"
            )

            price_value = extract_text_or_default(
                soup, "div.mt-1.line-height-2.text-primary.text-h6 div.mr-1"
            ).replace(" ", "")
            price_unit = extract_text_or_default(
                soup, "div.mt-1.line-height-2.text-primary.text-h6 div.mr-1 + div"
            )
            price_dec = traitement_prix(price_value, price_unit)

            # === Detection for bien and transaction ===
            breadcrumb_bien, breadcrumb_transaction = extract_bien_transaction_from_breadcrumbs(
                soup
            )

            # Transaction priority: Breadcrumbs > Title detection > Chips
            transaction_from_title = detect_transaction_from_title(title)
            transaction_chips = [
                chip.get_text(strip=True)
                for chip in soup.select(
                    "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Conditions de paiement') + div .v-chip__content"
                )
            ]

            final_transaction = (
                breadcrumb_transaction
                or transaction_from_title
                or ", ".join(transaction_chips)
                or "Non spécifié"
            )

            # Bien priority: Breadcrumbs > Spec table
            spec_bien = convert_property_type(
                extract_text_or_default(
                    soup,
                    "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Type') + div",
                )
            )
            final_bien = breadcrumb_bien or spec_bien

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

            # --- LOCATION EXTRACTION ---
            address = ""
            wilaya = ""
            commune = ""

            try:
                # Parse ok-list entries using icon markers.
                for li in soup.select("ul.ok-list li"):
                    # Wilaya + Commune usually with map marker icon.
                    if li.select_one(".__prepend i.mdi-map-marker"):
                        content = (
                            li.select_one(".__content .__title .text-wrap")
                            or li.select_one(".__content .__title")
                        )
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

                # Address with the home-map-marker icon.
                for li in soup.select("ul.ok-list li"):
                    if li.select_one(".__prepend i.mdi-home-map-marker"):
                        content = (
                            li.select_one(".__content .__title .text-wrap")
                            or li.select_one(".__content .__title")
                        )
                        if content:
                            address = content.get_text(" ", strip=True)
                        break

            except Exception:
                # Fallback: try some generic selectors if ok-list isn't present.
                loc = soup.select_one(
                    "div.text-wrap.text-capitalize.d-flex.flex-wrap"
                )
                if loc:
                    txt = loc.get_text(" ", strip=True)
                    if " - " in txt:
                        wilaya, commune = map(str.strip, txt.split(" - ", 1))
                    else:
                        wilaya = txt

                addr = soup.select_one("div.v-list-item__content") or soup.select_one(
                    "span.__title div.text-wrap.text-capitalize"
                )
                if addr:
                    address = addr.get_text(" ", strip=True)

            if wilaya:
                wilaya = wilaya.strip()
            if commune:
                commune = commune.strip()
            if address:
                address = address.strip()

            print(
                f"[DETAIL][{zone_name}] Location → wilaya={wilaya!r}, commune={commune!r}, adresse={address!r}"
            )

            contact_container = soup.find(id="announcementUserInfo")
            if not contact_container:
                print(f"[DETAIL][{zone_name}] No contact container found.")
            else:
                first_item = contact_container.select_one(".v-list-item")
                if first_item:
                    city_div = first_item.select_one(
                        ".py-2.text-wrap.text-capitalize"
                    )
                    if city_div:
                        city_text = city_div.get_text(strip=True)
                        parts = city_text.split("-")
                        if len(parts) == 2:
                            wilaya, commune = parts
                        else:
                            wilaya, commune = city_text, ""

                address_element = contact_container.find(
                    "div", class_="v-list-item__content"
                )
                if address_element:
                    address = address_element.get_text(strip=True)

            # ==================== CONTACT EXTRACTION ====================
            contact = {
                "name": None,
                "profile_link": None,
                "email": [],
                "phones": [],
                "whatsapp": [],
                "telegram": [],
                "viber": [],
            }

            # 1. Name extraction (with fallbacks).
            name_elem = (
                soup.select_one("a.ok-list-item .__title")
                or soup.select_one("ul.ok-list .__title")
                or (
                    contact_container.select_one("a.ok-list-item .__title")
                    if contact_container
                    else None
                )
                or soup.select_one(".ok-list-item .__title")
            )
            if name_elem:
                contact["name"] = name_elem.get_text(strip=True)

            # 2. Profile link (build from user ID in raw HTML / JSON).
            user_id = None
            id_patterns = [
                r'"userId"\s*:\s*"?(\d+)"?',
                r'"user"\s*:\s*\{[^}]*?"id"\s*:\s*(\d+)',
                r'store\.user\.id\s*=\s*(\d+)',
                r'https://www\.ouedkniss\.com/membre/(\d+)',
                r'"@id":\s*"https://www\.ouedkniss\.com/membre/(\d+)"',
            ]
            for pattern in id_patterns:
                match = re.search(pattern, result.html)
                if match:
                    user_id = match.group(1)
                    break
            if user_id:
                contact["profile_link"] = (
                    f"https://www.ouedkniss.com/membre/{user_id}"
                )

            # 3. Emails.
            for a in soup.select('a[href^="mailto:"]'):
                email = a["href"].replace("mailto:", "").strip().lower()
                if email and email not in contact["email"]:
                    contact["email"].append(email)

            # 4. Phones (links + visible text).
            seen_phones = set()
            for a in soup.select('a[href^="tel:"]'):
                phone = re.sub(r"\D", "", a["href"])
                if len(phone) >= 9 and phone not in seen_phones:
                    seen_phones.add(phone)
                    contact["phones"].append(phone)

            for btn in soup.select(
                "#announcementUserInfo a.v-btn, #announcementUserInfo a.ok-list-item"
            ):
                txt = btn.get_text(strip=True)
                phones_in_text = re.findall(
                    r"(?:0|\+213)\s?[567]\d{1}\s?\d{2}\s?\d{2}\s?\d{2}", txt
                )
                for p in phones_in_text:
                    clean = re.sub(r"\D", "", p)
                    if len(clean) >= 9 and clean not in seen_phones:
                        seen_phones.add(clean)
                        contact["phones"].append(clean)

            # 5. Social links (WhatsApp / Telegram / Viber).
            for a in soup.select('a[href*="wa.me"], a[href*="whatsapp.com"]'):
                href = a.get("href", "")
                match = re.search(r"wa\.me/(\+?\d+)", href)
                if match:
                    clean_link = f"https://wa.me/{match.group(1)}"
                    if clean_link not in contact["whatsapp"]:
                        contact["whatsapp"].append(clean_link)

            for a in soup.select('a[href*="t.me"]'):
                href = a.get("href", "")
                match = re.search(r"t\.me/(\+?\d+)", href)
                if match:
                    clean_link = f"https://t.me/{match.group(1)}"
                    if clean_link not in contact["telegram"]:
                        contact["telegram"].append(clean_link)

            for a in soup.select('a[href^="viber://"]'):
                href = a.get("href", "").strip()
                if href and href not in contact["viber"]:
                    contact["viber"].append(href)

            # 6. Fallback phones from social links if necessary.
            if not contact["phones"]:
                for link in (
                    contact["whatsapp"] + contact["telegram"] + contact["viber"]
                ):
                    nums = re.findall(r"(\+?\d{9,15})", link)
                    for n in nums:
                        cleaned = re.sub(r"\D", "", n)
                        if len(cleaned) >= 9 and cleaned not in seen_phones:
                            seen_phones.add(cleaned)
                            contact["phones"].append(cleaned)

            # Clean up empty lists.
            for k in ["email", "phones", "whatsapp", "telegram", "viber"]:
                if not contact[k]:
                    contact[k] = []

            now_iso = datetime.now().isoformat()

            property_data = {
                "titre": title,
                "url": target_url,
                # Versioning: unique document/version id based on URL and crawl date.
                # This is stored as a field; Elasticsearch will still use its own _id.
                "id": f"{target_url}|{now_iso}",
                "site_origine": "Ouedkniss.com",
                "categorie": "immobilier",
                "category": "immobilier",
                "date_crawl": now_iso,
                "prix": f"{price_value} {price_unit}"
                if price_value and price_unit
                else "",
                "prix_unit": "DA",
                "prix_value": price_value or "",
                "prix_dec": price_dec if price_value else "",
                "description": description,
                "bien": final_bien,
                "numero": extract_text_or_default(
                    soup,
                    "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Numéro') + div",
                ),
                "date_depot": parse_date(
                    extract_text_or_default(
                        soup,
                        "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Date') + div",
                    )
                ),
                "nombre_vues": extract_text_or_default(
                    soup,
                    "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Vues') + div",
                ),
                "nb_pieces": normalize_pieces(
                    extract_text_or_default(
                        soup,
                        "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Pièces') + div",
                    )
                ),
                "superficie": extract_text_or_default(
                    soup,
                    "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Superficie') + div span",
                ).split(" ")[0]
                if extract_text_or_default(
                    soup,
                    "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Superficie') + div span",
                )
                != ""
                else "",
                "superficie_unit": extract_text_or_default(
                    soup,
                    "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Superficie') + div span",
                ).split(" ")[-1]
                if extract_text_or_default(
                    soup,
                    "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Superficie') + div span",
                )
                != ""
                else "",
                "papiers": [
                    chip.get_text(strip=True)
                    for chip in soup.select(
                        "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Papiers') + div .v-chip__content"
                    )
                ],
                "specifications": [
                    chip.get_text(strip=True)
                    for chip in soup.select(
                        "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Spécifications') + div .v-chip__content"
                    )
                ],
                "images": images,
                "etage": extract_text_or_default(
                    soup,
                    "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Etage') + div",
                )
                or extract_text_or_default(
                    soup,
                    "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('étage') + div",
                ),
                "transaction": final_transaction,
                "payment": [
                    chip.get_text(strip=True)
                    for chip in soup.select(
                        "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Conditions de paiement') + div .v-chip__content"
                    )
                ]
                + [
                    span.get_text(strip=True)
                    for span in soup.select(
                        "div.v-col-sm-3.v-col-5.spec-name:-soup-contains('Type de vente') + div span"
                    )
                ],
                "adresse": address or "",
                "wilaya": wilaya.strip() if wilaya else "",
                "commune": commune.strip() if commune else "",
                "status": "200",
                "contact": contact,
                "as_photo": as_photo,
                "date_verif": now_iso,
                "as_prix": "Avec prix" if price_value else "Sans prix",
            }

            if not is_essential_data_empty(property_data):
                print(
                    f"[DETAIL][{zone_name}] Successfully parsed listing → "
                    f"{property_data['titre'][:80]!r}"
                )
                # Optional local debug saves (JSONL + pretty JSON) in `junk_test/`.
                # Toggle with DEBUG_SAVE_LOCAL at the top of this file.
                if DEBUG_SAVE_LOCAL:
                    save_to_json(property_data)
                    if ImmobilierUtils is not None:
                        try:
                            ImmobilierUtils.save_listing_file(property_data)
                        except Exception as e:
                            print(f"[DETAIL][{zone_name}] Failed to save listing file: {e}")

                # Send to Elasticsearch immediately.
                try:
                    # Interface aligned with documentation: insert_data_to_es(data, index)
                    insert_data_to_es(property_data, index="immobilier")
                    print(
                        f"[DETAIL][{zone_name}] [ES] Inserted → "
                        f"{property_data['titre'][:80]!r}"
                    )
                except Exception as e:
                    print(
                        f"[DETAIL][{zone_name}] [ES] Failed to insert document: {e}"
                    )

                return  # Success – stop retry loop.

        # If we reach here the attempt failed or parsing produced empty essential data.
        if attempt < max_retries:
            print(
                f"[DETAIL][{zone_name}] Retrying in {retry_delay} seconds "
                f"(attempt {attempt}/{max_retries})..."
            )
            await asyncio.sleep(retry_delay)

    print(
        f"[DETAIL][{zone_name}] FAILED to scrape {target_url} after "
        f"{max_retries} attempts."
    )


# Manual test example (uncomment to debug a single URL):
# asyncio.run(
#     scrape_single_url(
#         "https://www.ouedkniss.com/appartement-location-f3-oran-algerie-d48254269",
#         max_retries=3,
#         retry_delay=10,
#         zone_name="TEST",
#     )
# )
