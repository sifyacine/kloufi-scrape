import asyncio
import json
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from datetime import datetime
import sys
sys.path.insert(1, '../../global')
from insert_scrape import insert_data_to_es

def traitement_prix(prix_dec, prix_unit):

    if len(prix_dec) and len(prix_unit):
        if prix_unit == "Millions":
            return float(prix_dec) * 10000
        elif prix_unit == "Milliards":
            return float(prix_dec) * 10000000
        else:
            return float(prix_dec)
    else:
        prix_dec = 0


def diplome(diplome):
    if diplome == "Niveau secondaire": return "Diplome de collège"
    elif diplome == "Baccalauréat": return "Bac"
    elif diplome == "Bac +2": return "Diplome universitaire"
    elif diplome == "Licence": return "Diplome universitaire"
    elif diplome == "Bac + 3": return "Diplome universitaire"
    elif diplome == "Bac+3": return "Diplome universitaire"
    elif diplome == "Master 1": return "Master"
    elif diplome == "Licence Bac + 4": return "Diplome universitaire"
    elif diplome == "Master 2": return "Master"
    elif diplome == "Ingéniorat": return "Diplome universitaire"
    elif diplome == "Bac + 5": return "Diplome universitaire"
    elif diplome == "Magistère Bac + 7": return "Diplome universitaire"
    elif diplome == "Certification": return "Diplôme professionnel / téchnique"


def traitement_wilaya(address):
    try:
        return address.split(',')[0].strip()
    except:
        return "N/A"


def normalize_experience(exp_str):
    exp_str = exp_str.strip()

    if exp_str in ["Débutant < 2 ans", "Jeune Diplômé"]:
        return "Jeune Diplômé"
    elif exp_str in ["Expérience entre 2 ans et 5 ans"]:
        return "Débutant / Junior"
    elif exp_str in ["Expérience entre 5 ans et 10 ans"]:
        return "Confirmé / Expérimenté"
    elif exp_str in ["Expérience > 10 ans"]:
        return "Confirmé / Expérimenté"
    elif exp_str in ["Etudiant"]:
        return "Etudiant"
    else:
        return exp_str

def traitement_domaine(domaine):
    # Commerce & Vente
    # Commercial & Marketing
    # Industrie & Production
    # Tourisme & Gastronomie
    # Beauté & Esthétique
    # Nettoyage & Hygiène
    # Bureautique & Secretariat
    # Informatique & Internet
    # Couture et Confection
    # Comptabilité & Audit
    # Administration & Management
    # Graphisme & Communication
    # Agents polyvalents
    # Mécanique Auto
    # Eléctronique & Téchnique
    # Artisanat
    # Securité
    # Immobilier
    # Juridique
    # Achat & Logistique
    # Journalisme & Pressente
    # Environnement
    # Recherche & developpement
    # Construction & Travaux
    # Carburants & Mines
    # Transport & Chauffeurs
    # Medecine & Santé
    # Banque
    # Assurance
    # Distribution
    # Industries
    # Services
    # Autre

    mapping = {
        "Achats": "Achat & Logistique",
        "Commercial, vente": "Commerce & Vente",
        "Gestion, comptabilité, finance": "Comptabilité & Audit",
        "Informatique, nouvelles technologies": "Informatique & Internet",
        "Juridique": "Juridique",
        "Management, direction générale": "Administration & Management",
        "Marketing, communication": "Commercial & Marketing",
        "Métiers de la santé et du social": "Medecine & Santé",
        "Métiers des services": "Services",
        "Métiers du BTP": "Construction & Travaux",
        "Production, maintenance, qualité": "Industrie & Production",
        "R&D, gestion de projets": "Recherche & developpement",
        "RH, formation": "Administration & Management",
        "Secrétariat, assistanat":  "Bureautique & Secretariat",
        "Télémarketing, téléassistance": "Commercial & Marketing",
        "Tourisme, hôtellerie, restauration": "Tourisme & Gastronomie",
        "Transport, logistique": "Achat & Logistique",
    }
    
    return mapping.get(domaine.strip(), "Autre")

