import re
import os
import json
from datetime import datetime
from bs4 import BeautifulSoup

class ImmobilierUtils:
    """
    Shared utilities for parsing and normalizing Real Estate (Immobilier) data.
    """

    @staticmethod
    def save_to_json(data: dict, filename: str = "scraped_data.jsonl"):
        """Append one scraped item as a JSON line to a file in the junk_test directory."""
        # Ensure junk_test directory exists
        output_dir = "junk_test"
        os.makedirs(output_dir, exist_ok=True)
        
        # Construct full path
        full_path = os.path.join(output_dir, filename)
        
        with open(full_path, "a", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.write("\n")

    @staticmethod
    def save_listing_file(data: dict, folder: str = "junk_test"):
        """Save a single listing as a pretty JSON file in the project root's junk_test folder."""
        # Calculate project root relative to this file (utils/immobilier.py)
        # Assuming utils/immobilier.py is in the project root or a subfolder
        try:
            # If utils/immobilier.py is at root/utils/immobilier.py, root is ../
            root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            base_dir = os.path.join(root_dir, folder)
        except Exception:
            base_dir = folder
        
        os.makedirs(base_dir, exist_ok=True)

        # Identifier logic
        identifier = "item"
        if isinstance(data.get("numero"), str) and data.get("numero"):
            identifier = re.sub(r"[^0-9A-Za-z_-]", "", data["numero"])[:64]
        else:
            prof = data.get("contact", {}).get("profile_link")
            if prof:
                m = re.search(r"/membre/(\d+)", prof)
                if m:
                    identifier = m.group(1)
            if identifier == "item":
                try:
                    last = os.path.basename(data.get("url", "").rstrip("/"))
                    if last:
                        identifier = re.sub(r"[^0-9A-Za-z_-]", "", last)[:64]
                except Exception:
                    pass
        
        if identifier == "item":
            title = data.get("titre") or "listing"
            identifier = re.sub(r"[^0-9A-Za-z_-]", "", title.replace(" ", "-"))[:64]

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{identifier}.json"
        path = os.path.join(base_dir, filename)
        
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"Saved listing to {path}")
        except Exception as e:
            print(f"Failed to save listing file: {e}")

    @staticmethod
    def parse_float_or_none(text):
        try:
            return float(text.strip())
        except (ValueError, AttributeError):
            return ""

    @staticmethod
    def traitement_prix(prix_dec, prix_unit):
        conversion = {"Millions": 10000, "Milliards": 10000000}
        try:
            val = float(prix_dec)
            return val * conversion.get(prix_unit, 1) if prix_unit else val
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def extract_text_or_default(soup, selector, default=""):
        element = soup.select_one(selector)
        return element.get_text(strip=True) if element else default

    @staticmethod
    def parse_date(date_str):
        try:
            # Try specific format often used
            return datetime.strptime(date_str, '%d/%m/%Y %H:%M:%S').isoformat()
        except ValueError:
            # Return original if parsing fails, or try other formats if needed
            return date_str

    @staticmethod
    def is_essential_data_empty(data):
        return not data.get("titre")

    @staticmethod
    def normalize_url(url):
        return os.path.splitext(url)[0]

    @staticmethod
    def convert_property_type(raw_key):
        valid_types = {
            "Appartement", "Villa", "Local", "Terrain", "Studio", "Hangar",
            "Niveau de villa", "Immeuble", "Duplex", "Carcasse", "Autre",
            "Bungalow", "Terrain agricole", "Usine", "Chalet", "Commerce",
            "Locaux", "Bureau", "Autres", "Salle", "Hostel", "Dortoir",
            "Ferme", "Hotel", "Triplex", "Maison", "Pavillon", "Auberge", "Résidence"
        }

        normalization_map = {
            "bungalow": "Bungalow", "bungalows": "Bungalow",
            "niveau": "Niveau de villa", "niveau de villa": "Niveau de villa",
            "terrain-agricole": "Terrain agricole", "terrain agricole": "Terrain agricole",
            "appartements": "Appartement", "immeubles": "Immeuble",
            "commerce, local": "Commerce", "bureaux": "Bureau",
            "ferme, terrain": "Ferme", "residence": "Résidence", "résidence": "Résidence"
        }

        if not raw_key or not isinstance(raw_key, str):
            return ""

        cleaned = raw_key.strip().lower()
        normalized = normalization_map.get(cleaned, cleaned).capitalize()
        
        if normalized in valid_types:
            return normalized

        for key, value in normalization_map.items():
            if key in cleaned:
                norm = value
                if norm in valid_types:
                    return norm

        for valid in valid_types:
            if valid.lower() in cleaned:
                return valid

        return ""

    @staticmethod
    def detect_transaction_from_title(title: str) -> str:
        """
        Detects the transaction type from the ad title.
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
        return ""
