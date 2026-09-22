import asyncio
from curl_cffi import requests as cffi_requests

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def test_lt():
    session = cffi_requests.AsyncSession(impersonate="chrome120")
    resp = await session.get("https://new4.gdflix.io/file/lt6zc7rtawtk3id", headers={"User-Agent": DEFAULT_UA})
    print("Status:", resp.status_code)
    with open("scratch/lt_gd.html", "w", encoding="utf-8") as f:
        f.write(resp.text)
    print("Saved lt_gd.html")

if __name__ == "__main__":
    asyncio.run(test_lt())
