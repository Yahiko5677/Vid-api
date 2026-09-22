import asyncio
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def check_step2():
    session = cffi_requests.AsyncSession(impersonate="chrome120")
    url = "https://exeygo.com/ysTfB"
    
    r1 = await session.get(url, headers={"User-Agent": DEFAULT_UA})
    soup1 = BeautifulSoup(r1.text, "html.parser")
    f1 = soup1.find("form")
    d1 = {inp.get("name"): inp.get("value", "") for inp in f1.find_all("input") if inp.get("name")}
    
    # POST 1
    r2 = await session.post(url, data=d1, headers={"User-Agent": DEFAULT_UA, "Referer": url})
    print("=== STEP 2 HTML SNIPPET ===")
    print(r2.text[:3000])
    
    soup2 = BeautifulSoup(r2.text, "html.parser")
    f2 = soup2.find("form")
    if f2:
        d2 = {inp.get("name"): inp.get("value", "") for inp in f2.find_all("input") if inp.get("name")}
        r3 = await session.post(url, data=d2, headers={"User-Agent": DEFAULT_UA, "Referer": url})
        print("=== STEP 3 HTML SNIPPET ===")
        print(r3.text[:3000])

if __name__ == "__main__":
    asyncio.run(check_step2())
