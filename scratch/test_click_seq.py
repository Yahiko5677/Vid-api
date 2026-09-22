import asyncio
from playwright.async_api import async_playwright

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def test_manual_click_sequence():
    url = "https://exe.io/Z3glQ3i"
    print("Testing manual element click sequence for:", url)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=DEFAULT_UA)
        page = await context.new_page()

        page.on("popup", lambda pop: asyncio.create_task(pop.close()))

        await page.goto(url, wait_until="domcontentloaded")
        print("Initial URL:", page.url)

        # Step 1: Wait & click Continue
        await page.wait_for_timeout(3000)
        btn1 = page.locator("button[data-ref='continue'], button:has-text('Continue')").first
        if await btn1.is_visible():
            print("Found Step 1 Continue button, clicking...")
            await btn1.click(force=True)
            await page.wait_for_timeout(4000)
            print("Post Step 1 URL:", page.url)

        # Step 2: Wait & click Verify / Recaptcha / Submit
        btn2 = page.locator("button:has-text('Verify'), #btn-main, button.vhit").first
        if await btn2.is_visible():
            print("Found Step 2 button, clicking...")
            await btn2.click(force=True)
            await page.wait_for_timeout(4000)
            print("Post Step 2 URL:", page.url)

        # Step 3: Check for Get Link
        btn3 = page.locator("#gotolink, a:has-text('Get Link'), button:has-text('Get Link')").first
        if await btn3.is_visible():
            print("Found Step 3 Get Link button, clicking...")
            await btn3.click(force=True)
            await page.wait_for_timeout(4000)
            print("Post Step 3 URL:", page.url)

        print("Final Resolved Page URL:", page.url)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_manual_click_sequence())
