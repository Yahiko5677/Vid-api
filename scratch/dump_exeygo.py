import asyncio
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def dump_exeygo():
    session = cffi_requests.AsyncSession(impersonate="chrome120")
    resp = await session.get("https://exeygo.com/ysTfB", headers={"User-Agent": DEFAULT_UA}, allow_redirects=True)
    print("Exeygo URL:", resp.url)
    print("Status:", resp.status_code)
    soup = BeautifulSoup(resp.text, "html.parser")
    forms = soup.find_all("form")
    print(f"Found {len(forms)} forms:")
    for f in forms:
        print("  Form action:", f.get("action"))
        for inp in f.find_all("input"):
            print("    Input:", inp.get("name"), "=", inp.get("value"))

if __name__ == "__main__":
    asyncio.run(dump_exeygo())
