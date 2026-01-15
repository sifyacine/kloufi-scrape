import asyncio
import json
import re
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from datetime import datetime
import sys
sys.path.insert(1, '../../global')
from insert_scrape import insert_data_to_es

def traitement_prix(prix_dec, prix_unit):
    """
    Convert price based on unit (Millions, Milliards).
    """
    try:
        prix_dec = float(prix_dec)
        if prix_unit == "Millions":
            return prix_dec * 1_000_000
        elif prix_unit == "Milliards":
            return prix_dec * 1_000_000_000
        return prix_dec
    except (ValueError, TypeError):
        return 0  # Default to 0 if conversion fails

async def scrape_car_details(url, item, etat):
    print(f"Scraping URL: {url}")
    
    browser_config = BrowserConfig(
        headless=True,
        text_mode=False,
        browser_type="chromium",
    )

    js_commands = [
        "await new Promise(resolve => setTimeout(resolve, 5000));",
        "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",
        """
        await new Promise(resolve => setTimeout(resolve, 3000));
        let maxScrollHeight = document.body.scrollHeight;
        let scrollStep = 300;
        let currentScroll = 0;

        while (currentScroll <= maxScrollHeight) {
            const targetElement = document.getElementById('announcementUserInfo');
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
        """
    ]

    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        js_code=js_commands,
        delay_before_return_html=10
    )

    async with AsyncWebCrawler(verbose=True, config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=config)

        if not result.success:
            print(f"Error scraping URL {url}: {result.error_message}")
            return

        soup = BeautifulSoup(result.html, "html.parser")

        # Extract images
        images = soup.find_all("div", class_="vehica-swiper-slide")
        images_links = [
            img.find("img")["src"].replace("-167x93", "").replace("-rotated", "").replace("-771x1024", "") for img in images
            if img.find("img") and img.find("img")["src"].startswith("https://tonobiles.com/wp-content/uploads")
        ]
        if len(images_links) > 0:
            set_images = set(images_links)
            images_links = list(set_images)

        # Extract title
        title = soup.find("h1", class_="vehica-car-name")
        title = title.text.strip() if title else ""

        # Photo status
        as_photo = "Avec photo" if images_links else "Sans photo"

        # Extract description
        description = soup.find("div", class_="vehica-car-description")
        description = description.text.strip() if description else ""

        # Extract price
        price_value, price_quantity = "0", "DA"
        price = soup.find("div", class_="vehica-car-price")
        if price:
            price_text = price.text.strip()
            price_parts = price_text.split(" ")
            if len(price_parts) == 2:
                price_value, price_quantity = price_parts
            elif len(price_parts) == 1:
                price_value = price_parts[0]

        # Extract attributes
        attributes = {}
        name_elements = soup.find_all('div', class_='vehica-car-attributes__name')
        for name_element in name_elements:
            attribute_name = name_element.text.strip().replace(':', '')
            value_element = name_element.find_next_sibling('div', class_='vehica-car-attributes__values')
            if value_element:
                attributes[attribute_name] = value_element.text.strip()
                
        # Extract wilaya (location)
        wilaya_element = soup.select_one('div.vehica-car-features a[href*="wilaya="]')
        wilaya = wilaya_element.text.strip() if wilaya_element else ""
        
        km = attributes.get("Kilométrage", "").replace(" km", "").replace(" KM", "") if attributes.get("Kilométrage") else ""
        if km != "":
            car_features = soup.select_one('div.vehica-car-feature')
            if car_features:
                km_match = re.search(r'(\d+)\s*KM', car_features.text)
                km = km_match.group(1) if km_match else km
                
        pattern = r"\b(produit[s]?\s+chimique[s]?|monétaires?|tachetée[s]?|masquée[s]?|nettoyer|billet[s]?|nettoyage|lavage|maculation|laveur|laboratoire|solution[s]?)\b"
        suspicious_text = re.search(pattern, description, re.IGNORECASE)

        # Extract and sanitize attribute values
        vehicle_data = {
            "titre": title,
            "description": description,
            "site_origine": "Tonobiles.com",
            "images": images_links,
            "url": url,
            "annee": attributes.get("Année", ""),
            "marque": attributes.get("Marque", ""),
            "model": attributes.get("Modèle", ""),
            "km": km,
            "km_unit": "km",
            "couleur": attributes.get("Couleur", ""),
            "energie": attributes.get("Enrgie", ""),
            "transmission": attributes.get("Transmission", ""),
            "prix": item['price'] if item['price'] and item['price'] != "Contactez pour le prix" else "",
            "prix_unit": "DA" if item['price'] and item['price'] != "Contactez pour le prix" else "",
            "prix_value": price_value if price_value else "",
            "prix_dec": traitement_prix(price_value, price_quantity) if price_value else 0.00,
            "etat": etat if etat else "",
            "date_crawl": datetime.now().isoformat(),
            "status": "200" if not suspicious_text else "404",
            "as_photo": as_photo,
            "date_depot": datetime.now().isoformat(),
            "category": "voiture",
            # "moteur": attributes.get("Moteur", ""),
            # "numero": vehicle_number,
            # "nombre_vues": vehicle_views,
            # "categorie": category,
            # "papers": papers,
            # "options": options,
            # "adresse": address,
            "wilaya": wilaya,
            "cylinders": re.findall(r"(\d+\.\d+|\d+)\sL", soup.text),
            "puissance":  re.findall(r"(\d+)\s[ch]", soup.text),
            "puissance_ch": "",
            # "commune": commune,
            # 'Cylinders_Num ': str_to_float(''.join(response.xpath("//div[@id='fiche_technique_auto']").re(r"(\d+.+\d+)\sL"))),
            # 'Cylinders_unit': ''.join(response.xpath("//div[@id='fiche_technique_auto']").re(r"\d+.+\d+\s(L)")),
            # 'Couple_moteur': ''.join(response.xpath('//div[@id="fiche_technique_auto"]').re(r"\d+\s\s?nm\s\s?-\s\d+tr/min")),
            # 'Acceleration': str_to_float(''.join(response.xpath('//div[@id="fiche_technique_auto"]').re(r"(\d+.?\d).?.?.?sec"))),
            # 'Acceleration_unit': ''.join(response.xpath('//div[@id="fiche_technique_auto"]').re(r"\d+.?\d.?.?.?(sec)")),
            # 'Max_speed': str_to_int(''.join(response.xpath('//div[@id="fiche_technique_auto"]').re(r"(\d+) km/h"))),
            # 'Max_speed_unit': ''.join(response.xpath('//div[@id="fiche_technique_auto"]').re(r"\d+ (km/h)")),
            # 'Options_ft': response.css('div#options > p ::text').re("(\w+)"),
            
        }

        # Print the extracted data
        print(json.dumps(vehicle_data, indent=2))
        insert_data_to_es(vehicle_data, "voiture")

# Uncomment to test the function
# asyncio.run(scrape_car_details("https://tonobiles.com/annonce/kia-sportage-2018-alger/"))
