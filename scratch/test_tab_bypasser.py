import asyncio
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def test_tab_bypasser():
    target_url = "https://exe.io/Z3glQ3i"
    print(f"Starting multi-tab Playwright shortener bypass for: {target_url}")

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
        
        # Capture and automatically close popup tabs opened by ad networks
        main_page = await context.new_page()
        
        def handle_popup(popup_page):
            print(f"Popup detected: {popup_page.url}. Closing popunder tab...")
            asyncio.create_task(popup_page.close())
            
        context.on("page", handle_popup)

        try:
            await main_page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            
            for step in range(8):
                await main_page.wait_for_timeout(3000)
                curr_url = main_page.url
                print(f"Step {step + 1} Main Page URL: {curr_url}")

                # Check if we reached real MEGA or GDFlix destination
                if any(dom in curr_url for dom in ["mega.nz", "gdflix.dev", "new4.gdflix.io", "drive.google.com"]):
                    print(f"SUCCESS! Reached real file destination: {curr_url}")
                    break

                # Execute JS in main page to bypass ad overlays and click form submit
                action_taken = await main_page.evaluate("""() => {
                    // Remove ad overlays
                    document.querySelectorAll('iframe, a[target="_blank"], div[id*="pop"], div[class*="pop"], div[style*="z-index: 2147483647"]').forEach(el => el.remove());
                    
                    // Look for submit form
                    const form = document.forms[0];
                    if (form && typeof form.submit === 'function') {
                        form.submit();
                        return "Form submitted";
                    }
                    
                    // Look for clickable buttons
                    const btn = document.querySelector('button[type="submit"], input[type="submit"], #gotolink, .btn-captcha, a.btn');
                    if (btn) {
                        btn.click();
                        return "Clicked button: " + (btn.innerText || btn.value || btn.id);
                    }
                    return "No action taken";
                }""")
                
                print(f"JS Action Result: {action_taken}")

            print(f"Final Resolved URL: {main_page.url}")

        except Exception as e:
            print(f"Error during tab bypass: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_tab_bypasser())
