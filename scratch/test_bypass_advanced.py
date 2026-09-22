import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def test_bypass_advanced():
    target_url = "https://exe.io/ysTfB"
    print(f"Starting advanced Playwright bypass test for: {target_url}")

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

        # Close any popups automatically
        page.on("popup", lambda popup: asyncio.create_task(popup.close()))

        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=45000)

            for step in range(6):
                await page.wait_for_timeout(3000)
                curr_url = page.url
                print(f"Step {step + 1} Current URL: {curr_url}")

                if "gdflix" in curr_url or "drive.google.com" in curr_url:
                    print(f"Reached destination: {curr_url}")
                    break

                # Remove ad overlays and popunders from DOM
                await page.evaluate("""() => {
                    document.querySelectorAll('iframe, a[target="_blank"], div[id*="pop"], div[class*="pop"], div[style*="z-index: 2147483647"]').forEach(el => el.remove());
                }""")

                # Try clicking buttons with force=True
                button_selectors = [
                    "button:has-text('Continue')", "a:has-text('Continue')",
                    "button:has-text('Verify')", "a:has-text('Verify')",
                    "button:has-text('Skip App')", "a:has-text('Skip App')",
                    "button:has-text('Get Link')", "a:has-text('Get Link')",
                    "button.btn-captcha", "#btn-main", "#gotolink"
                ]

                clicked = False
                for sel in button_selectors:
                    elem = page.locator(sel).first
                    if await elem.is_visible(timeout=1000):
                        print(f"Clicking button: '{sel}'")
                        try:
                            await elem.click(force=True, timeout=5000)
                            clicked = True
                            await page.wait_for_timeout(3000)
                            break
                        except Exception as ex:
                            print(f"Click warning on {sel}: {ex}")

                if not clicked:
                    content = await page.content()
                    soup = BeautifulSoup(content, "html.parser")
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "gdflix" in href or "drive.google.com" in href:
                            print(f"Found target link in HTML: {href}")
                            curr_url = href
                            clicked = True
                            break
                    if clicked:
                        break

            print(f"Final Resolved URL: {page.url}")

        except Exception as e:
            print(f"Error during bypass: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_bypass_advanced())
