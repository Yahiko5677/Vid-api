import asyncio
import re
import json
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def test_clean_resolution():
    urls = [
        "https://archive.toonworld4all.me/episode/liar-game-1x2",
        "https://archive.toonworld4all.me/redirect/6d7bc1e263a9a2eebbe01107971ee36fa567903e828ff5544405bc14553754de04a9f172864cc524d709ca6f5dd24fac7e568c12a91c85c03a43f1218ad12cce740ff8dd6ff0fd210bb4c78a1f365f1d"
    ]
    
    session = cffi_requests.AsyncSession(impersonate="chrome120")
    
    for url in urls:
        print(f"\n==========================================")
        print(f"Resolving clean URL: {url}")
        print(f"==========================================")
        
        resp = await session.get(url, headers={"User-Agent": DEFAULT_UA})
        m = re.search(r'window\.__PROPS__\s*=\s*(\{.*?\});', resp.text)
        if not m:
            print("Failed to find window.__PROPS__")
            continue
            
        props = json.loads(m.group(1))
        
        # Check if redirect page
        if "/redirect/" in url:
            link_info = props.get("link", {})
            hidden = link_info.get("hidden", "")
            if hidden:
                target_gdflix = f"https://new4.gdflix.io/file/{hidden}"
                print(f"Direct GDFlix File Link extracted from JSON: {target_gdflix}")
                
                # Fetch GDFlix page
                gd_resp = await session.get(target_gdflix, headers={"User-Agent": DEFAULT_UA})
                soup = BeautifulSoup(gd_resp.text, "html.parser")
                title = soup.find("title").text if soup.find("title") else "N/A"
                print(f"GDFlix Page Status: {gd_resp.status_code}, Title: {title}")
                
                # Direct links on GDFlix page
                for a in soup.find_all("a", href=True):
                    if any(k in a["href"] for k in ["drive.google.com", "workers.dev", "/download"]):
                        print(f"  Found Download Link: {a.text.strip()} -> {a['href']}")

        # Episode Page
        else:
            encodes = props.get("data", {}).get("data", {}).get("encodes", [])
            print(f"Found {len(encodes)} encodes on episode page:")
            for enc in encodes:
                q = enc.get("readable", {}).get("codec", enc.get("resolution"))
                sz = enc.get("readable", {}).get("size", "")
                print(f"\n--- Quality: {q} ({sz}) ---")
                for f in enc.get("files", []):
                    if f.get("host", "").lower() == "gdflix":
                        red_link = "https://archive.toonworld4all.me" + f["link"]
                        print(f"GDFlix Redirect Link: {red_link}")
                        
                        # Fetch redirect props
                        r_red = await session.get(red_link, headers={"User-Agent": DEFAULT_UA})
                        m_red = re.search(r'window\.__PROPS__\s*=\s*(\{.*?\});', r_red.text)
                        if m_red:
                            p_red = json.loads(m_red.group(1))
                            h_code = p_red.get("link", {}).get("hidden", "")
                            if h_code:
                                gd_direct = f"https://new4.gdflix.io/file/{h_code}"
                                print(f"  ==> Resolved GDFlix File Link: {gd_direct}")

if __name__ == "__main__":
    asyncio.run(test_clean_resolution())

