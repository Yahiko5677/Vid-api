import asyncio
from curl_cffi import requests as cffi_requests

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def dump_live():
    session = cffi_requests.AsyncSession(impersonate="chrome120")
    resp = await session.get("https://new4.gdflix.io/file/qpn9r1pelvcb1k9", headers={"User-Agent": DEFAULT_UA}, allow_redirects=True)
    with open("scratch/live_gd.html", "w", encoding="utf-8") as f:
        f.write(resp.text)
    print("Live GDFlix page saved.")

if __name__ == "__main__":
    asyncio.run(dump_live())
