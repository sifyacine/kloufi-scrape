import asyncio
import json
import re
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from bs4 import BeautifulSoup
from datetime import datetime
import sys
sys.path.insert(1, '../../../global')
from insert_scrape import insert_data_to_es

all_results = []

# Compléter les URLs des images


def image_complete(image):
    return ["https:" + img for img in image]


# Vérifier si une annonce a une photo
def avec_sans_photo(image):
    return "Avec photo" if image and "//www.lkeria.com/image/vide.jpg" not in image else "Sans photo"


# Vérifier si une annonce a un prix
def avec_sans_prix(prix_dec, prix_unit):
    return "Avec prix" if prix_dec and prix_unit else "Sans prix"


# Compléter les URLs des liens
def lien_complete(lien):
    return ["https:" + link for link in lien]


# Convertir une chaîne en date
def str_todate(strdate):
    try:
        return datetime.strptime(strdate, '%d-%m-%Y')
    except ValueError:
        return datetime.now()


# Nettoyer la ville
def clean_ville(ville):
    return ville[4:].replace("e Niveau de villa ", "").strip()


# Convertir une chaîne en float
def str_to_float(valeur):
    if valeur:
        valeur = valeur.replace(",", ".").replace(" ", "")
        return float(valeur)
    return 0.0


# Convertir une chaîne en int
def str_to_int(valeur):
    return int(valeur) if valeur else 0

def convert_property_type(raw_key):
    valid_types = {
        "Appartement", "Villa", "Local", "Terrain", "Studio", "Hangar",
        "Niveau de villa", "Immeuble", "Duplex", "Carcasse", "Autre",
        "Bungalow", "Terrain agricole", "Usine", "Chalet", "Commerce",
        "Locaux", "Bureau", "Autres", "Salle", "Hostel", "Dortoir",
        "Ferme", "Hotel", "Triplex", "Maison", "Pavillon", "Auberge", "Résidence"
    }

    normalization_map = {
        "bungalow": "Bungalow",
        "bungalows": "Bungalow",
        "niveau": "Niveau de villa",
        "niveau de villa": "Niveau de villa",
        "terrain-agricole": "Terrain agricole",
        "terrain agricole": "Terrain agricole",
        "appartements": "Appartement",
        "immeubles": "Immeuble",
        "commerce, local": "Commerce",
        "bureaux": "Bureau",
        "ferme, terrain": "Ferme",
        "residence": "Résidence",
        "résidence": "Résidence"
    }

    if not raw_key or not isinstance(raw_key, str):
        return ""

    cleaned = raw_key.strip().lower()

    normalized = normalization_map.get(cleaned, cleaned).capitalize()
    if normalized in valid_types:
        return normalized

    lowered = raw_key.lower()
    for key, value in normalization_map.items():
        if key in lowered:
            normalized_candidate = value
            if normalized_candidate in valid_types:
                return normalized_candidate

    for valid in valid_types:
        if valid.lower() in lowered:
            return valid

    return ""

async def get_total_pages():
    """Get the total number of pages from the first page."""
    url = "https://www.lkeria.com/annonces/immobilier/vente/studio-P0"
    js_commands = [
        "await new Promise(resolve => setTimeout(resolve, 2000));",
        "document.querySelector('button.fc-button.fc-cta-consent.fc-primary-button')?.click();",
        "await new Promise(resolve => setTimeout(resolve, 2000));"
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

    browser_config = BrowserConfig(
        headless=True,
        text_mode=False,
        browser_type="chromium",
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=url,
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                js_code=js_commands,
                delay_before_return_html=10
            )
        )

        if result.success:
            print("Successfully scraped the first page!")

            # Parse the HTML content using BeautifulSoup to find the pagination
            soup = BeautifulSoup(result.html, 'html.parser')

            # Find the last page number by checking the pagination
            pagination_items = soup.find_all('li', class_='v-pagination__item')

            # Check the last page number (it's inside the <span> of the last <li> element)
            last_page_button = pagination_items[-1].find('button')
            if last_page_button:
                last_page_number = last_page_button.find(
                    'span', class_='v-btn__content').get_text(strip=True)
                last_page_number = re.sub(r'\D', '', last_page_number)
                print(f"Total pages: {last_page_number}")
                return int(last_page_number)
            else:
                print("Failed to find the last page number.")
                return 1  # Default to 1 page if not found
        else:
            print("Error scraping the first page:", result.error_message)
            return 1


