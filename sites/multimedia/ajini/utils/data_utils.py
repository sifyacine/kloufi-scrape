import csv
import json
from models.tv import Tv

CATEGORY_MAP = {
    "Téléphone portable": "Smartphones",
    "Accessoires & Smartwatches": "Accessoires",
    "TV & Vidéo": "Télévisions",  # Add new categories here if needed
}



def avec_sans_photo(image):
    return "Avec photo" if image else "Sans photo"

def avec_sans_prix(Prix_dec, Prix_unit):
    return "Avec prix" if Prix_dec and Prix_unit and float(Prix_dec) != 0 else "Sans prix"

def process_price(price_input):
    # Handle numeric inputs directly
    if isinstance(price_input, (float, int)):
        return float(price_input)
    
    # Handle string inputs
    if not price_input:
        return 0.0
        
    cleaned_price = (
        price_input.replace("DZD", "")
        .replace(" DA", "")
        .replace("\xa0", "")
        .strip()
        .replace(" ", "")
        .replace(",", ".")
    )
    
    try:
        return float(cleaned_price)
    except ValueError:
        return 0.0

def traitement_prix(prix_dec, prix_unit):
    if not prix_dec or not prix_unit:
        return None  # Return None instead of 0.0 to indicate missing data
    try:
        prix_dec = float(prix_dec)
        multiplier = 10000 if prix_unit == "Millions" else 10000000 if prix_unit == "Milliards" else 1
        return prix_dec * multiplier
    except ValueError:
        return None

def str_to_float(valeur):
    return float(valeur.replace(",", ".")) if valeur else ""

def str_to_int(valeur):
    return int(valeur) if valeur else ""

def categorie(valeur):
    return CATEGORY_MAP.get(valeur, valeur or "").capitalize()

def is_duplicate_tv(tv_name: str, seen_names: set) -> bool:
    return tv_name in seen_names

def is_complete_tv(tv: dict, required_keys: list) -> bool:
    return all(key in tv for key in required_keys)

import csv
import json
import requests
from urllib.parse import urlparse
from models.tv import Tv

CATEGORY_MAP = {
    "Téléphone portable": "Smartphones",
    "Accessoires & Smartwatches": "Accessoires",
    "TV & Vidéo": "Télévisions",
}

def is_valid_image_url(url):
    """Check if URL points to a valid image resource."""
    try:
        # Skip data URIs and invalid formats
        if url.startswith('data:image'):
            return False
            
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False

        # Verify the URL exists
        response = requests.head(url, timeout=5, allow_redirects=True)
        return response.status_code == 200
    except Exception:
        return False

def normalize_image_url(url):
    """Fix common URL formatting issues"""
    if not isinstance(url, str):
        return url
        
    # Remove size parameters from filename
    url = url.replace("-500x500", "").replace("-300x300", "")
    
    # Fix double extensions
    url = url.replace(".jpg.jpg", ".jpg").replace(".png.png", ".png")
    
    # Convert HTTP to HTTPS
    if url.startswith("http://"):
        url = url.replace("http://", "https://", 1)
    
    return url

def format_tv_data(tv):
    required_fields = [
        "site_origine", "garantie", "garantie_unit", "titre", "description", 
        "couleur", "prix_unit", "prix_dec", "etat", "camera_av", "as_photo", 
        "date_crawl", "camera_ar", "modele", "taille_ecran", "dimension", 
        "poid_unit",  "processor_cores", "images", "categorie", "os", 
        "os_version", "date_verif", "m_interne", "date_depot", "url", "poid", 
        "marque", "type_ecran", "as_prix", 
        "m_interne_unit", "adresse", "livraison", "category", 
        "transaction", "status"
    ]
    
    # Process images first
    raw_images = tv.get("images", [])
    processed_images = []
    
    for img_url in raw_images:
        if isinstance(img_url, str):
            clean_url = normalize_image_url(img_url)
            if is_valid_image_url(clean_url):
                processed_images.append(clean_url)
    
    # Fallback to placeholder if no valid images
    if not processed_images:
        processed_images = []
    
    # Create formatted TV data
    formatted_tv = {field: tv.get(field, "") for field in required_fields}
    formatted_tv["images"] = processed_images
    formatted_tv["as_photo"] = "Avec photo" if processed_images else "Sans photo"
    formatted_tv["as_prix"] = "Avec prix" if tv.get("prix_dec") and float(tv["prix_dec"]) != 0 else "Sans prix"
    formatted_tv["prix_dec"] = process_price(tv.get("prix_dec", 0.0))
    formatted_tv["categorie"] = CATEGORY_MAP.get(tv.get("categorie", ""), tv.get("categorie", "")).capitalize()
    
    return formatted_tv

# Rest of your functions remain the same

def save_tvs_to_csv(tvs: list, filename: str):
    if not tvs:
        print("No TVs to save.")
        return
    try:
        fieldnames = Tv.model_fields.keys()
        with open(filename, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(tvs)
        print(f"Saved {len(tvs)} TVs to '{filename}'.")
    except Exception as e:
        print(f"Error saving to CSV: {e}")

def save_tvs_to_json(tvs, filename):
    seen_names = set()
    processed_tvs = []
    
    for tv in tvs:
        if tv["titre"] not in seen_names:  # Avoid duplicates based on TV name
            seen_names.add(tv["titre"])
            processed_tvs.append(format_tv_data(tv))
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(processed_tvs, f, indent=4, ensure_ascii=False)
    print(f"Saved {len(processed_tvs)} unique TVs to '{filename}'.")
