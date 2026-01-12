async def has_captcha(html):
    keywords = ["captcha", "cloudflare", "verify you are human", "hcaptcha"]
    return any(k in html.lower() for k in keywords)