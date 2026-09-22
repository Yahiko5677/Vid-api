import sys
import os
import json
import re
from bs4 import BeautifulSoup
from curl_cffi import requests
from playwright.sync_api import sync_playwright

def inspect_toonworld_episode(url):
    print(f"Fetching episode page: {url}")
    session = requests.Session(impersonate="chrome120")
    res = session.get(url)
    
    match = re.search(r'window\.__PROPS__\s*=\s*(\{.*?\});?</script>', res.text, re.DOTALL)
    if not match:
        print("No window.__PROPS__ found!")
        return []
    
    data = json.loads(match.group(1))
    post = data.get("pageProps", {}).get("post", {})
    redirects = post.get("redirects", [])
    
    mega_redirects = []
    for r in redirects:
        label = r.get("label", "")
        if "mega" in label.lower():
            red_url = f"https://archive.toonworld4all.me/redirect/{r.get('id')}"
            quality = r.get("quality", "Unknown")
            size = r.get("size", "Unknown")
            mega_redirects.append({
                "quality": quality,
                "size": size,
                "redirect_url": red_url
            })
    return mega_redirects

def resolve_redirect_page(redirect_url):
    print(f"\n--- Resolving Redirect Page: {redirect_url} ---")
    session = requests.Session(impersonate="chrome120")
    res = session.get(redirect_url)
    print(f"HTTP Status: {res.status_code}")
    
    # Check for window.__PROPS__
    match = re.search(r'window\.__PROPS__\s*=\s*(\{.*?\});?</script>', res.text, re.DOTALL)
    if match:
        data = json.loads(match.group(1))
        print("Found window.__PROPS__ on redirect page:")
        print(json.dumps(data, indent=2)[:1000])
        # Look for target url in props
        link = data.get("pageProps", {}).get("link", {})
        if link:
            print("Link object in props:", link)
    else:
        print("No window.__PROPS__ found directly in HTML.")
        soup = BeautifulSoup(res.text, 'html.parser')
        # Check form actions, standard scripts, or iframe links
        forms = soup.find_all('form')
        for f in forms:
            print(f"Form action: {f.get('action')}, inputs: {[{i.get('name'): i.get('value')} for i in f.find_all('input')]}")
            
        links = soup.find_all('a')
        for a in links[:10]:
            print(f"Link text: '{a.get_text(strip=True)}', href: '{a.get('href')}'")
            
    return res.text

def main():
    episode_url = "https://archive.toonworld4all.me/episode/liar-game-1x2"
    mega_list = inspect_toonworld_episode(episode_url)
    print(f"Found {len(mega_list)} MEGA redirect URLs:")
    for item in mega_list:
        print(f"Quality: {item['quality']} | Size: {item['size']} -> {item['redirect_url']}")
        
    if mega_list:
        # Resolve the first MEGA redirect
        html = resolve_redirect_page(mega_list[0]['redirect_url'])
        
        # Test playwright headless on this redirect URL
        print("\nAttempting Playwright navigation on redirect URL...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(mega_list[0]['redirect_url'], wait_until="domcontentloaded", timeout=30000)
            print("Playwright loaded URL:", page.url)
            print("Playwright page title:", page.title())
            
            # Check window.__PROPS__ via JS evaluate
            props = page.evaluate("() => window.__PROPS__ || null")
            if props:
                print("JS evaluated __PROPS__:", json.dumps(props, indent=2)[:1000])
            
            # Check if page redirected or has click button
            buttons = page.query_selector_all("button, a.btn, input[type='submit']")
            print(f"Found {len(buttons)} potential click targets.")
            for btn in buttons[:5]:
                try:
                    txt = btn.inner_text() or btn.get_attribute("value") or ""
                    print(f"Button/Link: '{txt.strip()}' | tag: {btn.evaluate('el => el.tagName')}")
                except Exception as e:
                    pass
            browser.close()

if __name__ == "__main__":
    main()

