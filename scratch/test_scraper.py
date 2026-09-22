import asyncio
import sys
import logging

logging.basicConfig(level=logging.INFO)

from services.scraper import process_toonworld_url

async def main():
    urls = [
        "https://archive.toonworld4all.me/episode/liar-game-1x2",
        "https://archive.toonworld4all.me/redirect/6d7bc1e263a9a2eebbe01107971ee36fa567903e828ff5544405bc14553754de04a9f172864cc524d709ca6f5dd24fac7e568c12a91c85c03a43f1218ad12cce740ff8dd6ff0fd210bb4c78a1f365f1d"
    ]
    for url in urls:
        print(f"\n==========================================")
        print(f"Testing URL: {url}")
        print(f"==========================================")
        res = await process_toonworld_url(url)
        print("RESULT:")
        print(res)

if __name__ == "__main__":
    asyncio.run(main())
