import aiohttp
import asyncio

PROXY_SOURCES = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=https",
]

async def _fetch_raw_proxies():
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
        async with session.get("https://www.google.com", proxy=proxy, timeout=8) as r:
            if r.status == 200:
                return proxy
    except:
        pass
    return None

async def fetch_and_validate_proxies():
    print("Fetching raw proxies...")
    raw_proxies = await _fetch_raw_proxies()
    print(f"Found {len(raw_proxies)} raw proxies. Validating...")
    
    valid_proxies = []
    async with aiohttp.ClientSession() as session:
        tasks = [validate_proxy(p, session) for p in raw_proxies]
        results = await asyncio.gather(*tasks)
        valid_proxies = [p for p in results if p]
        
    print(f"Validation complete. {len(valid_proxies)}/{len(raw_proxies)} proxies are alive.")
    return valid_proxies