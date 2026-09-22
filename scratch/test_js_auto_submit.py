import asyncio
from playwright.async_api import async_playwright

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def test_exeygo_form_auto_submit():
    url = "https://exe.io/ysTfB"
    print("Testing JS form auto-submitter for:", url)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=DEFAULT_UA)
        page = await context.new_page()

        page.on("popup", lambda p: asyncio.create_task(p.close()))

        await page.goto(url, wait_until="networkidle")
        print("Page loaded:", page.url)

        for step in range(5):
            await page.wait_for_timeout(4000)
            curr = page.url
            print(f"Step {step+1} URL: {curr}")

            if any(dom in curr for dom in ["gdflix", "drive.google.com"]):
                print("SUCCESS! Reached target:", curr)
                break

            # Execute JS script inside page context to trigger form submission
            res = await page.evaluate("""() => {
                const forms = document.forms;
                if (forms.length > 0) {
                    const form = forms[0];
                    if (typeof form.submit === 'function') {
                        form.submit();
                        return "Triggered form.submit()";
                    }
                }
                const btn = document.querySelector('button[type="submit"], input[type="submit"], #gotolink, .btn-captcha');
                if (btn) {
                    btn.click();
                    return "Clicked button element: " + (btn.innerText || btn.value || btn.id);
                }
                return "No form or button found";
            }""")

            print("JS Script Output:", res)

        print("Final Page URL:", page.url)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_exeygo_form_auto_submit())

