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
        valeur = valeur.replace(",", "").replace("د.ج", "").replace(".", "").strip()
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
    list_items = description_soup.select('ul li')
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
            # If no unit is captured, it will be inferred later in extract_item_details

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
    os_match = re.search(r'(Windows\s*\d+(?:\s*\w+)?)', description_text, re.IGNORECASE)
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
    price_elements = soup.select('p.price span.woocommerce-Price-amount')
    prix_dec = 0.0
    if price_elements:
        # Use the first (minimum) price
        price_text = price_elements[0].get_text(strip=True).replace('د.ج', '').replace(',', '').strip()
        prix_dec = str_to_float(price_text)

    # Extract Etat and Categories
    categories = soup.select('span.posted_in a[rel="tag"]')
    processed_categories = []
    etat = ""
    for category in categories:
        text = category.get_text(strip=True)
        if text == "Renewed PC":
            etat = "Renewed"
        elif text == "DESKTOP PC":
            processed_categories.append("Desktop PCs")
        else:
            processed_categories.append(text)
    etat_element = etat or "New"

    # Extract Description
    description = safe_extract(soup, '#tab-description .wc-tab-inner')
    description_text = ""
    description_elem = soup.select_one('#tab-description .wc-tab-inner')
    if description_elem:
        # Remove promotional links
        for link in description_elem.select('a'):
            link.decompose()
        description_text = description_elem.get_text(strip=True)

    # Extract Images
    images_list = []
    gallery = soup.select('div.product-images img')
    for img in gallery:
        src = img.get('src') or img.get('data-src', '')
        if src and "logo" not in src.lower():  # Exclude logo images
            images_list.append(src)
    
    zoom_imgs = soup.select('img.zoomImg')
    for img in zoom_imgs:
        src = img.get('src')
        if src and src not in images_list and "logo" not in src.lower():
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

    # Extract brand from title or tags
    brand = ""
    brand_match = re.search(r'^(DELL|LENOVO|HP|ASUS|ACER|MSI|APPLE|INFORMATICS)', titre, re.IGNORECASE)
    if brand_match:
        brand = brand_match.group(1).upper()
    else:
        tags = soup.select('span.tagged_as a[rel="tag"]')
        for tag in tags:
            tag_text = tag.get_text(strip=True).upper()
            if tag_text in ["DELL", "LENOVO", "HP", "ASUS", "ACER", "MSI", "APPLE", "INFORMATICS"]:
                brand = tag_text
                break

    # Extract model from title or tags
    model = ""
    model_match = re.search(r'(OPTIPLEX\s+\d+|CONFIG\s+PC\s+GAMER\s+[A-Z0-9-]+|[A-Z0-9-]+)', titre, re.IGNORECASE)
    if model_match:
        model = model_match.group(0)
    else:
        tags = soup.select('span.tagged_as a[rel="tag"]')
        for tag in tags:
            tag_text = tag.get_text(strip=True)
            if "OptiPlex" in tag_text or "CONFIG PC GAMER" in tag_text:
                model = tag_text
                break

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
            # Default to "ans" if no unit found
            garantie_unit = "ans"
        # Extract the numeric value
        garantie_match = re.search(r'(\d+)', garantie)
        if garantie_match:
            garantie = garantie_match.group(1)

    now_iso = datetime.now().strftime("%Y-%m-%d")
    item_details = {
        'titre': titre,
        'url': url,
        'etat': etat_element,
        'livraison': "58 Wilayas",
        'site_origine': "informatics-dz.com",
        'transaction': "Vente",
        'category': "multimedia",
        'categorie': extracted_data.get('categorie', "Desktop PCs"),
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