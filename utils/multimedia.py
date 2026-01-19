# utils/multimedia.py - Unified utility class for multimedia scrapers

import re
from datetime import datetime


class MultimediaUtils:
    """
    Unified utility class for multimedia/electronics scraping and normalization.
    Provides common functions for price, category, brand, specs extraction.
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
        Convert string to float, removing commas, spaces, 'د.ج', 'DA'.
        Returns 0.0 if conversion fails.
        """
        if not valeur:
            return 0.0
        try:
            valeur = str(valeur).replace(",", "").replace("د.ج", "").replace("DA", "").replace(" ", "").strip()
            return float(valeur)
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
        """Standardize category names for multimedia products"""
        if not valeur:
            return ""
        
        valeur_lower = valeur.lower()
        
        # Téléphones
        if "téléphone" in valeur_lower or "portable" in valeur_lower or "smartphone" in valeur_lower:
            return "Smartphones"
        
        # Ordinateurs
        elif "desktop" in valeur_lower or "pc de bureau" in valeur_lower:
            return "Desktop PCs"
        elif "laptop" in valeur_lower or "ordinateur portable" in valeur_lower:
            return "Laptops"
        
        # Accessoires
        elif "accessoire" in valeur_lower or "smartwatch" in valeur_lower:
            return "Accessoires"
        
        # Tablettes
        elif "tablet" in valeur_lower or "tablette" in valeur_lower:
            return "Tablettes"
        
        # Default
        else:
            return valeur

    # ==================== BRAND & MODEL EXTRACTION ====================
    
    @staticmethod
    def extract_brand(text):
        """
        Extract brand from title or description.
        Supports common brands: Apple, Samsung, Lenovo, HP, Dell, etc.
        """
        if not text:
            return ""
        
        brands = [
            "APPLE", "SAMSUNG", "LENOVO", "HP", "DELL", "ASUS", "ACER", 
            "MSI", "SONY", "KONICA", "HUAWEI", "XIAOMI", "OPPO", "VIVO",
            "REALME", "ONEPLUS", "NOKIA", "MOTOROLA", "LG", "GOOGLE",
            "MICROSOFT", "RAZER", "ALIENWARE"
        ]
        
        text_upper = text.upper()
        
        # Try exact match at start
        brand_match = re.search(r'^(' + '|'.join(brands) + r')\b', text, re.IGNORECASE)
        if brand_match:
            return brand_match.group(1).upper()
        
        # Try anywhere in text
        for brand in brands:
            if brand in text_upper:
                return brand
        
        return ""

    @staticmethod
    def extract_model(text):
        """
        Extract model from title or description.
        Handles iPhone, MacBook, PlayStation, Galaxy, etc.
        """
        if not text:
            return ""
        
        patterns = [
            r'iPhone\s+\d+\s*(?:Pro\s*Max|Pro)?',
            r'MacBook\s*\w+',
            r'PlayStation\s*\d',
            r'Galaxy\s*[A-Z]\d+',
            r'Redmi\s*\d+[A-Z]?',
            r'KM\d+i?\s*[A-Z\-]+',
            r'Pavilion\s*\w+',
            r'ThinkPad\s*\w+',
            r'Latitude\s*\d+',
            r'Inspiron\s*\d+',
        ]
        
        for pattern in patterns:
            model_match = re.search(pattern, text, re.IGNORECASE)
            if model_match:
                return model_match.group(0)
        
        return ""

    # ==================== TECHNICAL SPECS EXTRACTION ====================
    
    @staticmethod
    def extract_ram(text):
        """
        Extract RAM from text.
        Returns tuple (value, unit) e.g. ('8', 'GB')
        """
        if not text:
            return ("", "")
        
        patterns = [
            r'RAM\s*:?\s*(\d+)\s*(GO|GB)',
            r'(\d+)\s*(GO|GB)\s*RAM',
            r'(\d+)\s*(GO|GB)\s*DDR\d',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return (match.group(1), "GB")
        
        return ("", "")

    @staticmethod
    def extract_storage(text):
        """
        Extract internal storage from text.
        Returns tuple (value, unit) e.g. ('256', 'GB')
        """
        if not text:
            return ("", "")
        
        patterns = [
            r'Storage\s*:?\s*(?:M\.2\s*NVME\s*)?(\d+)\s*(GB|TB)',
            r'(\d+)\s*(GB|TB)\s*(?:SSD|M\.2|NVME)',
            r'Capacité\s*(?:\(\w+\))?\s*:?\s*(\d+)\s*(GB|TB)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return (match.group(1), match.group(2))
        
        return ("", "")

    @staticmethod
    def extract_processor(text):
        """
        Extract processor information from text.
        Returns processor string with speed if available.
        """
        if not text:
            return ""
        
        patterns = [
            r'(?:CPU|Processor)\s*:?\s*([^\(]+)(?:\s*\((\d+\.?\d*\s*GHz)\))?',
            r'(?:Intel\s*[iI][3579](?:-\d{4,5}(?:KF)?)|RYZEN\s*[3579]\s*\d{4}(?:X)?|CORE\s*ULTRA\s*[3579]\s*\d+[K]?)',
            r'(Quad-Core|Octa-Core)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if len(match.groups()) > 1 and match.group(2):
                    return f"{match.group(1).strip()} ({match.group(2)})"
                return match.group(0).strip()
        
        return ""

    @staticmethod
    def extract_screen_size(text):
        """
        Extract screen size in inches from text.
        Returns value as string e.g. '15.6'
        """
        if not text:
            return ""
        
        patterns = [
            r'Taille\s*(?:de\s*l\')?écran\s*(?:\(pouces\))?\s*:?\s*([\d\.]+)',
            r'([\d\.]+)\s*(?:inch|pouces|")',
            r'(\d{2}\.?\d*)\s*[″"]',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return ""

    @staticmethod
    def extract_os(text):
        """
        Extract operating system from text.
        Returns tuple (os_name, os_version) e.g. ('Windows', '11')
        """
        if not text:
            return ("", "")
        
        patterns = [
            (r'Windows\s*(\d{1,2}(?:\.?\d*)?)', 'Windows'),
            (r'macOS\s*(\d{1,2}(?:\.?\d*)?)', 'macOS'),
            (r'iOS\s*(\d{1,2}(?:\.?\d*)?)', 'iOS'),
            (r'Android\s*(\d{1,2}(?:\.?\d*)?)', 'Android'),
            (r'Linux', 'Linux'),
            (r'Ubuntu', 'Ubuntu'),
            (r'Chrome\s*OS', 'Chrome OS'),
        ]
        
        for pattern, os_name in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if len(match.groups()) > 0:
                    return (os_name, match.group(1))
                return (os_name, "")
        
        return ("", "")

    @staticmethod
    def extract_warranty(text):
        """
        Extract warranty information from text.
        Returns tuple (duration, unit) e.g. ('2', 'ans')
        """
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
                unit = "ans"  # Default
            
            return (duration, unit)
        
        return ("", "")

    @staticmethod
    def extract_camera(text):
        """
        Extract camera megapixels from text.
        Returns tuple (rear_camera, front_camera) in MP
        """
        rear = ""
        front = ""
        
        if not text:
            return (rear, front)
        
        # Rear camera
        rear_match = re.search(r'(?:caméra arrière|rear camera|arrière)\s*:?\s*(\d+(?:\.\d+)?)\s*(?:MP|Mégapixels)', text, re.IGNORECASE)
        if rear_match:
            rear = rear_match.group(1)
        
        # Front camera
        front_match = re.search(r'(?:caméra avant|front camera|avant|selfie)\s*:?\s*(\d+(?:\.\d+)?)\s*(?:MP|Mégapixels)', text, re.IGNORECASE)
        if front_match:
            front = front_match.group(1)
        
        return (rear, front)

    @staticmethod
    def extract_battery(text):
        """
        Extract battery capacity in mAh from text.
        Returns value as string e.g. '5000'
        """
        if not text:
            return ""
        
        match = re.search(r'(\d+)\s*mAh', text, re.IGNORECASE)
        return match.group(1) if match else ""

    # ==================== DATE UTILITIES ====================
    
    @staticmethod
    def str_to_date(valeur):
        """
        Convert date string in format 'DD Month YYYY HH:MM' to ISO format 'YYYY-MM-DD'.
        Handles French and English month names.
        """
        if not valeur:
            return ""
        
        try:
            # Remove 'Publiée le:' prefix
            valeur = valeur.replace("Publiée le:", "").strip()
            
            # Month mapping
            month_map = {
                "jan": "Jan", "janvier": "Jan", "fév": "Feb", "février": "Feb", 
                "mar": "Mar", "mars": "Mar", "avr": "Apr", "avril": "Apr", 
                "mai": "May", "juin": "Jun", "juil": "Jul", "juillet": "Jul",
                "aoû": "Aug", "août": "Aug", "sep": "Sep", "sept": "Sep", 
                "oct": "Oct", "octobre": "Oct", "nov": "Nov", "novembre": "Nov", 
                "déc": "Dec", "décembre": "Dec"
            }
            
            valeur_lower = valeur.lower()
            for fr, en in month_map.items():
                valeur_lower = valeur_lower.replace(fr.lower(), en.lower())
            
            # Normalize format
            valeur_lower = re.sub(r'[-–—]', ' ', valeur_lower)
            valeur_lower = re.sub(r'(\d{4})(\d{2}:\d{2})', r'\1 \2', valeur_lower)
            
            # Extract date components
            date_match = re.match(r'(\d{1,2})\s+([a-zA-Z]+)\s+(?:(?:(\d{4})\s+)?(\d{1,2}:\d{2}))', valeur_lower)
            if not date_match:
                return ""
            
            day, month, year, time = date_match.groups()
            month = month.capitalize()
            current_year = datetime.now().year
            year = year if year else str(current_year)
            
            # Parse the date
            date_str = f"{day} {month} {time} {year}"
            date_obj = datetime.strptime(date_str, "%d %b %H:%M %Y")
            
            # If parsed date is in future, assume previous year
            if date_obj > datetime.now():
                date_obj = date_obj.replace(year=int(year) - 1)
            
            return date_obj.strftime("%Y-%m-%d")
        except (ValueError, IndexError):
            return ""

    # ==================== CONDITION/STATE ====================
    
    @staticmethod
    def normalize_etat(titre, description=""):
        """
        Determine product condition: 'New' or 'Renewed' (Used/Occasion)
        """
        text = f"{titre} {description}".lower()
        
        if any(word in text for word in ["occasion", "used", "reconditionné", "renewed"]):
            return "Renewed"
        
        return "New"
