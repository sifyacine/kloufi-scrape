import re
import json
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
import sys
sys.path.insert(1, '../../global')

def normalize_domaine(domaine):
    # Convert to lowercase and strip whitespace for robust matching
    domaine_clean = domaine.strip()
    mapping = {
        'Accueil/Secrétariat/Administration':        'Bureautique & Secretariat',
        'Agriculture/Environnement/Espaces Verts':    'Services',
        'Automobile':                                     'Achat & Logistique',
        'Banque/Finance/Assurance':                   'Comptabilité & Audit',
        'Biologie/Chimie/Pharmaceutique':             'Recherche & developpement',
        'Commerce/Artisanat':                           'Commerce & Vente',
        'Commercial/Vente':                             'Commerce & Vente',
        'Comptabilité/Gestion/Audit':                 'Comptabilité & Audit',
        'Construction/Btp':                             'Construction & Travaux',
        'Droit/Justice/Association':                  'Juridique',
        'Education/Social/Petite Enfance':            'Services',
        'Entreprise/Import/Export':                   'Achat & Logistique',
        'Fitness/Coach/Club Sportif':                 'Services',
        'Grande Distribution':                            'Commerce & Vente',
        'Immobilier':                                     'Services',
        'Industrie/Ingénierie/Energie':               'Industrie & Production',
        'Informatique/Multimédia/Internet':           'Informatique & Internet',
        'International/Télécommunication':              'Informatique & Internet',
        'Maintenance/Entretien':                        'Services',
        'Marketing/Communication/Publicité/Rp':     'Commercial & Marketing',
        'Mode/Luxe/Beauté':                           'Commercial & Marketing',
        'Médias/Art/Culture':                         'Services',
        'Ressources Humaines/Recrutement/Intérim':    'Administration & Management',
        'Santé/Médical':                                'Medecine & Santé',
        'Secteur Public':                                 'Administration & Management',
        'Services aux Entreprises/Formation':           'Services',
        'Services à La Personne':                         'Services',
        'Sécurité/Surveillance /Gardiennage':          'Services',
        'Tourisme/Hotellerie/Restauration':           'Tourisme & Gastronomie',
        'Transport /Achat/Logistique':                 'Achat & Logistique',
        'Urbanisme/Architecture/Aménagement':         'Construction & Travaux',
        'Édition/Imprimerie/Journalisme':             'Services',
    }
    return mapping.get(domaine_clean, "Autre")  # Return Autre

