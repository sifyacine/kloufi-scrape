async def is_blocked(status, html):
    if status in (403, 429):
        return True
    if "access denied" in html.lower():
        return True
    return False