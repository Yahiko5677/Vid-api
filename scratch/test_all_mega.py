import asyncio
import json
import re
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def test_extract_all_mega():
    ep_url = "https://archive.toonworld4all.me/episode/liar-game-1x2"
    print("=" * 60)
    print(f"Testing full extraction & verification for episode: {ep_url}")
    print("=" * 60)

    session = cffi_requests.AsyncSession(impersonate="chrome120")
    resp = await session.get(ep_url, headers={"User-Agent": DEFAULT_UA})

    m = re.search(r'window\.__PROPS__\s*=\s*(\{.*?\});', resp.text)
    if not m:
        print("Error: Could not parse window.__PROPS__ from episode page")
        return

    props = json.loads(m.group(1))
    encodes = props.get("data", {}).get("data", {}).get("encodes", [])
    print(f"Found {len(encodes)} quality encode options on page.\n")

    results = []

    for idx, enc in enumerate(encodes, 1):
        quality = enc.get("readable", {}).get("codec", enc.get("resolution", "Unknown"))
        size = enc.get("readable", {}).get("size", "")
        print(f"[{idx}] Quality: {quality} | Size: {size}")

        files = enc.get("files", [])
        for f in files:
            host = f.get("host", "")
            short_domain = f.get("short", "")
            redirect_rel = f.get("link", "")
            redirect_url = f"https://archive.toonworld4all.me{redirect_rel}" if redirect_rel.startswith("/") else redirect_rel

            print(f"   • Host: {host} ({short_domain})")
            print(f"     Redirect URL: {redirect_url[:70]}...")

            # Fetch redirect URL page HTML & window.__PROPS__
            try:
                r_red = await session.get(redirect_url, headers={"User-Agent": DEFAULT_UA})
                m_red = re.search(r'window\.__PROPS__\s*=\s*(\{.*?\});', r_red.text)

                if m_red:
                    p_red = json.loads(m_red.group(1))
                    link_info = p_red.get("link", {})
                    domain = link_info.get("domain", "")
                    hidden = link_info.get("hidden", "")
                    shortener_dest = p_red.get("destination", "")

                    if domain and hidden:
                        target_file_url = f"{domain}{hidden}"
                        print(f"     ==> Direct File Link: {target_file_url}")

                        # Verify target file link status
                        v_resp = await session.get(target_file_url, headers={"User-Agent": DEFAULT_UA}, allow_redirects=True)
                        v_soup = BeautifulSoup(v_resp.text, "html.parser")
                        v_title = v_soup.find("title").text.strip() if v_soup.find("title") else "N/A"

                        print(f"     [Status: HTTP {v_resp.status_code}] Title: '{v_title}'")
                        results.append({
                            "quality": quality,
                            "size": size,
                            "host": host,
                            "file_url": target_file_url,
                            "status": v_resp.status_code,
                            "title": v_title
                        })
                    else:
                        print(f"     [Shortener Gateway Required]: {shortener_dest}")
                else:
                    print("     [No React metadata on redirect page]")

            except Exception as ex:
                print(f"     Error processing redirect: {ex}")

        print("-" * 60)

    print("\n" + "=" * 60)
    print("FINAL SUMMARY OF EXTRACTED WORKING FILE LINKS:")
    print("=" * 60)
    for r in results:
        print(f"Quality : {r['quality']} ({r['size']})")
        print(f"Host    : {r['host']}")
        print(f"URL     : {r['file_url']}")
        print(f"Status  : HTTP {r['status']} | Title: {r['title']}")
        print("-" * 40)

if __name__ == "__main__":
    asyncio.run(test_extract_all_mega())