def normalize_diplome(diplome):
    mapping = {
        "niveau secondaire": "Diplome de collège",
        "niveau terminal": "Diplome de collège",
        "baccalauréat": "Bac",
        "bac +2": "Diplome universitaire",
        "ts bac +2": "Diplome universitaire",
        "ts bac +2 | Formation Professionnelle": "Diplôme professionnel / téchnique",
        "licence": "Diplome universitaire",
        "licence (lmd), bac + 3": "Diplome universitaire",
        "licence bac + 4": "Diplome universitaire",
        "bac + 3": "Diplome universitaire",
        "bac+3": "Diplome universitaire",
        "master 1": "Master",
        "master 1, licence  bac + 4": "Diplome universitaire",
        "master 2, ingéniorat, bac + 5": "Diplome universitaire",
        "baster 2": "Master",
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

def normalize_date(date_text):
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
    date_text = re.sub(r'\s+', ' ', date_text.lower().strip())
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
        match = re.search(pattern, date_text)
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

def extract_diplome_from_description(description):
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

async def extract_job_details(url, entry_data=None):
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
                delay_before_return_html=5
            )
        )
        if not result.success:
            return {"error": f"Failed to load page: {result.error_message}"}

        soup = BeautifulSoup(result.html, "html.parser")
        job_details = {
            "date_crawl": datetime.now().strftime('%Y-%m-%d'),
            "url": url,
            "site_origine": "algerieannonces.com",
            "titre": "",
            "niveau": [],
            "numero": url.split('/')[-1].split('.')[0],
            "date_depot": "",
            "transaction": "Offres",
            "contrat": "",
            "diplome": [],
            "diplome_src": [],
            "domaine": "",
            "description": "",
            "employeur": "",
            "poste": "",
            "adresse": "",
            "wilaya": "",
            "status": 200,
            "date_verif": datetime.now().strftime('%Y-%m-%d'),
            "images": [],
            "as_photo": "Sans photo",
            "prix": "",
            "prix_unit": "",
            "prix_dec": "",
            "as_prix": "Sans prix",
            "vehicle": "False"
        }

        # Extract from JSON-LD
        script_tag = soup.find('script', type='application/ld+json')
        if script_tag:
            try:
                data = json.loads(script_tag.string)
                if data.get('@type') == 'JobPosting':
                    # Title
                    job_details['titre'] = data.get('title', '')
                    
                    # Date posted (use now if missing)
                    date_posted = data.get('datePosted', '')
                    if date_posted:
                        job_details['date_depot'] = normalize_date(date_posted)
                    else:
                        job_details['date_depot'] = datetime.now().strftime('%Y-%m-%d')
                    
                    # Employer
                    org = data.get('hiringOrganization', {})
                    job_details['employeur'] = org.get('name', '')
                    
                    # Location
                    location = data.get('jobLocation', {}).get('address', {})
                    job_details['wilaya'] = location.get('addressRegion', '')
                    job_details['adresse'] = location.get('addressLocality', '')
                    
                    # Description
                    desc = BeautifulSoup(data.get('description', ''), 'html.parser').get_text('\n', strip=True)
                    job_details['description'] = desc
            except:
                pass

        # Extract from visible elements
        if not job_details['titre']:
            title_tag = soup.find('h1')
            if title_tag:
                job_details['titre'] = title_tag.get_text(strip=True)

        # Extract main info blocks
        info_holder = soup.find('ul', class_='info-holder')
        if info_holder:
            lis = info_holder.find_all('li')
            if lis:
                job_details['wilaya'] = lis[0].get_text(strip=True)
                job_details['adresse'] = job_details['wilaya']
                
            for li in lis:
                text = li.get_text(strip=True)
                if 'Publiée le:' in text:
                    date_str = text.split('Publiée le:')[-1].split('Vue:')[0].strip()
                    job_details['date_depot'] = normalize_date(date_str)
                if 'Annonce N°:' in text:
                    job_details['numero'] = text.split('Annonce N°:')[-1].strip()

        # Extract parameters from extra questions
        eq=soup.find('ul',class_='extraQuestionName')
        if eq:
            for li in eq.find_all('li'):
                txt=li.get_text(strip=True)
                if 'Fonction :' in txt:
                    job_details['poste']=txt.split('Fonction :')[-1].strip()
                elif 'Domaine :' in txt:
                    dom=txt.split('Domaine :')[-1].strip()
                    job_details['domaine']=normalize_domaine(dom) if dom else 'Autre'
                elif 'Contrat :' in txt:
                    job_details['contrat']=txt.split('Contrat :')[-1].strip()
                elif 'Entreprise :' in txt:
                    job_details['employeur']=txt.split('Entreprise :')[-1].strip()
                elif 'Salaire :' in txt:
                    job_details['prix']=txt.split('Salaire :')[-1].strip()
                elif "Niveau d'études :" in txt:
                    dpl=txt.split("Niveau d'études :")[-1].strip()
                    nd=normalize_diplome(dpl)
                    if nd: job_details['diplome'].append(nd)
                    job_details['diplome_src'].append(dpl)

        # Extract description with safety check
        if not job_details['description']:
            desc_container = soup.find('div', class_='desccatemploi')
            if desc_container:
                desc_block = desc_container.find('div', class_='block')
                if desc_block:
                    job_details['description'] = desc_block.get_text('\n', strip=True)

        # Extract employer fallback
        if not job_details['employeur']:
            info_annonce = soup.find('div', class_='infoannonce')
            if info_annonce:
                dt = info_annonce.find('dt', string='Annonceur :')
                if dt:
                    dd = dt.find_next_sibling('dd')
                    if dd:
                        job_details['employeur'] = dd.get_text(strip=True)

        # Extract diploma from description
        raw_desc_diplomes = extract_diplome_from_description(job_details['description'])
        job_details['diplome_src'].extend(raw_desc_diplomes)
        normalized_desc_diplomes = [normalize_diplome(d) for d in raw_desc_diplomes if normalize_diplome(d)]
        job_details['diplome'].extend(normalized_desc_diplomes)
        job_details['diplome'] = list(set(job_details['diplome']))

        # Extract logo/image
        logo = soup.find('img', class_='logo')
        if logo and logo.get('src'):
            job_details['images'].append(logo['src'])
            job_details['as_photo'] = "Avec photo"

        return job_details