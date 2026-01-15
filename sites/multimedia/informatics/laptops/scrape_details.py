import re
import asyncio
import json
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode


def avec_sans_photo(image: str) -> str:
    """
    Return "Avec photo" if the image string is non-empty, otherwise "Sans photo".
    """
    return "Avec photo" if str(image).strip() else "Sans photo"


def avec_sans_prix(prix_dec: str, prix_unit: str) -> str:
    """
    Return "Avec prix" if both price parts are provided and prix_dec is non-zero;
    otherwise, return "Sans prix".
    """
    try:
        if prix_dec and prix_unit and float(prix_dec) != 0:
            return "Avec prix"
    except ValueError:
        pass
    return "Sans prix"


def traitement_prix(prix_dec: str, prix_unit: str) -> float:
    """
    Convert the price to DA based on the unit.
    - "Millions": multiply by 10,000.
    - "Milliards": multiply by 10,000,000.
    - Otherwise, return the float value.
    If any price part is missing or conversion fails, returns 0.0.
    """
    if prix_dec and prix_unit:
        try:
            value = float(prix_dec)
        except ValueError:
            return 0.0
        if prix_unit == "Millions":
            return value * 10000
        elif prix_unit == "Milliards":
            return value * 10000000
        else:
            return value
    return 0.0


