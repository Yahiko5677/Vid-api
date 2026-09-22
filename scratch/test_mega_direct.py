import asyncio
import json
import re
from curl_cffi import requests as cffi_requests

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

def parse_props_json(html_text):
    m = re.search(r'window\.__PROPS__\s*=\s*(\{.*?\});\s*</script>', html_text, re.DOTALL)
    if not m:
        m = re.search(r'window\.__PROPS__\s*=\s*(\{.*?\});', html_text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception as e:
            print("JSON load error:", e)
    return None

async def extract_working_mega_url():
    ep_url = "https://archive.toonworld4all.me/episode/liar-game-1x2"
    print(f"Fetching episode: {ep_url}")

    session = cffi_requests.AsyncSession(impersonate="chrome120")
    resp = await session.get(ep_url, headers={"User-Agent": DEFAULT_UA})
    props = parse_props_json(resp.text)

    if not props:
        print("Failed to parse episode props!")
        return

    encodes = props.get("data", {}).get("data", {}).get("encodes", [])
    
    mega_link_obj = None
    for enc in encodes:
        quality = enc.get("readable", {}).get("codec", enc.get("resolution", "Unknown"))
        files = enc.get("files", [])
        for f in files:
            host = f.get("host", "")
            if "mega" in host.lower():
                rel = f.get("link", "")
                full_red = f"https://archive.toonworld4all.me{rel}" if rel.startswith("/") else rel
                mega_link_obj = {
                    "quality": quality,
                    "host": host,
                    "redirect_url": full_red
                }
                break
        if mega_link_obj:
            break

    if not mega_link_obj:
        print("No MEGA link found in encodes!")
        return

    print(f"Quality: {mega_link_obj['quality']} | Host: {mega_link_obj['host']}")
    print(f"Toonworld Redirect URL: {mega_link_obj['redirect_url']}")

    # Fetch redirect page HTML
    r_red = await session.get(mega_link_obj['redirect_url'], headers={"User-Agent": DEFAULT_UA})
    print(f"Redirect Response Status: {r_red.status_code}")

    p_red = parse_props_json(r_red.text)
    if p_red:
        link_info = p_red.get("link", {})
        domain = link_info.get("domain", "")
        hidden = link_info.get("hidden", "")
        dest = p_red.get("destination", "")

        print("\nExtracted Link Object Properties:")
        print(f"  domain      : {domain}")
        print(f"  hidden      : {hidden}")
        print(f"  destination : {dest}")

        if domain and hidden:
            working_mega_url = f"{domain}{hidden}"
            print("\n" + "=" * 60)
            print("EXTRACTED WORKING MEGA DOWNLOAD LINK:")
            print(f"URL: {working_mega_url}")
            print("=" * 60)
            
            # Verify status of MEGA URL
            try:
                m_check = await session.get(working_mega_url, headers={"User-Agent": DEFAULT_UA}, timeout=10)
                print(f"MEGA URL HTTP Status: {m_check.status_code}")
            except Exception as ex:
                print(f"MEGA URL Reachability Check: {ex}")
            return working_mega_url

    print("No direct link props found in redirect page.")

if __name__ == "__main__":
    asyncio.run(extract_working_mega_url())
