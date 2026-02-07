import asyncio
import sys
import os
import json

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from scraper.proxy.proxy_sources import fetch_proxies
from scraper.proxy.proxy_manager import ProxyManager
from scraper.crawler.crawler_runner import crawl
from scraper.browser.fingerprint import build_context

async def verify_proxy_masking():
    print("="*60)
    print("PROXY INTEGRATION VERIFICATION")
    print("="*60)

    # 1. Fetch Proxies
    print("1. Fetching proxies...")
    proxies = await fetch_proxies()
    if not proxies:
        print("❌ No proxies found! Checking proxy sources...")
        return
    
    print(f"✅ Fetched {len(proxies)} proxies.")
    manager = ProxyManager(proxies)

    # 2. Define IP Check URL
    # httpbin.org/ip returns the IP address of the requester
    check_url = "https://httpbin.org/ip"
    
    print(f"\n2. Testing Proxy Masking via {check_url}")
    print("   We will make 3 requests with different proxies.")
    print("   If working, each 'origin' IP should be different.\n")

    for i in range(1, 4):
        proxy = manager.get_proxy("httpbin.org")
        print(f"--- Test #{i} ---")
        print(f"👉 Selected Proxy: {proxy}")
        
        context = build_context()
        
        try:
            # Run crawl with the proxy
            result = await crawl(check_url, proxy, context, magic=True)
            
            if result.success:
                try:
                    # httpbin returns JSON: { "origin": "1.2.3.4" }
                    data = json.loads(result.html)
                    origin_ip = data.get("origin")
                    print(f"✅ SUCCESS! Site sees IP: {origin_ip}")
                    
                    # Basic validation
                    proxy_ip = proxy.split("://")[-1].split(":")[0]
                    if proxy_ip in origin_ip:
                        print("   (Matches Proxy IP - Confirmed)")
                    else:
                        print("   (Note: Output IP differs from Proxy IP - likely a cascading/rotating proxy)")
                        
                except Exception as e:
                    print(f"⚠️  Crawl success but failed to parse JSON: {e}")
                    print(f"   Raw HTML: {result.html[:100]}...")
            else:
                print(f"❌ Failed to connect (Status: {result.status_code})")
                manager.report_failure(proxy)
                
        except Exception as e:
            print(f"❌ Exception: {e}")
        
        print("-" * 30)
        # Rotate for next test
        manager.rotate("httpbin.org")
        await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(verify_proxy_masking())