def str_to_float(valeur: str) -> float:
    """
    Convert a string to a float, replacing commas with dots.
    Returns 0.0 if the string is empty or conversion fails.
    """
    if not valeur:
        return 0.0
    try:
        valeur = valeur.replace(",", "")
        return float(valeur)
    except ValueError:
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
    Placeholder for converting a string to a date.
    Currently returns the original value.
    """
    return valeur if valeur else ""


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


def extract_from_description(description):
    """
    Extract specific details from product description using regex
    """
    data = {}
    
    # Processor
    processor_match = re.search(r'Intel Core (i\d-\d+[^\s,]+)', description, re.IGNORECASE)
    if processor_match:
        data['processor_cores'] = processor_match.group(1)
    
    # Processor speed
    processor_hz_match = re.search(r'(\d+(?:\.\d+)?\s*GHz)', description, re.IGNORECASE)
    if processor_hz_match:
        data['processor_hz'] = processor_hz_match.group(1)
    
    # RAM
    ram_match = re.search(r'(\d+)\s*GB\s*(?:DDR\d)?\s*RAM', description, re.IGNORECASE)
    if ram_match:
        data['ram'] = ram_match.group(1)
        data['ram_unit'] = "GB"
    
    # Storage
    storage_match = re.search(r'(\d+)\s*GB\s*SSD', description, re.IGNORECASE)
    if storage_match:
        data['m_interne'] = storage_match.group(1)
        data['m_interne_unit'] = "GB"
    
    # Screen size
    screen_size_match = re.search(r'(\d+(?:\.\d+)?)[″"]\s*(?:Full HD|FHD|HD)', description, re.IGNORECASE)
    if screen_size_match:
        data['taille_ecran'] = screen_size_match.group(1)
    
    # Screen type
    screen_type_match = re.search(r'(Full HD|FHD|HD|IPS)', description, re.IGNORECASE)
    if screen_type_match:
        data['type_ecran'] = screen_type_match.group(1)
    
    # Color
    color_match = re.search(r'(black|blue|silver|gray|grey|white|gold|night blue)', description, re.IGNORECASE)
    if color_match:
        data['couleur'] = color_match.group(1).title()
    
    # Weight
    weight_match = re.search(r'(\d+(?:\.\d+)?)\s*kg', description, re.IGNORECASE)
    if weight_match:
        data['poid'] = weight_match.group(1)
        data['poid_unit'] = "kg"
    
    # Battery
    battery_match = re.search(r'(\d+(?:\.\d+)?)\s*hours\s*battery', description, re.IGNORECASE)
    if battery_match:
        data['batterie'] = f"{battery_match.group(1)} hours"
    
    # Camera
    camera_match = re.search(r'(HD|FHD|720p|1080p)\s*(?:webcam|camera)', description, re.IGNORECASE)
    if camera_match:
        data['camera_av'] = camera_match.group(1)
    
    # OS
    os_match = re.search(r'(Windows\s*\d+(?:\s*\w+)?)', description, re.IGNORECASE)
    if os_match:
        os_full = os_match.group(1)
        data['os'] = "Windows"
        data['os_version'] = os_full.replace("Windows", "").strip()
    
    return data


async def extract_item_details(url: str) -> dict:
    """
    Asynchronously extracts item details from the provided URL.
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
                return elem.get_text(strip=True)
            return elem.get(attr, '')
        return ''

    # Extract Title
    titre = safe_extract(soup, 'h1.product_title')

    # Extract Price
    price_element = soup.select_one('p.price span.woocommerce-Price-amount')
    price_text = ""
    if price_element:
        price_text = (
            price_element.get_text(strip=True)
            .replace('د.ج', '')
            .replace('.', '')
            .replace(',', '')
            .strip()
        )
        prix_dec = str_to_float(price_text)
    else:
        prix_dec = 0.0
    
    # Extract Etate
    categories = soup.select('span.posted_in a[rel="tag"]')

    # Process category text
    processed_categories = []
    for category in categories:
        text = category.get_text(strip=True)
        if text == "NEW LAPTOP":
            processed_categories.append("New")
        elif text == "RENEWED LAPTOP":
            processed_categories.append("Renewed")
        else:
            processed_categories.append(text)

    # Join categories with comma separator
    etat_element = ", ".join(processed_categories)
    # Extract Description
    description = safe_extract(soup, '#tab-description .wc-tab-inner')
    
    # Extract Description Text Only
    description_text = ""
    description_elem = soup.select_one('#tab-description .wc-tab-inner')
    if description_elem:
        description_text = description_elem.get_text(strip=True)

    # Extract Images
    images_list = []
    gallery = soup.select('div.product-images img')
    for img in gallery:
        src = img.get('src') or img.get('data-src', '')
        if src:
            images_list.append(src)
    
    # Also check for zoomImg images
    zoom_imgs = soup.select('img.zoomImg')
    for img in zoom_imgs:
        src = img.get('src')
        if src and src not in images_list:
            images_list.append(src)
            
    images_list = list(dict.fromkeys(images_list))  # Remove duplicates

    # Extract Technical Specifications
    specs = {}
    spec_table = soup.select('#tab-additional_information table.woocommerce-product-attributes tr')
    for row in spec_table:
        key = safe_extract(row, 'th')
        value = safe_extract(row, 'td')
        if key and value:
            specs[key.strip().lower()] = value.strip()

    def get_spec(key: str, default: str = '') -> str:
        """
        Helper function to retrieve a technical specification.
        """
        return specs.get(key.lower(), default)

    # Extract brand from title or breadcrumbs
    brand = ""
    brand_match = re.search(r'^(LENOVO|HP|DELL|ASUS|ACER|MSI|APPLE)', titre, re.IGNORECASE)
    if brand_match:
        brand = brand_match.group(1).upper()
    else:
        # Try to extract from breadcrumbs
        breadcrumbs = soup.select('.wd-breadcrumbs span a')
        for crumb in breadcrumbs:
            crumb_text = crumb.get_text(strip=True)
            if crumb_text.upper() in ["LENOVO", "HP", "DELL", "ASUS", "ACER", "MSI", "APPLE"]:
                brand = crumb_text.upper()
                break
    
    # Extract categories from breadcrumbs
    category = ""
    categories = []
    breadcrumbs = soup.select('.wd-breadcrumbs span a')
    for crumb in breadcrumbs:
        crumb_text = crumb.get_text(strip=True)
        categories.append(crumb_text)
        if "LAPTOP" in crumb_text.upper() or "ORDINATEUR" in crumb_text.upper():
            category = "Laptops"
    
    # Extract model from title
    model = ""
    model_match = re.search(r'(?:IDEAPAD|THINKPAD|PAVILION|LATITUDE|INSPIRON|ZENBOOK|VIVOBOOK|PREDATOR|NITRO)\s+([A-Z0-9-]+)', titre, re.IGNORECASE)
    if model_match:
        model = model_match.group(0)
    
    # Extract additional details from description
    extracted_data = extract_from_description(description_text)
    
    # Get garantie if present
    garantie = get_spec('warranty') or get_spec('garantie')
    garantie_unit = ""
    if garantie:
        garantie_match = re.search(r'(\d+)', garantie)
        if garantie_match:
            garantie_value = garantie_match.group(1)
            if "month" in garantie.lower() or "mois" in garantie.lower():
                garantie_unit = "mois"
            elif "year" in garantie.lower() or "an" in garantie.lower():
                garantie_unit = "ans"
            garantie = garantie_value

    now_iso = datetime.now().strftime("%Y-%m-%d")
    item_details = {
        'titre': titre,
        'url': url,
        'etat': etat_element,
        'livraison': "58 Wilayas",
        'site_origine': "Informatics-dz.com",
        'transaction': "Vente",
        'category': "multimedia",
        'categorie': category or "Laptops",
        'description': description,
        'date_depot': now_iso,
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
        'm_interne': extracted_data.get('m_interne', get_spec('hard drive capacity')),
        'm_interne_unit': extracted_data.get('m_interne_unit', 'GB'),
        'processor_cores': extracted_data.get('processor_cores', get_spec('cpu')),
        'processor_hz': extracted_data.get('processor_hz', ''),
        'prix_dec': prix_dec,
        'prix_unit': "DA",
        'images': images_list,
        'adresse': "Toute l'Algérie",
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
