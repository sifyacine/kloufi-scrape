```python
import re
import asyncio
import sys
import os
# Removed - using MultimediaUtils
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

        print("Debug: str_to_float received empty value")
        return 0.0
    try:
        # Remove spaces, commas, 'د.ج', 'DA', and other non-numeric characters
        valeur = valeur.replace(",", "").replace("د.ج", "").replace("DA", "").replace(" ", "").strip()
        print(f"Debug: str_to_float processed value: {valeur}")
        return float(valeur)
    except ValueError as e:
        print(f"Debug: str_to_float failed for value '{valeur}': {e}")
        return 0.0


def str_to_int(valeur: str) -> int:
    """
    Convert a string to an int.
    Returns 0 if the string is empty or conversion fails.
    """
    if not valeur:
        return 0
    try:
        return int(valeur)
    except ValueError:
        return 0


def str_to_date(valeur: str) -> str:
    """
    Convert a date string in format 'DD Month YYYYHH:MM' or 'DD Month-HH:MM' to ISO format 'YYYY-MM-DD'.
    Handles French and English month names, assumes current year for missing year unless date is in the future.
    Returns empty string if conversion fails.
    """
    if not valeur:
        print("Debug: str_to_date received empty value")
        return ""
    try:
        # Remove 'Publiée le:' prefix and strip whitespace
        valeur = valeur.replace("Publiée le:", "").strip()
        print(f"Debug: str_to_date input after removing prefix: '{valeur}'")
        
        # Replace French month names with English (case-insensitive)
        month_map = {
            "jan": "Jan", "janvier": "Jan", "fév": "Feb", "février": "Feb", "mar": "Mar", "mars": "Mar",
            "avr": "Apr", "avril": "Apr", "mai": "May", "juin": "Jun", "juil": "Jul", "juillet": "Jul",
            "aoû": "Aug", "août": "Aug", "sep": "Sep", "sept": "Sep", "oct": "Oct", "octobre": "Oct",
            "nov": "Nov", "novembre": "Nov", "déc": "Dec", "décembre": "Dec"
        }
        valeur_lower = valeur.lower()
        for fr, en in month_map.items():
            valeur_lower = valeur_lower.replace(fr.lower(), en.lower())
        print(f"Debug: str_to_date after month mapping: '{valeur_lower}'")

        # Normalize format: replace hyphens or other separators with spaces
        valeur_lower = re.sub(r'[-–—]', ' ', valeur_lower)
        print(f"Debug: str_to_date after replacing separators: '{valeur_lower}'")

        # Insert space between year and time if missing (e.g., "202516:52" -> "2025 16:52")
        valeur_lower = re.sub(r'(\d{4})(\d{2}:\d{2})', r'\1 \2', valeur_lower)
        print(f"Debug: str_to_date after inserting space: '{valeur_lower}'")

        # Extract date components using regex for 'DD Month YYYY HH:MM' or 'DD Month HH:MM'
        date_match = re.match(r'(\d{1,2})\s+([a-zA-Z]+)\s+(?:(?:(\d{4})\s+)?(\d{1,2}:\d{2}))', valeur_lower)
        if not date_match:
            print(f"Debug: str_to_date regex match failed for '{valeur_lower}'")
            return ""

        day, month, year, time = date_match.groups()
        print(f"Debug: str_to_date extracted components: day='{day}', month='{month}', year='{year}', time='{time}'")

        # Capitalize month for strptime (e.g., 'may' -> 'May')
        month = month.capitalize()
        from datetime import datetime # Temporarily import here for this function
        current_year = datetime.now().year
        year = year if year else str(current_year)  # Use current year if not provided

        # Parse the date
        date_str = f"{day} {month} {time} {year}"
        print(f"Debug: str_to_date parsing string: '{date_str}'")
        date_obj = datetime.strptime(date_str, "%d %b %H:%M %Y")

        # If parsed date is in the future, assume it's from the previous year
        if date_obj > datetime.now():
            date_obj = date_obj.replace(year=int(year) - 1)
        
        formatted_date = date_obj.strftime("%Y-%m-%d")
        print(f"Debug: str_to_date output: '{formatted_date}'")
        return formatted_date
    except (ValueError, IndexError) as e:
        print(f"Debug: str_to_date failed for value '{valeur}': {e}")
        return ""


def categorie(valeur: str) -> str:
    """
    Standardize category names.
    """
    if not valeur:
        return ""
    elif valeur == "Téléphone portable":
        return "Smartphones"
    elif valeur == "Accessoires & Smartwatches":
        return "Accessoires"
    elif valeur == "DESKTOP PC":
        return "Desktop PCs"
    else:
        return valeur


def extract_numeric_value(text, unit=None):
    """
    Extract numeric value from text with optional unit.
    Returns tuple of (value, unit) or (value, '') if no unit specified
    """
    if not text:
        return ("", "")
    
    # Common patterns with units
    if unit:
        pattern = rf'(\d+(?:\.\d+)?)\s*{unit}'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return (match.group(1), unit)
    
    # Generic number extraction
    match = re.search(r'(\d+(?:\.\d+)?)', text)
    if match:
        return (match.group(1), '')
    
    return ("", "")


def extract_from_description(description_soup, description_text):
    """
    Extract specific details from product description using regex and BeautifulSoup
    """
    data = {}
    
    # Parse list items in description
    list_items = description_soup.select('ul li') if description_soup else []
    processor_options = []
    
    for item in list_items:
        text = item.get_text(strip=True)
        
        # CPU (any CPU model)
        cpu_match = re.search(r'(?:CPU|Processor):\s*([^\(]+)(?:\s*\((\d+\.\d+\s*GHz)\))?', text, re.IGNORECASE)
        if cpu_match:
            processor = cpu_match.group(1).strip()
            speed = cpu_match.group(2) if cpu_match.group(2) else ''
            processor_str = f"{processor} ({speed})" if speed else processor
            processor_options.append(processor_str)
            if not data.get('processor_cores'):
                data['processor_cores'] = processor
                data['processor_hz'] = speed

        # Optional CPU
        optional_cpu_match = re.search(r'CPU:\s*([^\(]+)', text, re.IGNORECASE)
        if optional_cpu_match:
            processor_options.append(optional_cpu_match.group(1).strip())

        # RAM
        ram_match = re.search(r'RAM:\s*(\d+)\s*GB\s*(?:DDR\d)?', text, re.IGNORECASE)
        if ram_match:
            data['ram'] = ram_match.group(1)
            data['ram_unit'] = "GB"

        # Optional RAM
        optional_ram_match = re.search(r'RAM:\s*(\d+)\s*GB\s*RAM', text, re.IGNORECASE)
        if optional_ram_match and not data.get('ram'):
            data['ram'] = optional_ram_match.group(1)
            data['ram_unit'] = "GB"

        # Storage
        storage_match = re.search(r'Storage:\s*(?:M\.2\s*NVME\s*)?(\d+)\s*(GB|TB)', text, re.IGNORECASE)
        if storage_match:
            data['m_interne'] = storage_match.group(1)
            data['m_interne_unit'] = storage_match.group(2)

        # Optional Storage
        optional_storage_match = re.search(r'Storage:\s*NVME\s*(\d+)\s*(GB|TB)', text, re.IGNORECASE)
        if optional_storage_match and not data.get('m_interne'):
            data['m_interne'] = optional_storage_match.group(1)
            data['m_interne_unit'] = optional_storage_match.group(2)

        # Warranty (Updated to handle Arabic 'سنة' and be more flexible)
        warranty_match = re.search(r'(?:Warranty|Garantie)\s*:?\s*(\d+)\s*(Year|Month|Mois|Ans|سنة)?', text, re.IGNORECASE)
        if warranty_match:
            data['garantie'] = warranty_match.group(1)
            warranty_unit = warranty_match.group(2).lower() if warranty_match.group(2) else ''
            if warranty_unit in ["year", "ans", "سنة"]:
                data['garantie_unit'] = "ans"
            elif warranty_unit in ["month", "mois"]:
                data['garantie_unit'] = "mois"

    # Combine processor options
    if processor_options:
        data['processor_cores'] = ", ".join(processor_options)

    # Fallback to text-based regex if list parsing didn't capture everything
    if not data.get('processor_cores'):
        processors = re.findall(r'(?:(?:Intel\s*[iI][3579](?:-\d{4,5}(?:KF)?)|RYZEN\s*[3579]\s*\d{4}(?:X)?|CORE\s*ULTRA\s*[3579]\s*\d+[K]?)(?:\s*\((\d+\.\d+\s*GHz)\))?)', description_text, re.IGNORECASE)
        if processors:
            processor_strings = [f"{p[0]} ({p[1]})" if p[1] else p[0] for p in processors]
            data['processor_cores'] = ", ".join(processor_strings)
            data['processor_hz'] = processors[0][1] if processors[0][1] else ''

    if not data.get('ram'):
        ram_match = re.search(r'(\d+)\s*GB\s*(?:DDR\d)?\s*RAM', description_text, re.IGNORECASE)
        if ram_match:
            data['ram'] = ram_match.group(1)
            data['ram_unit'] = "GB"

    if not data.get('m_interne'):
        storage_match = re.search(r'(\d+)\s*(GB|TB)\s*(?:SSD|M\.2\s*NVME)', description_text, re.IGNORECASE)
        if storage_match:
            data['m_interne'] = storage_match.group(1)
            data['m_interne_unit'] = storage_match.group(2)

    # Color
    color_match = re.search(r'(black|blue|silver|gray|grey|white|gold|night blue)', description_text, re.IGNORECASE)
    if color_match:
        data['couleur'] = color_match.group(1).title()

    # Weight
    weight_match = re.search(r'(\d+(?:\.\d+)?)\s*kg', description_text, re.IGNORECASE)
    if weight_match:
        data['poid'] = weight_match.group(1)
        data['poid_unit'] = "kg"

    # Operating System
    os_match = re.search(r'(Windows\s*\d+(?:\s*\w+)?|iOS\s*\d+)', description_text, re.IGNORECASE)
    if os_match:
        os_full = os_match.group(1)
        if "Windows" in os_full:
            data['os'] = "Windows"
            data['os_version'] = os_full.replace("Windows", "").strip()
        elif "iOS" in os_full:
            data['os'] = "iOS"
            data['os_version'] = os_full.replace("iOS", "").strip()

    return data


async def extract_item_details(url: str, date_depot: str) -> dict:
    """
    Asynchronously extracts item details from the provided URL for algerieannonces.com.
    Uses pre-extracted date_depot from the listing page.
    """
    browser_config = BrowserConfig(
        headless=True,
        browser_type="chromium",
        text_mode=False
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=url,
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                delay_before_return_html=10
            )
        )

    if not result.success:
        raise Exception(f"Failed to load detail page: {result.error_message}")

    soup = BeautifulSoup(result.html, "html.parser")

    def safe_extract(element, selector: str, attr: str = 'text') -> str:
        """
        Safely extract text or attribute from the selected element.
        """
        elem = element.select_one(selector)
        if elem:
            if attr == 'text':
                text = elem.get_text(strip=True)
                print(f"Debug: safe_extract ({selector}, {attr}) -> '{text}'")
                return text
            value = elem.get(attr, '')
            print(f"Debug: safe_extract ({selector}, {attr}) -> '{value}'")
            return value
        print(f"Debug: safe_extract ({selector}, {attr}) -> None")
        return ''

    # Extract Title
    titre = safe_extract(soup, 'div.description h1')

    # Extract Price with fallback selectors
    price_selectors = [
        'div.description strong.price span',
        'strong.price span',
        'div.description span.price',
        'strong.price'
    ]
    price_text = ""
    for selector in price_selectors:
        price_text = safe_extract(soup, selector)
        if price_text:
            break
    print(f"Debug: Extracted price_text: '{price_text}'")
    prix_dec = MultimediaUtils.str_to_float(price_text)

    # Extract Categories and Etat
    categories = []
    category_from_url = re.search(r'categorie/(\d+)/([^/]+)', url)
    if category_from_url:
        categories.append(category_from_url.group(2).replace('-', ' '))
    processed_categories = [MultimediaUtils.normalize_categorie(cat) for cat in categories]
    etat = MultimediaUtils.normalize_etat(titre, description_text)

    # Extract Description
    description_elem = soup.select_one('div.parameter div.block')
    description_text = ""
    if description_elem:
        for link in description_elem.select('a'):
            link.decompose()
        description_text = description_elem.get_text(strip=True)
    print(f"Debug: Extracted description: {description_text[:100]}...")  # Truncate for logging

    # Extract Images
    images_list = []
    gallery = soup.select('div.ad-gallery img')
    for img in gallery:
        src = img.get('src') or img.get('data-src', '')
        if src and "logo" not in src.lower() and "loader" not in src.lower():
            images_list.append(src)
    
    thumb_images = soup.select('div.ad-gallery ul.ad-thumb-list img')
    for img in thumb_images:
        src = img.get('src')
        if src and src not in images_list and "logo" not in src.lower():
            images_list.append(src)
            
    images_list = list(dict.fromkeys(images_list))  # Remove duplicates
    print(f"Debug: Extracted {len(images_list)} images")

    # Extract Technical Specifications
    specs = {}
    spec_list = soup.select('div.parameter ul.extraQuestionName li')
    for item in spec_list:
        text = item.get_text(strip=True)
        if ':' in text:
            key, value = map(str.strip, text.split(':', 1))
            specs[key.lower()] = value
    print(f"Debug: Extracted specs: {list(specs.keys())}")

    def get_spec(key: str, default: str = '') -> str:
        """
        Helper function to retrieve a technical specification.
        """
        return specs.get(key.lower(), default)

    # Extract brand from title or description
    brand = MultimediaUtils.extract_brand(titre) or MultimediaUtils.extract_brand(description_text)
    print(f"Debug: Extracted brand: {brand}")

    # Extract model from title or description
    model = MultimediaUtils.extract_model(titre) or MultimediaUtils.extract_model(description_text)
    print(f"Debug: Extracted model: {model}")

    # Extract additional details from description
    extracted_data = extract_from_description(description_elem, description_text)
    
    # Get garantie if present from specs or description
    garantie = get_spec('warranty') or get_spec('garantie') or extracted_data.get('garantie', '')
    garantie_unit = extracted_data.get('garantie_unit', '')

    if garantie and not garantie_unit:
        garantie_lower = garantie.lower()
        if any(word in garantie_lower for word in ["month", "mois"]):
            garantie_unit = "mois"
        elif any(word in garantie_lower for word in ["year", "an", "ans", "سنة"]):
            garantie_unit = "ans"
        else:
            garantie_unit = "ans"
        garantie_match = re.search(r'(\d+)', garantie)
        if garantie_match:
            garantie = garantie_match.group(1)
    print(f"Debug: Extracted garantie: {garantie}, unit: {garantie_unit}")

    # Extract address from info-holder
    adresse = safe_extract(soup, 'ul.info-holder li:first-child').split('/')[0].strip() if safe_extract(soup, 'ul.info-holder li:first-child') else "Toute l'Algérie"
    print(f"Debug: Extracted adresse: {adresse}")

    # Parse provided date_depot
    parsed_date_depot = MultimediaUtils.str_to_date(date_depot)
    now_iso = datetime.now().strftime("%Y-%m-%d")
    if not parsed_date_depot:
        print(f"Warning: Failed to parse date_depot '{date_depot}', using {now_iso} as fallback")

    item_details = {
        'titre': titre,
        'url': url,
        'etat': etat,
        'livraison': "58 Wilayas",
        'site_origine': "algerieannonces.com",
        'transaction': "Vente",
        'category': "multimedia",
        'categorie': processed_categories[0] if processed_categories else "Smartphones",
        'description': description_text,
        'date_depot': parsed_date_depot or now_iso,  # Fallback to current date if parsing fails
        'marque': brand or extracted_data.get('marque', ''),
        'modele': model or extracted_data.get('modele', ''),
        'garantie': garantie,
        'garantie_unit': garantie_unit,
        'dimension': extracted_data.get('dimension', ''),
        'taille_ecran': extracted_data.get('taille_ecran', get_spec('screen size')),
        'type_ecran': extracted_data.get('type_ecran', get_spec('screen type')),
        'os': extracted_data.get('os', get_spec('operating system')),
        'os_version': extracted_data.get('os_version', ''),
        'poid': extracted_data.get('poid', get_spec('weight')),
        'poid_unit': extracted_data.get('poid_unit', 'kg'),
        'couleur': extracted_data.get('couleur', get_spec('color')),
        'ram': extracted_data.get('ram', get_spec('ram')),
        'ram_unit': extracted_data.get('ram_unit', 'GB'),
        'm_interne': extracted_data.get('m_interne', get_spec('storage')),
        'm_interne_unit': extracted_data.get('m_interne_unit', 'GB'),
        'processor_cores': extracted_data.get('processor_cores', get_spec('cpu')),
        'processor_hz': extracted_data.get('processor_hz', ''),
        'prix_dec': prix_dec,
        'prix_unit': "DA",
        'images': images_list,
        'adresse': adresse,
        'status': 200,
        'date_crawl': now_iso,
        'date_verif': now_iso,
        'as_photo': "Avec photo" if images_list else "Sans photo",
        'as_prix': "Avec prix" if prix_dec else "Sans prix",
        'camera_ar': extracted_data.get('camera_ar', ''),
        'camera_av': extracted_data.get('camera_av', ''),
        'batterie': extracted_data.get('batterie', ''),
    }

    print("Extracted item details:", item_details)
    return item_details