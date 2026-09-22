import asyncio
import json
import re
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def test_active():
    session = cffi_requests.AsyncSession(impersonate="chrome120")
    
    # 1. Fetch Toonworld episode page
    ep_url = "https://archive.toonworld4all.me/episode/liar-game-1x2"
    resp = await session.get(ep_url, headers={"User-Agent": DEFAULT_UA})
    
    # Extract window.__PROPS__ JSON data
    m = re.search(r'window\.__PROPS__\s*=\s*(\{.*?\});', resp.text)
    if m:
        props = json.loads(m.group(1))
        encodes = props.get("data", {}).get("data", {}).get("encodes", [])
        print(f"Found {len(encodes)} quality encodes!")
        for enc in encodes:
            res_name = enc.get("readable", {}).get("codec", enc.get("resolution"))
            print(f"\n--- Quality: {res_name} ---")
            for f in enc.get("files", []):
                host = f.get("host")
                link = f.get("link")
                print(f"Host: {host} -> Link: {link}")
                if host.lower() == "gdflix":
                    full_link = "https://archive.toonworld4all.me" + link
                    print(f"Resolving GDFlix link: {full_link}")
                    r_red = await session.get(full_link, headers={"User-Agent": DEFAULT_UA})
                    soup = BeautifulSoup(r_red.text, "html.parser")
                    dest_block = soup.find("code")
                    dest_url = dest_block.text.strip() if dest_block else "Not found"
                    print(f"Destination URL: {dest_url}")

if __name__ == "__main__":
    asyncio.run(test_active())