async def scrape_single_url_with_crawl4ai_and_bs4(url, job):
    print(f"Scraping URL: {url}")

    browser_config = BrowserConfig(
        headless=True,
        text_mode=False,
        browser_type="chromium",
    )
    # JavaScript commands to handle dynamic content (e.g., accept cookies)
    js_commands = [
        # Wait for banners
        "await new Promise(resolve => setTimeout(resolve, 5000));",
        # Accept cookies
        "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",
        """
        await new Promise(resolve => setTimeout(resolve, 3000));  // Allow content to load

        let maxScrollHeight = document.body.scrollHeight;
        let scrollStep = 300;
        let currentScroll = 0;

        const checkElement = async () => {
            while (currentScroll <= maxScrollHeight) {
                const targetElement = document.getElementById('announcementUserInfo');
                if (targetElement) {
                    targetElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    console.log('Element found and scrolled into view');
                    break;
                }
                currentScroll += scrollStep;
                window.scrollBy(0, scrollStep);
                await new Promise(resolve => setTimeout(resolve, 500));  // Delay between scrolls
                maxScrollHeight = document.body.scrollHeight;  // Update scroll height
            }

            if (!document.getElementById('announcementUserInfo')) {
                console.log('Element not found after scrolling to the bottom of the page');
            }
        };

        await checkElement();
        """
    ]

    # Configure the crawler
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        js_code=js_commands,
        delay_before_return_html=10
    )

    # Run the crawler
    async with AsyncWebCrawler(verbose=True, config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=config)

        if not result.success:
            print(f"Error scraping URL {url}: {result.error_message}")
            return

        # Parse the HTML content with BeautifulSoup
        soup = BeautifulSoup(result.html, "html.parser")

        as_photo = "Sans photo"
        images = []
        titre = job["titre"] if job["titre"] != "" else ""
        poste = job["poste"] if job["poste"] != "" else ""
        date_depot = job["date_depot"] if job["date_depot"] != "" else ""
        numero = url.split('-')[-1]
        job_details_section = soup.find_all(
            'div', class_='card card-block card-block-summary')[0]
        entreprise_section = soup.find_all(
            'div', class_='card card-block card-block-summary')[1]
        details_section = soup.find('h2', string="Détails de l'annonce")
        adresse = ""
        contrat = ""
        employeur = job["employeur"] if job["employeur"] != "" else ""
        diplome_list = []
        domaine = []
        diplome_list_normalized = []
        niveau_poste_normalized = []
        wilaya = ""

        if entreprise_section:
            image_src = entreprise_section.find('img')
            if image_src:
                image_src = image_src.get('src')
                images.append(image_src)
                as_photo = "Avec Photo"
            # entreprise_sector = entreprise_section.find_all(
            #     'strong', string="Secteur d´activité")
            # if entreprise_sector:
            #     domaine_text = li.withicon.suitcase[0].find_next('span').text
            #     domaine_list = domaine_text.split(',')
            #     for dom in domaine_list:
            #         domaine.append(dom.strip().capitalize())

        if job_details_section:
            diplome_li = job_details_section.find(
                'li', class_='withicon graduation-cap')
            contrat_li = job_details_section.find(
                'li', class_='withicon file-signature')
            niveau_li = job_details_section.find('li', class_='withicon chart')
            adresse_li = job_details_section.find(
                'li', class_='withicon location-dot')
            domaine_li = job_details_section.find('li', class_='withicon suitcase')
            
            if domaine_li:
                domaine_text = domaine_li.find('span').text
                domaine = traitement_domaine(domaine_text)

            if diplome_li:
                diplome_text = diplome_li.find('span').text
                diplomes = diplome_text.split('-')
                for dipl in diplomes:
                    diplome_list_normalized.append(diplome(dipl.strip()))
                    diplome_list.append(dipl.strip())

            if contrat_li:
                contrat_text = contrat_li.find('span').text
                contrat = contrat_text

            if niveau_li:
                niveau_text = niveau_li.find('span').text
                niveau_poste_list = niveau_text.split('-')
                for niveau in niveau_poste_list:
                    niveau_poste_normalized.append(
                        normalize_experience(niveau.strip()))

            if adresse_li and adresse_li.find('span').text != "Adrar - Aïn-Defla - Aïn Témouchent - Alger - Annaba - Batna - Béchar - Béjaïa - Biskra - Blida - Bordj Bou Arreridj - Bouira - Boumerdès - Chlef - Constantine - Djelfa - El Bayadh - El Oued - El Tarf - Ghardaïa - Guelma - Illizi - Jijel - Khenchela - Laghouat - M'Sila - Mascara - Médéa - Mila - Mostaganem - Naâma - Oran - Ouargla - Oum el-Bouaghi - Relizane - Saïda - Sétif - Sidi Bel Abbès - Skikda - Souk Ahras - Tamanrasset - Tébessa - Tiaret - Tindouf - Tipaza - Tissemsilt - Tizi Ouzou - Tlemcen - International":
                wilaya = adresse_li.find('span').text
                adresse = f"{wilaya}, Algérie"
            else:
                wilaya = "WorldWide - International"
                adresse = f"{wilaya}"
        
            if details_section:
                description_section = details_section.find_next('div')
                description = description_section.text

        job = {
            'date_crawl': datetime.now().isoformat(),
            'url': url,
            'site_origine': "Algeriejob.com",
            'titre': titre,
            'niveau': niveau_poste_normalized,
            'numero': numero,
            'date_depot': date_depot,
            'transaction': "Offres",
            'contrat': contrat,
            'diplome': diplome_list_normalized,
            'diplome_src': diplome_list,
            'domaine': domaine,
            'description': description,
            'employeur': employeur,
            'poste': poste,
            'adresse': adresse,
            'wilaya': wilaya,
            'status': 200,
            'date_verif': datetime.now().isoformat(),
            'images': images,
            'as_photo': as_photo,
            'as_prix': "",
            'vehicle': "False",
        }
        
        print(json.dumps(job, indent=2))
        insert_data_to_es(job, "emploi")

# Run the main function
# asyncio.run(scrape_single_url_with_crawl4ai_and_bs4(
#     "https://www.algeriejob.com/offre-emploi-algerie/chef-production-aquacole-toute-aglerie-146378", {"poste": "Chef de Production Aquacole", "employeur": "AQUA HOUTA", "date_depot": "2021-09-30", "titre": "Chef de Production Aquacole"}))
