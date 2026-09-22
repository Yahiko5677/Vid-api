"""
services/scraper.py

Scraper & shortlink bypass engine for Toonworld4all, GDFlix, Exeygo, Cutty, GPLinks, etc.
Features:
- Fast HTTP bypass using curl_cffi and React __PROPS__ extraction
- Stealth Playwright headless browser fallback for Cloudflare Turnstile & dynamic countdown buttons
- Link unraveling and direct GDFlix / MEGA / Filepress extraction
"""

import re
import json
import asyncio
import logging
import urllib.parse
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

logger = logging.getLogger(__name__)

# User agent for requests
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Supported domain patterns
GDFLIX_DOMAINS = ["gdflix.dev", "gdflix.top", "gdflix.pro", "gdflix.io", "new4.gdflix.io"]
SHORTENER_DOMAINS = ["exeygo.com", "exe.io", "cutty.com", "cutty.io", "gplinks.in", "gplinks.co", "gplinks.com"]


def parse_props_json(html_text: str) -> dict:
    """Extract and parse window.__PROPS__ JSON from Toonworld pages."""
    m = re.search(r'window\.__PROPS__\s*=\s*(\{.*?\});\s*</script>', html_text, re.DOTALL)
    if not m:
        m = re.search(r'window\.__PROPS__\s*=\s*(\{.*?\});', html_text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception as e:
            logger.warning(f"JSON decode error for window.__PROPS__: {e}")
    return None


async def unmask_url(url: str) -> str:
    """Follow standard HTTP redirects to unmask underlying destination."""
    try:
        session = cffi_requests.AsyncSession(impersonate="chrome120")
        resp = await session.get(url, allow_redirects=True, timeout=15, headers={"User-Agent": DEFAULT_UA})
        return str(resp.url)
    except Exception as e:
        logger.warning(f"Failed HTTP unmask for {url}: {e}")
        return url


async def bypass_with_playwright(target_url: str, timeout: int = 45) -> str:
    """
    Playwright stealth fallback for shortlinks (exeygo, cutty, gplinks, etc.)
    Wait & click through 'Continue', 'Verify', 'Skip App', timer countdown buttons.
    """
    from playwright.async_api import async_playwright

    logger.info(f"🎭 Launching Playwright browser for shortlink bypass: {target_url}")
    final_url = target_url

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        context = await browser.new_context(
            user_agent=DEFAULT_UA,
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=timeout * 1000)

            for step in range(5):
                await page.wait_for_timeout(3000)
                curr = page.url
                logger.info(f"Step {step + 1} Current URL: {curr}")

                if any(dom in curr for dom in GDFLIX_DOMAINS) or "mega.nz" in curr or "drive.google.com" in curr:
                    final_url = curr
                    break

                button_selectors = [
                    "button:has-text('Verify')", "a:has-text('Verify')",
                    "button:has-text('Continue')", "a:has-text('Continue')",
                    "button:has-text('Click here to continue')", "a:has-text('Click here to continue')",
                    "button:has-text('Skip App')", "a:has-text('Skip App')",
                    "button:has-text('Get Link')", "a:has-text('Get Link')",
                    "#gotolink", ".btn-captcha", "#btn-main", "#zero_click_wrapper a"
                ]

                clicked = False
                for sel in button_selectors:
                    elem = page.locator(sel).first
                    if await elem.is_visible(timeout=1000):
                        logger.info(f"Clicking shortlink button matching '{sel}'")
                        await elem.click()
                        clicked = True
                        await page.wait_for_timeout(2000)
                        break

                if not clicked:
                    content = await page.content()
                    soup = BeautifulSoup(content, "html.parser")
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if any(dom in href for dom in GDFLIX_DOMAINS) or "mega.nz" in href:
                            logger.info(f"Found destination link in DOM: {href}")
                            final_url = href
                            clicked = True
                            break
                    if clicked:
                        break

            final_url = page.url
        except Exception as e:
            logger.error(f"Playwright bypass error for {target_url}: {e}")
        finally:
            await browser.close()

    return final_url


async def process_toonworld_url(input_url: str) -> dict:
    """
    Main entry point:
    1. Parse Toonworld4all episode page OR redirect URL.
    2. Extract file links (MEGA, GDFlix, Filepress).
    3. If direct props exist (domain + hidden), construct working file link.
    4. Otherwise, bypass shortener via Playwright.
    """
    logger.info(f"Processing URL: {input_url}")
    output = {
        "source_url": input_url,
        "extracted_files": [],
        "status": "pending"
    }

    session = cffi_requests.AsyncSession(impersonate="chrome120")
    resp = await session.get(input_url, headers={"User-Agent": DEFAULT_UA})

    # Check if page has window.__PROPS__
    props = parse_props_json(resp.text)
    
    if props:
        # Scenario A: Episode page with encodes list
        encodes = props.get("data", {}).get("data", {}).get("encodes", [])
        if encodes:
            for enc in encodes:
                quality = enc.get("readable", {}).get("codec", enc.get("resolution", "Unknown"))
                size = enc.get("readable", {}).get("size", "")
                files = enc.get("files", [])

                for f in files:
                    host = f.get("host", "")
                    rel = f.get("link", "")
                    redirect_url = f"https://archive.toonworld4all.me{rel}" if rel.startswith("/") else rel

                    # Fetch redirect URL
                    try:
                        r_red = await session.get(redirect_url, headers={"User-Agent": DEFAULT_UA})
                        p_red = parse_props_json(r_red.text)

                        if p_red:
                            link_info = p_red.get("link", {})
                            domain = link_info.get("domain", "")
                            hidden = link_info.get("hidden", "")
                            dest = p_red.get("destination", "")

                            if domain and hidden:
                                direct_url = f"{domain}{hidden}"
                                output["extracted_files"].append({
                                    "quality": quality,
                                    "size": size,
                                    "host": host,
                                    "direct_url": direct_url,
                                    "status": "HTTP 200"
                                })
                            elif dest:
                                # Shortener bypass needed
                                bypassed = await bypass_with_playwright(dest)
                                output["extracted_files"].append({
                                    "quality": quality,
                                    "size": size,
                                    "host": host,
                                    "direct_url": bypassed,
                                    "status": "Bypassed"
                                })
                    except Exception as ex:
                        logger.warning(f"Error processing redirect URL {redirect_url}: {ex}")

            if output["extracted_files"]:
                output["status"] = "success"
                return output

        # Scenario B: Direct redirect URL page with props
        link_info = props.get("link", {})
        domain = link_info.get("domain", "")
        hidden = link_info.get("hidden", "")
        dest = props.get("destination", "")

        if domain and hidden:
            output["extracted_files"].append({
                "quality": "Direct Link",
                "size": "N/A",
                "host": "Direct",
                "direct_url": f"{domain}{hidden}",
                "status": "HTTP 200"
            })
            output["status"] = "success"
            return output

    output["status"] = "error"
    output["error"] = "Could not extract download files from given URL."
    return output
