import re
import json
import sys
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from utils.emploi import EmploiUtils

try:
    from insert2db.insert_scrape import insert_data_to_es
except ImportError:
    def insert_data_to_es(data, index):
        print(f"[Mock] Inserting data to ES index '{index}'")

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
                        job_details['date_depot'] = EmploiUtils.normalize_date(date_posted)
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
                    job_details['date_depot'] = EmploiUtils.normalize_date(date_str)
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
                    job_details['domaine']=EmploiUtils.normalize_domaine(dom) if dom else 'Autre'
                elif 'Contrat :' in txt:
                    job_details['contrat']=txt.split('Contrat :')[-1].strip()
                elif 'Entreprise :' in txt:
                    job_details['employeur']=txt.split('Entreprise :')[-1].strip()
                elif 'Salaire :' in txt:
                    job_details['prix']=txt.split('Salaire :')[-1].strip()
                elif "Niveau d'études :" in txt:
                    dpl=txt.split("Niveau d'études :")[-1].strip()
                    nd=EmploiUtils.normalize_diplome(dpl)
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
        raw_desc_diplomes = EmploiUtils.extract_diplome_from_description(job_details['description'])
        job_details['diplome_src'].extend(raw_desc_diplomes)
        normalized_desc_diplomes = [EmploiUtils.normalize_diplome(d) for d in raw_desc_diplomes if EmploiUtils.normalize_diplome(d)]
        job_details['diplome'].extend(normalized_desc_diplomes)
        job_details['diplome'] = list(set(job_details['diplome']))

        # Extract logo/image
        logo = soup.find('img', class_='logo')
        if logo and logo.get('src'):
            job_details['images'].append(logo['src'])
            job_details['as_photo'] = "Avec photo"

        insert_data_to_es(job_details, "emploi")
        return job_details