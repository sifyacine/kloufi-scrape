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
    test_url = "https://webstar-electro.com/stores/?annonce=apple-iphone-14-pro-max-6-256gb-1sim&page=telephones-portables&store=force-technologie-magasin-vente-en-ligne-algerie&id_store=14854049&id_famille=3758&id_annonce=21956560&position=3"
    
    if len(sys.argv) > 1:
        test_url = sys.argv[1]
    
    print(f"Testing with URL: {test_url}")
    asyncio.run(test_extract(test_url))