async def scrape_page(page_number):
    global all_results
    url = f"https://www.lkeria.com/annonces/immobilier/vente/studio-P{
        page_number}"

    # JavaScript commands to accept cookies (if needed)
    js_commands = [
        # Wait 5 seconds for banner
        "await new Promise(resolve => setTimeout(resolve, 5000));",
        "document.querySelector('button.sd-cmp-1bquj')?.click();",
        "await new Promise(resolve => setTimeout(resolve, 3000));"
    ]

    # Define the browser configuration
    browser_config = BrowserConfig(
        headless=True,
        text_mode=False,
        browser_type="chromium",
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        # Scrape the page for name, vente, and URL
        result = await crawler.arun(
            url=url,
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                js_code=js_commands,  # Inject the JS code to accept cookies
                delay_before_return_html=10  # Wait for the page to settle
            )
        )

        if result.success:

            # Parse the HTML content with BeautifulSoup
            soup = BeautifulSoup(result.html, 'html.parser')

            # Find all the listings on the page
            annonces = soup.select('article.hentry')
            print(f"Found {len(annonces)} listings on page {page_number}")
            photo = "Sans photo"

            for annonce in annonces:
                # Titre
                titre_element = annonce.select_one(
                    'div.property-title.hidden-xs > a')
                titre = titre_element.text.strip().capitalize() if titre_element else ""

                # URL
                url = titre_element['href'] if titre_element and titre_element.has_attr(
                    'href') else ""
                url = f"https:{url}" if url else ""

                # Numero
                numero = re.search(r'-(\d+)-', url)
                numero = numero.group(1) if numero else "Numéro non disponible"

                # image
                image_element = annonce.select_one('div.property-featured')
                if image_element:
                    image_src = image_element.select_one('img')['src']
                    print(image_src)
                    image = image_complete(
                        [image_src]) if image_src != "//www.lkeria.com/image/vide.jpg" else []
                else:
                    image = []

                print(len(image))
                if len(image) != 0:
                    photo = "Avec photo"
                else:
                    photo = "Sans photo"

                # Date de dépôt
                date_depot_element = annonce.select_one(
                    'span.property-label.hidden-xs')
                date_depot = str_todate(date_depot_element.text.strip(
                )) if date_depot_element else datetime.now()

                # Bien category
                category_element = annonce.select_one(
                    'div.property-title.hidden-xs')
                bien = ' '.join(
                    re.findall(r'appartement|autre|bungalow|carcasse|duplex|hangar|immeuble|local|niveau-de-villa|studio|terrain-agricole|terrain|usine|villa',
                               category_element.text if category_element else "", flags=re.IGNORECASE)
                ).capitalize()

                # Superficie and Unit
                superficie_text = annonce.select_one(
                    'p').text if annonce.select_one('p') else ""
                superficie = str_to_int(re.search(r'(\d+)\s?m2', superficie_text).group(
                    1)) if re.search(r'(\d+)\s?m2', superficie_text) else 0
                superficie_unit = "m2" if "m2" in superficie_text.lower() else ""

                # Nombre de pièces
                nb_pieces = ''.join(re.findall(r'[fF](\d+)', superficie_text))

                # Description
                description = ' '.join([p.text.strip()
                                       for p in annonce.select('p')])

                # Prix
                prix_element = annonce.select_one('span.amount')
                prix_str = prix_element.text.strip() if prix_element else ""
                prix_dec = str_to_float(prix_str) if prix_str else 0.0
                prix_unit = "DA" if prix_str else ""

                # Adresse and Wilaya
                adresse_wilaya = [span.text.strip() for span in annonce.select(
                    'span.property-category') if '-' in span.text]
                adresse = adresse_wilaya[0] if adresse_wilaya else ""
                wilaya = adresse_wilaya[1] if len(adresse_wilaya) > 1 else ""

                # Assemble data
                data = {
                    'titre': titre,
                    'url': url,
                    'site_origine': "Lkeria.com",
                    'date_crawl': datetime.now().isoformat(),
                    'numero': numero,
                    'date_depot': date_depot.isoformat(),
                    'transaction': "Vente",
                    'category': "immobilier",
                    'bien': convert_property_type(bien) if bien else "",
                    'superficie': superficie,
                    'superficie_unit': superficie_unit,
                    'nb_pieces': nb_pieces,
                    'description': description,
                    'prix': prix_str,
                    'prix_dec': prix_dec,
                    'prix_unit': prix_unit,
                    'images': image,
                    'adresse': adresse,
                    'wilaya': wilaya,
                    'status': 200,
                    'date_verif': datetime.now().isoformat(),
                    'as_photo': photo,
                }

                if data['url'] != "":
                    insert_data_to_es(data, "immobilier")
                print(json.dumps(data, indent=2))

        else:
            print(f"Error on page {page_number}:", result.error_message)

