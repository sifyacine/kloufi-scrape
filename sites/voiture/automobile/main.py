import asyncio
import sys
import os
from datetime import datetime

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from scrape_details import MobileScraper


async def main():
    """
    Main entry point for Mobile.de scraper
    """
    print("=" * 60)
    print("🚗 Mobile.de Scraper")
    print("=" * 60)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    try:
        # Initialize scraper
        scraper = MobileScraper()
        
        # Run the scraper
        results = await scraper.run()
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 SCRAPING SUMMARY")
        print("=" * 60)
        print(f"Total vehicles scraped: {len(results)}")
        print(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if results:
            print("\n✅ Data saved to: mobile_data.json")
            print(f"✅ Data inserted to Elasticsearch index: voiture")
            
            # Print sample of first result
            if len(results) > 0:
                print("\n📝 Sample of first result:")
                first = results[0]
                print(f"  - Title: {first.get('titre', 'N/A')}")
                print(f"  - Marque: {first.get('marque', 'N/A')}")
                print(f"  - Model: {first.get('model', 'N/A')}")
                print(f"  - Year: {first.get('annee', 'N/A')}")
                print(f"  - Price: {first.get('prix', 'N/A')} {first.get('prix_unit', '')}")
                print(f"  - KM: {first.get('km', 'N/A')}")
                print(f"  - Images: {len(first.get('images', []))}")
                
                if first.get('other_information'):
                    print(f"  - Other info fields: {len(first['other_information'])}")
        else:
            print("\n⚠️ No results were scraped")
        
        print("=" * 60)
        
        return results
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Scraping interrupted by user")
        sys.exit(0)
        
    except Exception as e:
        print(f"\n❌ Error occurred: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Run the async main function
    results = asyncio.run(main())