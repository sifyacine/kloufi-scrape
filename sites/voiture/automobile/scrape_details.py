import asyncio
import re
import sys
import os
from datetime import datetime
from bs4 import BeautifulSoup

from core.base_scraper import BaseScraper
from core.utils import save_data
from utils import VehicleUtils


try:
    sys.path.insert(1, '../../global')
    from insert_scrape import insert_data_to_es
except ImportError:

    def insert_data_to_es(data, index):
        print(f"[Mock] Inserting data to ES index '{index}'")


class MobileScraper(BaseScraper):
    def __init__(self, max_concurrent_details=5):
        super().__init__(base_url="https://www.mobile.de/fr")
        self.all_urls = []
        self.general_url = (
            "https://www.mobile.de/fr/voiture/recherche.html"
            "?isSearchRequest=true&s=Car&vc=Car&fr=2023&ref=quickSearch"
        )
        self.max_concurrent_details = max_concurrent_details
        self.results = []
        self.results_lock = asyncio.Lock()
        self.processed_urls = set()  # Track processed URLs
        self.failed_urls = []  # Track failed URLs for retry

    # ============================================================
    # LISTINGS WITH CONCURRENT DETAIL SCRAPING - FIXED VERSION
    # ============================================================
    async def scrape_listings_and_details(self):
        """Crawl listing pages and scrape details concurrently with guaranteed processing"""
        print("🔍 Starting concurrent listing scrape for Mobile.de/fr...")

        page = 1
        max_pages = 200
        
        # Queue for URLs to process
        url_queue = asyncio.Queue()
        
        # Semaphore to limit concurrent detail scraping
        detail_semaphore = asyncio.Semaphore(self.max_concurrent_details)
        
        # Event to signal when crawling is done
        crawling_done = asyncio.Event()
        
        # Task to process detail pages
        async def detail_worker(worker_id):
            print(f"🔧 Detail worker {worker_id} started")
            while True:
                try:
                    # Wait for URL with timeout
                    url = await asyncio.wait_for(url_queue.get(), timeout=2.0)
                    
                    # Skip if already processed
                    if url in self.processed_urls:
                        url_queue.task_done()
                        continue
                    
                    async with detail_semaphore:
                        success = await self.scrape_and_save_detail(url)
                        if success:
                            self.processed_urls.add(url)
                        else:
                            self.failed_urls.append(url)
                    
                    url_queue.task_done()
                    
                except asyncio.TimeoutError:
                    # Check if we're done crawling and queue is empty
                    if crawling_done.is_set() and url_queue.empty():
                        print(f"🛑 Worker {worker_id} finishing (no more URLs)")
                        break
                    # Otherwise continue waiting
                    continue
                    
                except Exception as e:
                    print(f"❌ Detail worker {worker_id} error: {e}")
                    url_queue.task_done()
            
            print(f"✅ Detail worker {worker_id} completed")

        # Start detail worker tasks
        num_workers = min(self.max_concurrent_details, 10)
        workers = [asyncio.create_task(detail_worker(i)) for i in range(num_workers)]
        
        # Crawl listing pages
        while page <= max_pages:
            url = (
                "https://www.mobile.de/fr/voiture/recherche.html"
                f"?isSearchRequest=true&s=Car&vc=Car&fr=2023&ref=quickSearch&pageNumber={page}"
            )

            print(f"\n📄 Crawling listing page {page}...")

            res = await self.scrape_page(url)
            if not res or not res.success:
                print(f"❌ Failed to load page {page}, stopping.")
                break

            soup = BeautifulSoup(res.html, "html.parser")
            links = []

            # Extract vehicle links
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/voiture/" in href and ".html" in href and "id=" in href:
                    full = href if href.startswith("http") else f"https://www.mobile.de{href}"
                    links.append(full)

            links = list(set(links))
            print(f"   Found {len(links)} links on page {page}")

            if len(links) == 0:
                print("⚠️ No more results. Pagination finished.")
                break

            # Add unique URLs to queue for processing
            new_urls = [url for url in links if url not in self.all_urls and url not in self.processed_urls]
            self.all_urls.extend(new_urls)
            
            for url in new_urls:
                await url_queue.put(url)
            
            print(f"   ✅ Added {len(new_urls)} URLs to processing queue")
            print(f"   📊 Queue size: {url_queue.qsize()}, Processed: {len(self.processed_urls)}, Total scraped: {len(self.results)}")

            # Add delay between listing page requests to prevent rate limiting
            await asyncio.sleep(1)
            
            page += 1

        # Signal that crawling is done
        crawling_done.set()
        print(f"\n✅ Finished crawling all listing pages. Total URLs found: {len(self.all_urls)}")
        print(f"⏳ Waiting for all detail pages to be processed...")
        print(f"   Queue remaining: {url_queue.qsize()}, Processed: {len(self.processed_urls)}")
        
        # Wait for all detail tasks to complete
        await url_queue.join()
        
        print(f"✅ Queue emptied. Processed: {len(self.processed_urls)}/{len(self.all_urls)}")
        
        # Retry failed URLs once
        if self.failed_urls:
            print(f"\n🔄 Retrying {len(self.failed_urls)} failed URLs...")
            retry_count = 0
            for url in self.failed_urls[:]:  # Copy list to avoid modification during iteration
                if url not in self.processed_urls:
                    success = await self.scrape_and_save_detail(url)
                    if success:
                        self.processed_urls.add(url)
                        self.failed_urls.remove(url)
                        retry_count += 1
            print(f"✅ Retry complete. Successfully processed {retry_count} additional URLs")
        
        # Cancel workers gracefully
        for worker in workers:
            worker.cancel()
        
        await asyncio.gather(*workers, return_exceptions=True)
        
        # Final summary
        print(f"\n{'='*60}")
        print(f"🎉 SCRAPING COMPLETE!")
        print(f"{'='*60}")
        print(f"   Total URLs found: {len(self.all_urls)}")
        print(f"   Successfully processed: {len(self.processed_urls)}")
        print(f"   Failed to process: {len(self.all_urls) - len(self.processed_urls)}")
        print(f"   Total results saved: {len(self.results)}")
        print(f"{'='*60}\n")

    # ============================================================
    # SCRAPE AND SAVE DETAIL PAGE - WITH SUCCESS RETURN
    # ============================================================

    
    async def scrape_and_save_detail(self, url):
        """Scrape a single detail page and save the result. Returns True if successful."""
        try:
            res = await self.scrape_page(url)
            if not res or not res.success:
                print(f"⚠️ Failed to load: {url}")
                return False

            data = await self.extract_data(res.html, url)
            if not data:
                print(f"⚠️ No data extracted: {url}")
                return False

            try:
                year = int(data.get("annee", "0"))
                if year >= datetime.now().year - 3:
                    # Add to results with thread safety
                    async with self.results_lock:
                        self.results.append(data)
                        result_count = len(self.results)

                    # Insert to Elasticsearch
                    insert_data_to_es(data, "voiture")

                    print(f"✅ [{result_count}] Scraped: {data.get('titre', '')[:60]}")
                    return True
                else:
                    print(f"⏩ Skipped: {url} (older car: {year})")
                    return True  # Successfully processed but filtered out

            except ValueError:
                print(f"⏩ Skipped: {url} (invalid year)")
                return True  # Successfully processed but filtered out

        except Exception as e:
            print(f"❌ Error scraping {url}: {e}")
            return False

    # ============================================================
    # EXTRACT DATA (unchanged)
    # ============================================================
    async def extract_data(self, html_content, url):
        soup = BeautifulSoup(html_content, "html.parser")

        # ---------------- TITLE ----------------
        title = ""

        # Primary selector - h2 with typography_headline__yJCAO class
        h2_title = soup.find("h2", class_="typography_headline__yJCAO")
        if h2_title:
            title = h2_title.get_text(strip=True)

        # Fallback to old selector
        if not title:
            title_el = soup.find(
                "div",
                class_="MainCtaBox_subTitle__wYybO margin_bottom_M__i_w26 typography_copyLarge__6DZQb"
            )
            if title_el:
                title = title_el.get_text(strip=True)

        # Last fallback
        if not title:
            fallback = soup.find("h1")
            if fallback:
                title = fallback.get_text(strip=True)


                def extract_price_block(soup):
                    """
                    Robustly extract old_price and current price.
                    Returns both as digit-only strings (e.g. "17000", "20000").
                    Tries to avoid taking both old+new concatenated from a single block.
                    """
                    old_price = ""
                    price = ""

                    # Try to find an element that clearly represents the old price
                    old_el = soup.find(attrs={"class": re.compile(r"oldPrice", re.I)})
                    if old_el:
                        old_text = old_el.get_text(strip=True)
                        old_price = re.sub(r"[^\d]", "", old_text)

                    # Try to find the "main" / current price element(s)
                    candidates = soup.find_all(attrs={"class": re.compile(r"mainPrice|MainPriceArea_mainPrice|main-price", re.I)})
                    for c in candidates:
                        # If this candidate contains the old-price element (as a child), remove the old-child text
                        child_old = c.find(attrs={"class": re.compile(r"oldPrice", re.I)})
                        if child_old:
                            # Remove the exact old-child text from the candidate's text to avoid concatenation
                            candidate_text = c.get_text(separator=' ', strip=True)
                            child_text = child_old.get_text(strip=True)
                            # Safely remove the child text once
                            new_text = candidate_text.replace(child_text, "", 1).strip()
                            if new_text:
                                price = re.sub(r"[^\d]", "", new_text)
                                break
                            # otherwise continue searching other candidates
                        else:
                            # No old-child inside candidate, use this candidate's text
                            candidate_text = c.get_text(separator=' ', strip=True)
                            price = re.sub(r"[^\d]", "", candidate_text)
                            break

                    # Final fallback - search any text node that looks like a price (e.g. "17 000 €" or "17000€")
                    if not price:
                        price_text_node = soup.find(text=re.compile(r"\d[\d\s\u00A0]*€"))
                        if price_text_node:
                            price = re.sub(r"[^\d]", "", price_text_node)

                    return old_price, price



                old_price, price = extract_price_block(soup)

        # Convert price value for numeric comparison (safe)
        price_digits = re.sub(r"[^\d]", "", price or "")
        price_numeric = int(price_digits) if price_digits.isdigit() else 0

        # Keep a formatted price string for storage (if you want separators, format here)
        # e.g., store as a simple digits-only string to avoid accidental concatenation elsewhere:
        price_str = price_digits

        # ---------------- IMAGES ----------------
        images = []
        # Target the thumbnail items that contain the actual image data
        for img in soup.select("div.InlineView_thumbnailItem__e4Ksg img.ImageSlideThumbnail_image__YDt4U"):
            # Try to get the highest resolution image from srcset
            srcset = img.get("srcset")
            if srcset:
                # Split srcset by comma and get the last (highest resolution) image
                # Format: "url width, url width, ..."
                src_list = [s.strip().split()[0] for s in srcset.split(',')]
                if src_list:
                    images.append(src_list[-1])  # Get the highest resolution (last one)
            else:
                # Fallback to src attribute if srcset is not available
                src = img.get("src")
                if src:
                    images.append(src)

        # Remove duplicates while preserving order
        images = list(dict.fromkeys(images))

        # ---------------- TECHNICAL DATA ----------------
        vehicle_data = {}
        tech_dl = soup.find("dl", class_="DataList_alternatingColorsList__8ejqq")

        if tech_dl:
            for dt, dd in zip(tech_dl.find_all("dt"), tech_dl.find_all("dd")):
                label = dt.get_text(strip=True).replace(':', '').lower()
                value = dd.get_text(strip=True)
                key = re.sub(r"\W+", '_', label)
                vehicle_data[key] = value

        # Fallback to alternative technical block
        if not vehicle_data:
            tech_block = soup.find(
                "div",
                class_=lambda v: v and v.startswith("KeyFeatures_keyFeatures__")
            )

            if tech_block:
                for row in tech_block.find_all(
                    "div",
                    class_=lambda v: v and v.startswith("KeyFeatures_keyFeature__")
                ):
                    label_div = row.find(
                        "div",
                        class_=lambda v: v and v.startswith("KeyFeatures_label__")
                    )
                    value_div = row.find(
                        "div",
                        class_=lambda v: v and v.startswith("KeyFeatures_value__")
                    )
                    if label_div and value_div:
                        label = label_div.get_text(strip=True).replace(':', '').lower()
                        value = value_div.get_text(strip=True)
                        key = re.sub(r"\W+", '_', label)
                        vehicle_data[key] = value

        # ---------------- OPTIONS ----------------
        options = []
        equip_ul = soup.find("ul", class_="CheckList_list__wPhvq")
        if equip_ul:
            options = [li.get_text(strip=True) for li in equip_ul.find_all("li")]

        # ---------------- DESCRIPTION ----------------
        description = ""
        desc_div = soup.find("div", class_="VehicleDescription_contentText__CgDL_")
        if desc_div:
            description = desc_div.get_text(separator=' ', strip=True)

        # ---------------- SPECIFIC FIELDS ----------------
        annee = vehicle_data.get('date_immatriculation', '').split('/')[-1] or ""

        raw_km = vehicle_data.get('kilométrage', '')
        km_digits = re.sub(r"[^\d]", "", raw_km)
        km = int(km_digits) if km_digits.isdigit() else 0

        # Marque / Model from title
        words = title.split()
        marque = words[0] if len(words) >= 1 else ""
        model = " ".join(words[1:3]) if len(words) >= 3 else (words[1] if len(words) == 2 else "")

        # ID
        ref_id = vehicle_data.get('reference_de_l_annonce', '')
        if not ref_id and "id=" in url:
            match = re.search(r"id=(\d+)", url)
            if match:
                ref_id = match.group(1)

        numero = (
            f"{ref_id}_{price}"
            if ref_id else f"{marque}_{model}_{price}".replace(" ", "_")
        )

        # ---------------- OTHER INFORMATION (unmapped fields) ----------------
        # Define fields that are already mapped to main structure
        mapped_fields = {
            'état_du_véhicule', 'catégorie', 'reference_de_l_annonce', 'origine',
            'kilométrage', 'cylindrée', 'puissance', 'motorisation', 'carburant',
            'nombre_de_places', 'nombre_de_portes', 'transmission', 'norme_antipollution',
            'pastille_verte', 'date_immatriculation', 'nombre_de_propriétaires_du_véhicule',
            'hu', 'climatisation', 'radar_de_recul', 'airbags',
            'nom_de_couleur_constructeur', 'couleur', 'équipements_intérieurs'
        }

        other_information = {}
        for key, value in vehicle_data.items():
            if key not in mapped_fields and value:
                other_information[key] = value

        # ---------------- RAW DATA ----------------
        raw_data = {
            "titre": title,
            "description": description,
            "numero": numero,
            "date_depot": datetime.now().isoformat(),
            "date_crawl": datetime.now().isoformat(),
            "site_origine": "Mobile.de",
            "url": url,
            "images": images,
            "options": options,
            "annee": annee,
            "marque": marque,
            "model": model,
            "km": str(km),
            "energie": vehicle_data.get('carburant', ''),
            "transmission": vehicle_data.get('transmission', ''),
            "couleur": vehicle_data.get('couleur', ''),
            "moteur": vehicle_data.get('puissance', ''),
            "prix": price_str,
            "prix_value": price_numeric,
            "old_price": old_price,
            "prix_unit": "€",
            "etat": vehicle_data.get('état_du_véhicule', 'Occasion').split(',')[0].strip(),
            "wilaya": "",
            "commune": "",
            "tax": "",
            "export": "true",
            "other_information": other_information,
        }

        unified = VehicleUtils.unify_data(raw_data)

        unified.update({
            "numero": numero,
            "category": "voiture",
            "categorie": "Automobiles & Vehicules",
            "status": "200",
            "as_photo": "Avec photo" if images else "Sans photo",
            "as_prix": "Avec prix" if price_numeric > 0 else "Sans prix",
            "tax": "",
            "export": "true",
            "other_information": other_information,
        })

        return unified

    # ============================================================
    # RUN
    # ============================================================
    async def run(self):
        await self.start_session()

        # Run concurrent scraping
        await self.scrape_listings_and_details()

        await self.close_session()

        if self.results:
            save_data(self.results, "mobile_data.json")
            print(f"💾 Saved {len(self.results)} results to mobile_data.json")

        return self.results