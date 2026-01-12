import aiohttp

PROXY_SOURCES = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=https",
]

async def fetch_proxies():
    proxies = set()
    async with aiohttp.ClientSession() as session:
        for url in PROXY_SOURCES:
            try:
                async with session.get(url, timeout=20) as r:
                    if r.status == 200:
                        text = await r.text()
                        proxies.update(text.split())
            except Exception:
                pass
    return list(proxies)