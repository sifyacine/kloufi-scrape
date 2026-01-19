from datetime import datetime, timedelta
import re


class EmploiUtils:
    """
    Shared utility functions for emploi (job) scrapers.
    Provides standardized data extraction and normalization methods.
    """

    @staticmethod
    def normalize_domaine(domaine):
        """
        Normalizes job domain/sector names to standardized categories.
        
        Args:
            domaine: Raw domain/sector string
            
        Returns:
            Standardized domain name or "Autre" if not found
        """
        domaine_clean = domaine.strip() if domaine else ""
        mapping = {
            'Accueil/Secrétariat/Administration': 'Bureautique & Secretariat',
            'Agriculture/Environnement/Espaces Verts': 'Services',
            'Automobile': 'Achat & Logistique',
            'Banque/Finance/Assurance': 'Comptabilité & Audit',
            'Biologie/Chimie/Pharmaceutique': 'Recherche & developpement',
            'Commerce/Artisanat': 'Commerce & Vente',
            'Commercial/Vente': 'Commerce & Vente',
            'Comptabilité/Gestion/Audit': 'Comptabilité & Audit',
            'Construction/Btp': 'Construction & Travaux',
            'Droit/Justice/Association': 'Juridique',
            'Education/Social/Petite Enfance': 'Services',
            'Entreprise/Import/Export': 'Achat & Logistique',
            'Fitness/Coach/Club Sportif': 'Services',
            'Grande Distribution': 'Commerce & Vente',
            'Immobilier': 'Services',
            'Industrie/Ingénierie/Energie': 'Industrie & Production',
            'Informatique/Multimédia/Internet': 'Informatique & Internet',
            'International/Télécommunication': 'Informatique & Internet',
            'Maintenance/Entretien': 'Services',
            'Marketing/Communication/Publicité/Rp': 'Commercial & Marketing',
            'Mode/Luxe/Beauté': 'Commercial & Marketing',
            'Médias/Art/Culture': 'Services',
            'Ressources Humaines/Recrutement/Intérim': 'Administration & Management',
            'Santé/Médical': 'Medecine & Santé',
            'Secteur Public': 'Administration & Management',
            'Services aux Entreprises/Formation': 'Services',
            'Services à La Personne': 'Services',
            'Sécurité/Surveillance /Gardiennage': 'Services',
            'Tourisme/Hotellerie/Restauration': 'Tourisme & Gastronomie',
            'Transport /Achat/Logistique': 'Achat & Logistique',
            'Urbanisme/Architecture/Aménagement': 'Construction & Travaux',
            'Édition/Imprimerie/Journalisme': 'Services',
        }
        return mapping.get(domaine_clean, "Autre")

    @staticmethod
    def normalize_diplome(diplome):
        """
        Normalizes diploma/education level to standardized categories.
        
        Args:
            diplome: Raw diploma/education string
            
        Returns:
            Standardized diploma name or None for "no diploma" cases
        """
        if not diplome:
            return None
            
        mapping = {
            "niveau secondaire": "Diplome de collège",
            "niveau terminal": "Diplome de collège",
            "baccalauréat": "Bac",
            "bac +2": "Diplome universitaire",
            "ts bac +2": "Diplome universitaire",
            "ts bac +2 | formation professionnelle": "Diplôme professionnel / téchnique",
            "licence": "Diplome universitaire",
            "licence (lmd), bac + 3": "Diplome universitaire",
            "licence bac + 4": "Diplome universitaire",
            "bac + 3": "Diplome universitaire",
            "bac+3": "Diplome universitaire",
            "master 1": "Master",
            "master 1, licence  bac + 4": "Diplome universitaire",
            "master 2, ingéniorat, bac + 5": "Diplome universitaire",
            "master 2": "Master",
            "ingéniorat": "Diplome universitaire",
            "bac + 5": "Diplome universitaire",
            "magistère bac + 7": "Diplome universitaire",
            "doctorat": "Doctorat",
            "certification": "Diplôme professionnel / téchnique",
            "formation professionnelle": "Diplôme professionnel / téchnique",
            "universitaire sans diplôme": "Diplôme professionnel / téchnique",
            "non diplômante": None,
            "sans diplôme": None,
            "sans diplome": None,
            "pas important": None,
        }
        return mapping.get(diplome.lower() if diplome else "", diplome)

    @staticmethod
    def normalize_date(date_text):
        """
        Normalizes various date formats to YYYY-MM-DD.
        
        Handles:
        - ISO format (YYYY-MM-DD)
        - Relative dates (il y a X jour/semaine/mois/an)
        - French month names
        - "Aujourd'hui", "Hier"
        
        Args:
            date_text: Raw date string
            
        Returns:
            Normalized date in YYYY-MM-DD format or original text if parsing fails
        """
        if not date_text:
            return ""
        
        # Try ISO format first
        try:
            return datetime.fromisoformat(date_text).strftime('%Y-%m-%d')
        except:
            pass

        # Handle schema.org dates with time
        if 'T' in date_text:
            try:
                return datetime.strptime(date_text.split('T')[0], '%Y-%m-%d').strftime('%Y-%m-%d')
            except:
                pass

        # Handle "4 Apr-10:24" format (assume current year)
        month_match = re.search(r'(\d{1,2})\s+([a-zA-Z]{3})', date_text)
        if month_match:
            day, month = month_match.groups()
            current_year = datetime.now().year
            try:
                return datetime.strptime(f"{day} {month} {current_year}", "%d %b %Y").strftime('%Y-%m-%d')
            except:
                pass

        # Existing relative date handling
        date_text_clean = re.sub(r'\s+', ' ', date_text.lower().strip())
        patterns = [
            (r'il y a (\d+) jour', 'days'),
            (r'il y a (\d+) semaine', 'weeks'),
            (r'il y a (\d+) mois', 'months'),
            (r'il y a (\d+) an', 'years'),
            (r'aujourd', 'today'),
            (r'hier', 'yesterday')
        ]

        today = datetime.now()
        for pattern, unit in patterns:
            match = re.search(pattern, date_text_clean)
            if match:
                if unit == 'today':
                    return today.strftime('%Y-%m-%d')
                if unit == 'yesterday':
                    return (today - timedelta(days=1)).strftime('%Y-%m-%d')
                if match:
                    value = int(match.group(1))
                    if unit == 'days':
                        return (today - timedelta(days=value)).strftime('%Y-%m-%d')
                    elif unit == 'weeks':
                        return (today - timedelta(weeks=value)).strftime('%Y-%m-%d')
                    elif unit == 'months':
                        return (today - timedelta(days=value*30)).strftime('%Y-%m-%d')
                    elif unit == 'years':
                        return (today - timedelta(days=value*365)).strftime('%Y-%m-%d')
        
        return date_text

    @staticmethod
    def extract_wilaya(address):
        """
        Extracts wilaya (region) from address string.
        
        Args:
            address: Full address string
            
        Returns:
            Wilaya name or special handling for remote work
        """
        if not address or address.lower() == "télétravail":
            return "Télétravail"
        parts = [p.strip() for p in address.split(',')]
        return parts[0] if parts else "N/A"

    @staticmethod
    def extract_salary(text):
        """
        Extracts salary information from text.
        
        Args:
            text: Text containing potential salary information
            
        Returns:
            Tuple of (amount, unit) or ("", "") if not found
        """
        if not text:
            return "", ""
        pattern = r'(\d[\d\s]*\d?)\s*(DA|DZD|dinars?)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount = re.sub(r'\s', '', match.group(1))
            return amount, "DA"
        return "", ""

    @staticmethod
    def extract_diplome_from_description(description):
        """
        Extracts diploma/education requirements from job description text.
        
        Args:
            description: Job description text
            
        Returns:
            List of extracted diploma-related text segments
        """
        if not description:
            return []
            
        diploma_keywords = [
            "diplôme en", "diplôme d'", "diplôme de",
            "titulaire d'un", "titulaire de", "titulaire du",
            "bac +", "bac+", "licence", "master", "doctorat",
            "formation en", "formation d'", "formation de",
            "niveau d'étude", "niveau étude"
        ]
        
        diplomes = []
        sentences = re.split(r'[.;\n]', description)
        for sentence in sentences:
            for keyword in diploma_keywords:
                if keyword.lower() in sentence.lower():
                    diplomes.append(sentence.strip())
                    break

        diploma_patterns = [
            r'[Tt]itulaire\s+d\'un\s+([^,\.;]+)',
            r'[Bb]ac\s*\+\s*(\d+)',
            r'[Nn]iveau\s+(d\'études|d\'étude)\s*:\s*([^\n.;]+)'
        ]
        
        for pattern in diploma_patterns:
            matches = re.findall(pattern, description, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    diplomes.extend([m.strip() for m in match if m.strip()])
                else:
                    diplomes.append(match.strip())
        
        return list(set(diplomes))
