import asyncio
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def test_exeygo_full_bypass():
    session = cffi_requests.AsyncSession(impersonate="chrome120")
    start_url = "https://exeygo.com/ysTfB"
    print(f"Starting multi-step shortener solver for: {start_url}")

    # Step 1: Initial GET
    resp1 = await session.get(start_url, headers={"User-Agent": DEFAULT_UA}, allow_redirects=True)
    soup1 = BeautifulSoup(resp1.text, "html.parser")
    form1 = soup1.find("form")
    if not form1:
        print("No form found on Step 1")
        return

    data1 = {inp.get("name"): inp.get("value", "") for inp in form1.find_all("input") if inp.get("name")}
    print(f"Step 1 form action: {form1.get('action')}, inputs: {data1}")

    # Step 2: First POST submit
    await asyncio.sleep(2) # simulate wait
    resp2 = await session.post(
        start_url,
        data=data1,
        headers={"User-Agent": DEFAULT_UA, "Referer": start_url, "Origin": "https://exeygo.com"},
        allow_redirects=True
    )
    print(f"Step 2 status: {resp2.status_code}, URL: {resp2.url}")
    soup2 = BeautifulSoup(resp2.text, "html.parser")
    form2 = soup2.find("form")
    if not form2:
        print("No form found on Step 2")
        print("Checking links on Step 2 page:")
        for a in soup2.find_all("a", href=True):
            print("  Link:", a.text.strip(), "->", a["href"])
        return

    data2 = {inp.get("name"): inp.get("value", "") for inp in form2.find_all("input") if inp.get("name")}
    print(f"Step 2 form action: {form2.get('action')}, inputs: {data2}")

    # Step 3: Second POST submit
    await asyncio.sleep(3) # wait for shortener countdown timer logic
    resp3 = await session.post(
        start_url,
        data=data2,
        headers={"User-Agent": DEFAULT_UA, "Referer": start_url, "Origin": "https://exeygo.com"},
        allow_redirects=True
    )
    print(f"Step 3 status: {resp3.status_code}, URL: {resp3.url}")
    soup3 = BeautifulSoup(resp3.text, "html.parser")
    
    # Check if we got redirected or if final link is in page
    for a in soup3.find_all("a", href=True):
        print("  Found Link step 3:", a.text.strip(), "->", a["href"])
        
    form3 = soup3.find("form")
    if form3:
        data3 = {inp.get("name"): inp.get("value", "") for inp in form3.find_all("input") if inp.get("name")}
        print(f"Step 3 form action: {form3.get('action')}, inputs: {data3}")

if __name__ == "__main__":
    asyncio.run(test_exeygo_full_bypass())

