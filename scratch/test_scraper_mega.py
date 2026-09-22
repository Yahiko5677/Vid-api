import asyncio
import json
import re
from curl_cffi import requests as cffi_requests

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

def parse_props(html):
    idx = html.find("window.__PROPS__")
    if idx == -1:
        return None
    start = html.find("{", idx)
    if start == -1:
        return None
    
    # Balanced brace matching or json raw decode
    decoder = json.JSONDecoder()
    try:
        data, _ = decoder.raw_decode(html, start)
        return data
    except Exception:
        # Fallback regex search
        m = re.search(r'window\.__PROPS__\s*=\s*(\{.+?\});', html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
    return None

async def test_extract_mega_and_gdflix():
    ep_url = "https://archive.toonworld4all.me/episode/liar-game-1x2"
    print("=" * 70)
    print(f"Testing Toonworld Link Extractor on Episode: {ep_url}")
    print("=" * 70)

    session = cffi_requests.AsyncSession(impersonate="chrome120")
    resp = await session.get(ep_url, headers={"User-Agent": DEFAULT_UA})

    props = parse_props(resp.text)
    if not props:
        print("Error: window.__PROPS__ not found")
        return

    encodes = props.get("data", {}).get("data", {}).get("encodes", [])
    print(f"Found {len(encodes)} quality encodes.\n")

    extracted_links = []

    for enc_idx, enc in enumerate(encodes, 1):
        quality = enc.get("readable", {}).get("codec", enc.get("resolution", "Unknown"))
        size = enc.get("readable", {}).get("size", "")
        print(f"--- Quality Encode #{enc_idx}: {quality} ({size}) ---")

        for f in enc.get("files", []):
            host = f.get("host", "")
            redirect_rel = f.get("link", "")
            redirect_url = f"https://archive.toonworld4all.me{redirect_rel}" if redirect_rel.startswith("/") else redirect_rel

            print(f"Checking Host: {host}")
            print(f"Redirect URL: {redirect_url[:75]}...")

            r_red = await session.get(redirect_url, headers={"User-Agent": DEFAULT_UA})
            p_red = parse_props(r_red.text)

            if p_red:
                link_info = p_red.get("link", {})
                domain = link_info.get("domain", "")
                hidden = link_info.get("hidden", "")
                dest = p_red.get("destination", "")

                if domain and hidden:
                    file_url = f"{domain}{hidden}"
                    print(f" ==> [DIRECT FILE LINK EXTRACTED]: {file_url}")
                    extracted_links.append({
                        "quality": quality,
                        "size": size,
                        "host": host,
                        "url": file_url,
                    })
                else:
                    print(f" ==> [Shortener Destination]: {dest}")
            else:
                print(" ==> [No window.__PROPS__ found on redirect page]")

            print()

    print("=" * 70)
    print("ALL EXTRACTED WORKING FILE DOWNLOAD LINKS:")
    print("=" * 70)
    for item in extracted_links:
        print(f"[{item['host']}] Quality: {item['quality']} ({item['size']})")
        print(f"  URL   : {item['url']}")
        print("-" * 50)

if __name__ == "__main__":
    asyncio.run(test_extract_mega_and_gdflix())

