async def has_captcha(html):
    # More specific markers for actual blocking challenges (like Cloudflare, Recaptcha, etc)
    # broad keywords like 'cloudflare' in the whole HTML cause false positives on Proxy sites
    markers = [
        'id="challenge-form"',          # Cloudflare Challenge
        'id="cf-challenge"',            # Cloudflare
        'class="g-recaptcha"',           # Google Recaptcha
        'id="hcaptcha-box"',            # hCaptcha
        'verify you are human',         # Explicit challenge text
        'checking your browser before accessing' # Cloudflare waiting room
    ]
    
    html_lower = html.lower()
    return any(m in html_lower for m in markers)