# Main function to run the tasks sequentially


async def main():
    # # Get the total number of pages from the first page
    # total_pages = await get_total_pages()

    # Scrape each page one by one
    for page_number in range(1, 50):
        await scrape_page(page_number)

    print(f"Total items collected: {len(all_results)}")
    print(all_results)

if __name__ == "__main__":
    asyncio.run(main())

#     def parse(self, response):
#         for annonce in response.css('article.hentry'):
#             # Images
#             image = annonce.css('div.property-featured > img::attr(src)').re('//www.lkeria.com/uploads.+.jpg')
#             if image and "//www.lkeria.com/image/vide.jpg" not in image:
#                 photo = "Avec photo"
#                 image = image_complete(image)
#             else:
#                 photo = "Sans photo"
#                 #image = []

#             # Titre
#             titre = ' '.join(annonce.css('div.property-title.hidden-xs > a::text').extract()).capitalize()

#             yield {
#                 'titre': titre,
#                 'url': "https:" + ''.join(annonce.css('div.list.property-action a').xpath('@href').extract()),
#                 'site_origine': "Lkeria.com",
#                 'date_crawl': datetime.now(),
#                 'numero': ''.join(annonce.css('div.list.property-action a').xpath('@href').re(r'-(\d+)-')),
#                 'date_depot': str_todate(''.join(annonce.css('span.property-label.hidden-xs::text').re(r'\d+-\d+-\d+'))),
#                 'transaction': "Vente",
#                 'category': "immobilier",
#                 'bien': ' '.join(annonce.css('div.property-title.hidden-xs').re(r'appartement|autre|bungalow|carcasse|duplex|hangar|immeuble|local|niveau-de-villa|studio|terrain-agricole|
# terrain|usine|villa')).capitalize(),
#                 'superficie': str_to_int(''.join(annonce.css('p::text').re(r'(\d+)\s?m2')[:1])),
#                 'superficie_unit': ''.join(annonce.css('p::text').re(r'\d+\s?(m2)')[:1]).upper(),
#                 'nb_pieces': ''.join(annonce.css('p::text').re(r'[fF](\d+)')[:1]),
#                 'description': ' '.join(annonce.css('p::text').extract()),
#                 'prix': ' '.join(annonce.css('span.amount::text').re(r'\d+ .*')[:1] + annonce.css('span').re(r'DA')[:1]),
#                 'prix_dec': str_to_float(''.join(annonce.css('span.amount::text').re(r'\d+ .*')[:1])),
#                 'prix_unit': ''.join(annonce.css('span').re(r'DA')[:1]),
#                 'images': annonce.css('div.property-featured > img::attr(src)').re('//www.lkeria.com/uploads.+.jpg'),
#                 'adresse': ' '.join(annonce.css('span.property-category::text').re(r'- (\w+.+)')),
#                 'wilaya': ' '.join(annonce.css('span.property-category::text').re(r'- (\w+.+)')),
#                 'status': 200,
#                 'date_verif': datetime.now(),
#                 'as_photo': photo,
#                 'as_prix': avec_sans_prix(
#                     ''.join(annonce.css('span.amount::text').re(r'\d+ .*')[:1]),
#                     ''.join(annonce.css('span').re(r'DA')[:1])
#                 )
#             }
