import asyncio
import json
import re
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def test_mega_redirect():
    session = cffi_requests.AsyncSession(impersonate="chrome120")
    
    # 1. Fetch Toonworld episode page
    ep_url = "https://archive.toonworld4all.me/episode/liar-game-1x2"
    resp = await session.get(ep_url, headers={"User-Agent": DEFAULT_UA})
    
    m = re.search(r'window\.__PROPS__\s*=\s*(\{.*?\});', resp.text)
    if not m:
        print("No window.__PROPS__ found")
        return

    props = json.loads(m.group(1))
    encodes = props.get("data", {}).get("data", {}).get("encodes", [])
    
    for enc in encodes:
        res_name = enc.get("readable", {}).get("codec", enc.get("resolution"))
        print(f"\n--- Quality: {res_name} ---")
        for f in enc.get("files", []):
            host = f.get("host")
            if host.lower() == "mega":
                link = f.get("link")
                full_link = "https://archive.toonworld4all.me" + link if link.startswith("/") else link
                print(f"Resolving MEGA redirect link: {full_link}")
                r_red = await session.get(full_link, headers={"User-Agent": DEFAULT_UA})
                print("Redirect page status:", r_red.status_code)
                
                m_red = re.search(r'window\.__PROPS__\s*=\s*(\{.*?\});', r_red.text)
                if m_red:
                    p_red = json.loads(m_red.group(1))
                    print("MEGA Redirect Props:", json.dumps(p_red, indent=2))
                else:
                    print("No __PROPS__ in MEGA redirect page")

if __name__ == "__main__":
    asyncio.run(test_mega_redirect())
