import aiohttp
import asyncio

# PROXY_SOURCES = [
#     "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
#     "https://api.proxyscrape.com/v2/?request=getproxies&protocol=https",
# ]
PROXY_SOURCES = [] # Disabled for test

# TEST CONFIGURATION
# User requested specific proxy: proenas.synology.me
# NOTE: Port 80 is assumed if not specified. Update if needed (e.g., :8080).
TEST_PROXY = "http://proenas.synology.me" 
USE_TEST_PROXY_ONLY = True

async def _fetch_raw_proxies():
    if USE_TEST_PROXY_ONLY and TEST_PROXY:
        print(f"!!! USING TEST PROXY ONLY: {TEST_PROXY} !!!")
        return [TEST_PROXY]

    proxies = set()
    async with aiohttp.ClientSession() as session:
        for url in PROXY_SOURCES:
            try:
                async with session.get(url, timeout=20) as r:
                    if r.status == 200:
                        text = await r.text()
                        for p in text.split():
                            # Remove whitespace
                            p = p.strip()
                            if not p:
                                continue
                            # Ensure protocol
                            if not p.startswith("http"):
                                p = f"http://{p}"
                            proxies.add(p)
            except Exception:
                pass
    return list(proxies)

async def validate_proxy(proxy, session):
    try:
        # Crucial: Validate against HTTPS to ensure CONNECT method works
        print(f"Validating proxy: {proxy}")
        async with session.get("https://www.google.com", proxy=proxy, timeout=10) as r:
            if r.status == 200:
                print(f"Proxy {proxy} is VALID.")
                return proxy
            else:
                print(f"Proxy {proxy} returned status {r.status}")
    except Exception as e:
        print(f"Proxy {proxy} validation failed: {e}")
        pass
    return None

async def fetch_and_validate_proxies():
    print("Fetching raw proxies...")
    raw_proxies = await _fetch_raw_proxies()
    print(f"Found {len(raw_proxies)} raw proxies. Validating...")
    
    # If using test proxy, we might want to skip validation OR be very verbose
    if USE_TEST_PROXY_ONLY:
        # We still validate it to ensure it works, but we print more info
        pass

    valid_proxies = []
    async with aiohttp.ClientSession() as session:
        tasks = [validate_proxy(p, session) for p in raw_proxies]
        results = await asyncio.gather(*tasks)
        valid_proxies = [p for p in results if p]
        
    print(f"Validation complete. {len(valid_proxies)}/{len(raw_proxies)} proxies are alive.")
    
    # Optional: If test proxy fails validation, you might still want to try it?
    # For now, we respect the validation result.
    return valid_proxies