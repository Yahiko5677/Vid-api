import asyncio
import json
import re
from curl_cffi import requests as cffi_requests
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def test_resolve_mega():
    ep_url = "https://archive.toonworld4all.me/episode/liar-game-1x2"
    print(f"Fetching episode page: {ep_url}")

    session = cffi_requests.AsyncSession(impersonate="chrome120")
    resp = await session.get(ep_url, headers={"User-Agent": DEFAULT_UA})

    m = re.search(r'window\.__PROPS__\s*=\s*(\{.*?\});', resp.text)
    if not m:
        print("Error: Could not parse window.__PROPS__ from episode page")
        return

    props = json.loads(m.group(1))
    encodes = props.get("data", {}).get("data", {}).get("encodes", [])
    
    mega_file = None
    for enc in encodes:
        quality = enc.get("readable", {}).get("codec", enc.get("resolution", "Unknown"))
        files = enc.get("files", [])
        for f in files:
            host = f.get("host", "")
            if "mega" in host.lower():
                redirect_rel = f.get("link", "")
                redirect_url = f"https://archive.toonworld4all.me{redirect_rel}" if redirect_rel.startswith("/") else redirect_rel
                mega_file = {
                    "quality": quality,
                    "host": host,
                    "redirect_url": redirect_url
                }
                break
        if mega_file:
            break

    if not mega_file:
        print("No MEGA redirect found!")
        return

    print(f"Target MEGA Redirect found for [{mega_file['quality']}]: {mega_file['redirect_url']}")
    
    # First check what the redirect page returns
    r_red = await session.get(mega_file['redirect_url'], headers={"User-Agent": DEFAULT_UA})
    print(f"Redirect page HTTP Status: {r_red.status_code}")
    
    m_red = re.search(r'window\.__PROPS__\s*=\s*(\{.*?\});', r_red.text)
    if m_red:
        p_red = json.loads(m_red.group(1))
        print("Redirect page props keys:", list(p_red.keys()))
        print("Props json:\n", json.dumps(p_red, indent=2))
        
        # Check link / destination in props
        link_info = p_red.get("link", {})
        dest = p_red.get("destination", "")
        domain = link_info.get("domain", "")
        hidden = link_info.get("hidden", "")
        if domain and hidden:
            print(f"Direct MEGA/Host Link: {domain}{hidden}")
            return
        elif dest:
            print(f"Shortener destination: {dest}")
            target_shortener = dest
        elif link_info.get("url"):
            print(f"Link info URL: {link_info.get('url')}")
            target_shortener = link_info.get("url")
        else:
            target_shortener = mega_file['redirect_url']
    else:
        print("No props on redirect page, using raw HTML inspection...")
        soup = BeautifulSoup(r_red.text, "html.parser")
        meta_refresh = soup.find("meta", attrs={"http-equiv": re.compile(r'refresh', re.I)})
        if meta_refresh:
            print("Meta refresh:", meta_refresh.get("content"))
        a_tags = soup.find_all("a", href=True)
        for a in a_tags:
            print(f"Link: {a['href']} (Text: '{a.text.strip()}')")
        target_shortener = mega_file['redirect_url']

    # Now use Playwright to follow target_shortener URL
    print(f"\nLaunching Playwright browser to resolve: {target_shortener}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=DEFAULT_UA)
        page = await context.new_page()

        # Monitor redirected URLs or new tabs
        dest_urls = []
        page.on("framenavigated", lambda frame: dest_urls.append(frame.url))

        try:
            await page.goto(target_shortener, wait_until="domcontentloaded", timeout=30000)
            print("Loaded page final URL:", page.url)
            print("Page title:", await page.title())

            # Evaluate any props or destination link in window
            props = await page.evaluate("() => window.__PROPS__ || null")
            if props:
                print("JS window.__PROPS__:", json.dumps(props, indent=2))

            # Look for mega.nz link anywhere in the page DOM
            mega_match = await page.evaluate("""() => {
                const anchors = Array.from(document.querySelectorAll('a[href*="mega.nz"], a[href*="mega.co.nz"]'));
                if (anchors.length > 0) return anchors[0].href;
                const bodyText = document.body.innerText;
                const m = bodyText.match(/https:\\/\\/mega\\.(?:nz|co\\.nz)\\/[^\\s"']+/);
                return m ? m[0] : null;
            }""")

            if mega_match:
                print(f"\n[SUCCESS] Extracted Working MEGA URL: {mega_match}")
            else:
                print("No direct mega.nz link in current DOM. Checking redirects history:", dest_urls)
                
        except Exception as e:
            print(f"Playwright error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_resolve_mega())

