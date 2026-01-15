from datetime import datetime
import re

class VehicleUtils:
    """
    Utility class for normalizing and processing vehicle data.
    """

    @staticmethod
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

    @staticmethod
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


    @staticmethod
    def format_title(title: str) -> str:
        """Format title to Title Case while keeping known words uppercase."""
        if not title:
            return ""

        # Words that should always stay uppercase
        always_upper = {"TV", "UHD", "LED", "OLED", "QLED", "HD", "4K", "SSD", "USB", "RAM"}
        
        def fix_word(w):
            up = w.upper()
            if up in always_upper:
                return up
            return w.capitalize()

        return " ".join(fix_word(word) for word in re.split(r"\s+", title.strip()))


    @staticmethod
    def format_date(date_obj) -> str:
        """
        Format date to %d/%m/%Y %H:%M:%S.
        Accepts datetime object or string (if it can be parsed).
        """
        if not date_obj:
            return ""
            
        if isinstance(date_obj, str):
            try:
                # Try parsing ISO format first as it's common in this project
                dt = datetime.fromisoformat(date_obj)
                return dt.strftime("%d/%m/%Y %H:%M:%S")
            except ValueError:
                return date_obj # Return original if parsing fails
        
        if isinstance(date_obj, datetime):
            return date_obj.strftime("%d/%m/%Y %H:%M:%S")
            
        return str(date_obj)

    @staticmethod
    def traitement_prix(prix_value, prix_unit):
        """
        Calculate decimal price based on value and unit.
        Handles 'Millions' (x10,000) and 'Milliards' (x10,000,000).
        For these units and foreign currencies, simple decimal parsing is attempted first.
        """
        if not prix_value:
            return 0.0
            
        conversion = {
            "Millions": 10000.0, 
            "Milliards": 10000000.0,
            "DA": 1.0,
            "DZD": 1.0
        }
        
        # Default multiplier is 1
        multiplier = conversion.get(prix_unit, 1.0)
        
        try:
            # If unit is Millions/Milliards or foreign (multiplier == 1 but unit not DA/DZD)
            # We want to support "1.5" or "1,5" as 1.5
            # "DA" usually uses dot as thousand separator (1.200.000), so we skip this for explicit DA/DZD
            is_aggregated_unit = prix_unit in ["Millions", "Milliards"]
            is_foreign_currency = prix_unit not in ["DA", "DZD", ""]
            
            if (is_aggregated_unit or is_foreign_currency):
                val_str = str(prix_value).replace(',', '.').strip()
                # Check if it looks like a simple float (e.g. 1.5, 10.55)
                # If it has spaces like "1 200", float() might fail, so we might need to remove spaces?
                # But usually export prices or millions are "1.5" or "220"
                return float(val_str.replace(" ", "")) * multiplier
        except ValueError:
            pass
            
        try:
            # Fallback to aggressive digit extraction (removes dots/commas completely)
            # Suitable for "1.200.000 DA" -> 1200000
            clean_val = VehicleUtils.clean_price_value(prix_value)
            return float(clean_val * multiplier)
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def clean_price_value(value: str) -> float:
        """
        Extract numeric value from price string.
        Handles: "1 200 000", "1,200,000", "1.200.000"
        """
        if not value:
            return 0.0
        
        # Remove spaces
        clean_val = str(value).replace(" ", "")
        
        # Remove all non-numeric characters except the last dot or comma if it looks like a decimal.
        # However, for simplicity and common cases in this project:
        # Just remove everything that is not a digit.
        
        clean_val = re.sub(r'[^\d]', '', str(value))
        
        try:
            return float(clean_val)
        except ValueError:
            return 0.0

    @staticmethod
    def normalize_km(value: str) -> int:
        """
        Normalize kilometer value to integer.
        """
        if not value:
            return 0
        try:
            # Remove 'km', spaces, and other non-digits
            clean_val = re.sub(r'[^\d]', '', str(value).lower())
            return int(clean_val)
        except ValueError:
            return 0

    @staticmethod
    def normalize_year(value: str) -> int:
        """
        Extract 4-digit year.
        """
        if not value:
            return 0
        try:
            match = re.search(r'\b(19|20)\d{2}\b', str(value))
            if match:
                return int(match.group(0))
            return 0
        except ValueError:
            return 0

    @staticmethod
    def unify_data(data: dict) -> dict:
        """
        Unify data from different scrapers into a standard format.
        """
        unified = {}
        
        # Basic fields
        unified["titre"] = VehicleUtils.format_title(data.get("titre", ""))
        unified["description"] = data.get("description", "")
        unified["numero"] = data.get("numero", "")
        unified["nombre_vues"] = data.get("nombre_vues", "")
        unified["date_depot"] = data.get("date_depot", "")
        unified["site_origine"] = data.get("site_origine", "Unknown")
        unified["categorie"] = data.get("categorie", "Automobiles & Véhicules")
        unified["category"] = data.get("category", "voiture")
        unified["images"] = data.get("images", [])
        unified["url"] = data.get("url", "")
        
        # Vehicle Specs
        # Ensure strings for annee and km as per example
        unified["annee"] = str(VehicleUtils.normalize_year(data.get("annee", "")))
        unified["marque"] = VehicleUtils.format_title(data.get("marque", ""))
        unified["model"] = VehicleUtils.format_title(data.get("model", ""))
        
        # Price
        # Example: "prix": "221 Millions Offert" (string), "prix_value": "221" (string), "prix_dec": 2210000.0 (float)
        unified["prix"] = data.get("prix", "")
        unified["prix_unit"] = data.get("prix_unit", "DA")
        
        # Handle prix_value formatting (remove .0 if integer)
        p_val = data.get("prix_value", "")
        if isinstance(p_val, float) and p_val.is_integer():
            unified["prix_value"] = str(int(p_val))
        else:
            unified["prix_value"] = str(p_val) if p_val != "" else ""
            
        # Calculate prix_dec using the new logic
        # We use the raw price value and unit from data
        unified["prix_dec"] = VehicleUtils.traitement_prix(
            unified["prix_value"], 
            unified["prix_unit"]
        )
        
        unified["adresse"] = data.get("adresse", "")
        unified["wilaya"] = VehicleUtils.format_title(data.get("wilaya", ""))
        unified["commune"] = VehicleUtils.format_title(data.get("commune", ""))
        unified["etat"] = data.get("etat", "Occasion")
        
        unified["date_crawl"] = data.get("date_crawl", datetime.now().isoformat())
        unified["status"] = data.get("status", "200")
        
        # Calculated fields if not present
        if "as_photo" in data:
            unified["as_photo"] = data["as_photo"]
        else:
            imgs = data.get("images", [])
            unified["as_photo"] = "Avec photo" if imgs else "Sans photo"
            
        if "as_prix" in data:
            unified["as_prix"] = data["as_prix"]
        else:
            # Check prix_dec
            p_dec = unified["prix_dec"]
            unified["as_prix"] = "Avec prix" if p_dec > 0 else "Sans prix"
        
        unified["km"] = str(VehicleUtils.normalize_km(data.get("km", "")))
        unified["km_unit"] = data.get("km_unit", "km")
        unified["moteur"] = data.get("moteur", "")
        unified["papers"] = data.get("papers", "")
        unified["couleur"] = VehicleUtils.format_title(data.get("couleur", ""))
        unified["options"] = data.get("options", [])
        unified["energie"] = VehicleUtils.normalize_energie(data.get("energie", ""))
        unified["transmission"] = VehicleUtils.normalize_transmission(data.get("transmission", ""))
        
        # Export logic
        # If currency is NOT Algerian, it is export
        # Algerian units: DA, DZD, Millions, Milliards, or sometimes empty (implies DA)
        algerian_units = {"DA", "DZD", "Millions", "Milliards", ""}
        
        p_unit = unified["prix_unit"].strip() if unified["prix_unit"] else ""
        if p_unit not in algerian_units:
            unified["export"] = "true"
        else:
            unified["export"] = "false"
        
        return unified