# utils/electromenager.py - Unified utility class for electromenager scrapers

import re
from datetime import datetime


class ElectromenagerUtils:
    """
    Unified utility class for electromenager (home appliances) scraping and normalization.
    Provides common functions for price, category, brand, specifications extraction.
    """

    # ==================== PRICE UTILITIES ====================
    
    @staticmethod
    def traitement_prix(prix_dec, prix_unit):
        """
        Convert price to DA based on unit.
        - "Millions": multiply by 10,000
        - "Milliards": multiply by 10,000,000
        Returns 0.0 if conversion fails.
        """
        if prix_dec and prix_unit:
            try:
                value = float(prix_dec)
                if prix_unit == "Millions":
                    return value * 10000
                elif prix_unit == "Milliards":
                    return value * 10000000
                else:
                    return value
            except ValueError:
                return 0.0
        return 0.0

    @staticmethod
    def str_to_float(valeur):
        """
        Convert string to float, removing commas, spaces, 'د.ج', 'DA', 'DZD'.
        Returns 0.0 if conversion fails.
        """
        if not valeur:
            return 0.0
        try:
            valeur = str(valeur).replace(",", "").replace("د.ج", "").replace("DA", "").replace("DZD", "").replace(" ", "").replace("\xa0", "").strip()
            return float(valeur)
        except ValueError:
            return 0.0

    @staticmethod
    def process_price(price_string):
        """Clean and convert price string to float"""
        if not price_string:
            return 0.0
        cleaned_price = price_string.replace("DZD", "").replace("Da", "").replace("DA", "").replace("\xa0", "").replace(" ", "").strip()
        cleaned_price = cleaned_price.replace(",", ".")
        try:
            return float(cleaned_price)
        except ValueError:
            return 0.0

    @staticmethod
    def avec_sans_prix(prix_dec, prix_unit):
        """Return 'Avec prix' if both price parts provided and non-zero, else 'Sans prix'"""
        try:
            if prix_dec and prix_unit and float(prix_dec) != 0:
                return "Avec prix"
        except ValueError:
            pass
        return "Sans prix"

    @staticmethod
    def avec_sans_photo(image):
        """Return 'Avec photo' if image string non-empty, else 'Sans photo'"""
        return "Avec photo" if str(image).strip() else "Sans photo"

    # ==================== CATEGORY NORMALIZATION ====================
    
    @staticmethod
    def normalize_categorie(valeur):
        """Standardize category names for home appliances"""
        if not valeur:
            return ""
        
        valeur_lower = valeur.lower()
        
        if any(word in valeur_lower for word in ["réfrigér", "refriger", "frigo", "congélateur", "freezer"]):
            return "Réfrigérateurs & Congélateurs"
        elif any(word in valeur_lower for word in ["machine à laver", "lave-linge", "washing machine", "sèche-linge", "dryer"]):
            return "Machines à Laver & Sèche-linge"
        elif any(word in valeur_lower for word in ["cuisinière", "four", "oven", "plaque", "cooktop", "hotte"]):
            return "Cuisinières & Fours"
        elif any(word in valeur_lower for word in ["lave-vaisselle", "dishwasher"]):
            return "Lave-vaisselle"
        elif "micro" in valeur_lower or "microwave" in valeur_lower:
            return "Micro-ondes"
        elif any(word in valeur_lower for word in ["bouilloire", "kettle", "grille-pain", "toaster", "mixeur", "blender", "robot", "cafetière"]):
            return "Petit Électroménager"
        elif any(word in valeur_lower for word in ["aspirateur", "vacuum"]):
            return "Aspirateurs"
        elif any(word in valeur_lower for word in ["climatiseur", "climatisation", "air conditioner"]):
            return "Climatisation"
        elif any(word in valeur_lower for word in ["chauffe-eau", "water heater"]):
            return "Chauffe-eau"
        else:
            return valeur.title()

    # ==================== BRAND EXTRACTION ====================
    
    @staticmethod
    def extract_brand(text):
        """Extract appliance brand from title or description"""
        if not text:
            return ""
        
        brands = [
            "SAMSUNG", "LG", "WHIRLPOOL", "BOSCH", "SIEMENS", "ELECTROLUX",
            "HAIER", "BEKO", "ARISTON", "INDESIT", "CANDY", "HOTPOINT",
            "MIELE", "AEG", "ZANUSSI", "BAUKNECHT", "GORENJE",
            "TEFAL", "MOULINEX", "PHILIPS", "KENWOOD", "BRAUN", "KRUPS",
            "DELONGHI", "MAGIMIX", "RUSSELL HOBBS",
            "CONDOR", "IRIS", "CRISTOR", "STARMANIA", "EWTEC",
            "TOSHIBA", "SHARP", "PANASONIC", "HITACHI", "MIDEA",
            "HISENSE", "TCL", "GREE", "CARRIER"
        ]
        
        text_upper = text.upper()
        brand_match = re.search(r'^(' + '|'.join(brands) + r')\b', text, re.IGNORECASE)
        if brand_match:
            return brand_match.group(1).upper()
        
        for brand in brands:
            if brand in text_upper:
                return brand
        
        return ""

    @staticmethod
    def extract_model(text):
        """Extract model from title or description"""
        if not text:
            return ""
        
        patterns = [
            r'[A-Z]{2,4}[-\s]?\d{3,5}[A-Z]*',
            r'\b\d{3,5}[A-Z]{1,3}\b',
            r'[A-Z]+\s*\d{2,4}',
        ]
        
        for pattern in patterns:
            model_match = re.search(pattern, text, re.IGNORECASE)
            if model_match:
                return model_match.group(0).strip()
        
        return ""

    # ==================== TECHNICAL SPECS EXTRACTION ====================
    
    @staticmethod
    def extract_capacity(text):
        """Extract capacity (L, kg). Returns (value, unit)"""
        if not text:
            return ("", "")
        
        patterns = [
            r'(?:Capacité|Capacity)\s*:?\s*(\d+(?:\.\d+)?)\s*(L|Litre|litres?|kg|KG)',
            r'(\d+(?:\.\d+)?)\s*(L|Litre|litres?|kg|KG)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                unit = match.group(2).upper()
                if unit in ["LITRE", "LITRES"]:
                    unit = "L"
                elif unit in ["KG"]:
                    unit = "kg"
                return (match.group(1), unit)
        
        return ("", "")

    @staticmethod
    def extract_energy_class(text):
        """Extract energy efficiency class (A+++, A++, etc.)"""
        if not text:
            return ""
        
        pattern = r'\b(A\+\+\+|A\+\+|A\+|A|B|C|D|E|F|G)\b'
        match = re.search(pattern, text, re.IGNORECASE)
        
        return match.group(1).upper() if match else ""

    @staticmethod
    def extract_power(text):
        """Extract power in Watts. Returns (value, unit)"""
        if not text:
            return ("", "")
        
        patterns = [
            r'(?:Puissance|Power)\s*:?\s*(\d+(?:\.\d+)?)\s*(W|Watt|Watts|KW)',
            r'(\d+(?:\.\d+)?)\s*(W|Watt|Watts|KW)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                unit = "W" if match.group(2).upper() in ["W", "WATT", "WATTS"] else "KW"
                return (match.group(1), unit)
        
        return ("", "")

    @staticmethod
    def extract_dimensions(text):
        """Extract dimensions. Returns formatted string"""
        if not text:
            return ""
        
        patterns = [
            r'(\d{1,3}(?:\.\d+)?)\s*[xX×]\s*(\d{1,3}(?:\.\d+)?)\s*[xX×]\s*(\d{1,3}(?:\.\d+)?)\s*cm',
            r'(?:Dimensions|Dimension)\s*:?\s*(\d{1,3})\s*[xX×]\s*(\d{1,3})\s*[xX×]\s*(\d{1,3})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return f"{match.group(1)} x {match.group(2)} x {match.group(3)} cm"
        
        return ""

    @staticmethod
    def extract_weight(text):
        """Extract weight. Returns (value, unit)"""
        if not text:
            return ("", "")
        
        patterns = [
            r'(?:Poids|Weight)\s*:?\s*([\d\.]+)\s*(kg|Kg|KG|g)',
            r'([\d\.]+)\s*(kg|Kg|KG)\b',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return (match.group(1).replace(",", "."), match.group(2).lower())
        
        return ("", "")

    @staticmethod
    def extract_color(text):
        """Extract color/couleur"""
        if not text:
            return ""
        
        colors = {
            "blanc": "Blanc", "white": "Blanc",
            "noir": "Noir", "black": "Noir",
            "gris": "Gris", "gray": "Gris", "grey": "Gris",
            "silver": "Silver", "argent": "Silver",
            "inox": "Inox", "stainless": "Inox",
            "rouge": "Rouge", "red": "Rouge",
            "bleu": "Bleu", "blue": "Bleu"
        }
        
        text_lower = text.lower()
        for french, standard in colors.items():
            if french in text_lower:
                return standard
        
        return ""

    @staticmethod
    def extract_warranty(text):
        """Extract warranty. Returns (duration, unit)"""
        if not text:
            return ("", "")
        
        pattern = r'(?:Warranty|Garantie)\s*:?\s*(\d+)\s*(Year|Years|Month|Months|Mois|Ans|سنة)?'
        match = re.search(pattern, text, re.IGNORECASE)
        
        if match:
            duration = match.group(1)
            unit_raw = match.group(2).lower() if match.group(2) else ''
            
            if unit_raw in ["year", "years", "ans", "سنة"]:
                unit = "ans"
            elif unit_raw in ["month", "months", "mois"]:
                unit = "mois"
            else:
                unit = "ans"
            
            return (duration, unit)
        
        return ("", "")

    # ==================== CONDITION/STATE ====================
    
    @staticmethod
    def normalize_etat(titre, description=""):
        """Determine condition: 'Neuf' or 'Occasion'"""
        text = f"{titre} {description}".lower()
        
        if any(word in text for word in ["occasion", "used", "reconditionné", "renewed", "seconde main"]):
            return "Occasion"
        
        return "Neuf"
