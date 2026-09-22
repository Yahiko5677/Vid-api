import asyncio
from curl_cffi import requests as cffi_requests

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def dump():
    session = cffi_requests.AsyncSession(impersonate="chrome120")
    
    # 1. Episode page
    r1 = await session.get("https://archive.toonworld4all.me/episode/liar-game-1x2", headers={"User-Agent": DEFAULT_UA})
    with open("scratch/ep_dump.html", "w", encoding="utf-8") as f:
        f.write(r1.text)
        
    # 2. GDFlix file page
    r2 = await session.get("https://new4.gdflix.io/file/qa5x2de24sna470", headers={"User-Agent": DEFAULT_UA})
    with open("scratch/gd_dump.html", "w", encoding="utf-8") as f:
        f.write(r2.text)

    print("Dumping complete.")

if __name__ == "__main__":
    asyncio.run(dump())
