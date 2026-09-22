import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def test_exeygo_playwright():
    url = "https://exe.io/ysTfB"
    print("Testing Playwright JS shortener solver for:", url)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=DEFAULT_UA)
        page = await context.new_page()

        # Handle popup tabs automatically
        page.on("popup", lambda p: asyncio.create_task(p.close()))

        await page.goto(url, wait_until="domcontentloaded")
        print("Page 1 loaded:", page.url)

        for step in range(5):
            await page.wait_for_timeout(3000)
            curr = page.url
            print(f"Step {step+1} URL: {curr}")

            if "gdflix" in curr or "drive.google.com" in curr:
                print("SUCCESS! Reached GDFlix:", curr)
                break

            # Execute JS to submit forms or click continue buttons automatically
            js_script = """() => {
                const btn = document.querySelector('button[type="submit"], button.vhit, #btn-main, a.btn-captcha, #gotolink');
                if (btn) {
                    btn.click();
                    return "Clicked button: " + (btn.innerText || btn.className);
                }
                const form = document.querySelector('form');
                if (form) {
                    form.submit();
                    return "Submitted form";
                }
                return "No button or form found";
            }"""

            res = await page.evaluate(js_script)
            print("JS Result:", res)

        print("Final URL:", page.url)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_exeygo_playwright())
