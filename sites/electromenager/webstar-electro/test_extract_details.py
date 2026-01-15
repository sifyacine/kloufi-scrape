import asyncio
import json
import sys
from scrape_details import extract_product_details

async def test_extract(url):
    """
    Tests the extract_product_details function with a given seller URL and prints the output.
    """
    try:
        details = await extract_product_details(url)
        print("\nExtracted Details:")
        print(json.dumps(details, indent=4, ensure_ascii=False))
    except Exception as e:
        print(f"Error extracting details: {e}")

if __name__ == "__main__":
    # Hardcode a test URL or pass it as a command-line argument
    test_url = "https://webstar-electro.com/stores/?annonce=bissell-2233e&page=aspirateurs&store=facilite-bechar-magasin-vente-en-ligne-algerie&id_store=15842838&id_famille=3766&id_annonce=21219696&position=3"
    
    if len(sys.argv) > 1:
        test_url = sys.argv[1]
    
    print(f"Testing with URL: {test_url}")
    asyncio.run(test_extract(test_url))