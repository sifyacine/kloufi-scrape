import re
from datetime import datetime

class VoitureUtils:
    @staticmethod
    def extract_text(soup, selector, default=""):
        """Extract text from a given selector or return a default value."""
        if not soup:
            return default
        try:
            element = soup.select_one(selector)
            return element.get_text(strip=True) if element else default
        except Exception:
            return default

    @staticmethod
    def normalize_fuel(text):
        """Normalize fuel type/energy source."""
        if not text:
            return ""
        
        text_clean = text.strip()
        text_lower = text_clean.lower()
        
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
            "Essence gpl": "GPL",

            # Electrique
            "Electrique": "Electrique",
            "Electric": "Electrique",

            # Hybride
            "Hybride": "Hybride",
            "Hybrid": "Hybride",
            "Hybrid (gasoline/electric)": "Hybride",
            "Hybride (essence/électrique)": "Hybride",
            "Hybride (diesel/électrique)": "Hybride",
            "Essence hybrid électrique": "Essence / Hybride / Electrique",
            "Essence hybride": "Essence / Hybride",
            "Essence hybrid": "Essence / Hybride",

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
        
        # Direct lookup (case-sensitive keys mostly, apart from custom logic below)
        if text_clean in mapping:
            return mapping[text_clean]

        # Case-insensitive partial matching for messy inputs
        if "essence" in text_lower and "gpl" in text_lower:
            return "GPL"
        if "hybrid" in text_lower or "hybride" in text_lower:
            return "Hybride"
        if "electrique" in text_lower or "electric" in text_lower:
            return "Electrique"
        if "diesel" in text_lower:
            return "Diesel"
        if "essence" in text_lower or "gasoline" in text_lower or "petrol" in text_lower:
            return "Essence"
            
        return "Multi-énergie"

    @staticmethod
    def normalize_transmission(text):
        """Normalize transmission type."""
        if not text:
            return ""

        val_upper = text.strip().upper()
        
        # Checking for specific keywords
        if val_upper in ["AT", "DCT", "CVT", "E-CVT", "DHT", "AMT", "TCT", "E-CVT+AT", "ISR"]:
            return "Automatique"
            
        if "SEMI" in val_upper:
            return "Semi-Automatique"
            
        if "AUTOMATIQUE" in val_upper or "AUTOMATIC" in val_upper:
            return "Automatique"
            
        if "MANUELLE" in val_upper or "MANUAL" in val_upper or "MÉCANIQUE" in val_upper or "MT" == val_upper:
            return "Manuelle"
            
        return text.strip()

    @staticmethod
    def parse_price(price_raw, unit_raw=None):
        """
        Convert price to its decimal value, handling units like Millions/Milliards.
        Returns (price_display, price_value_str, price_decimal, unit)
        """
        if not price_raw:
            return "", "", 0, "DA"
            
        # Clean up price value string (remove spaces)
        price_val_str = re.sub(r"[^\d.,]", "", str(price_raw)).replace(",", ".")
        
        try:
            price_float = float(price_val_str)
        except ValueError:
            price_float = 0.0

        conversion = 1
        if unit_raw:
            unit_clean = unit_raw.strip().lower()
            if "million" in unit_clean:
                conversion = 10000
            elif "milliard" in unit_clean:
                conversion = 10000000
        
        final_price = price_float * conversion
        
        # Construct display string
        parts = [price_val_str]
        if unit_raw:
            parts.append(unit_raw.strip())
        
        return " ".join(parts), price_val_str, final_price, unit_raw if unit_raw else "DA"

    @staticmethod
    def normalize_mileage(text):
        """Extract numeric mileage and unit."""
        if not text:
            return "", "KM"
        
        kms_value = ''.join(filter(str.isdigit, text))
        
        # Guess unit
        unit = "KM"
        if "mi" in text.lower():
            unit = "Miles"
            
        return kms_value, unit

    @staticmethod
    def parse_date(date_str):
        """Try to parse a date string into ISO format."""
        if not date_str or date_str == "Date":
            return ""
            
        # Try common formats
        formats = [
            '%d/%m/%Y %H:%M:%S',
            '%d-%m-%Y %H:%M:%S',
            '%Y-%m-%d %H:%M:%S',
            '%d/%m/%Y',
            '%Y-%m-%d'
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).isoformat()
            except ValueError:
                continue
                
        return ""
