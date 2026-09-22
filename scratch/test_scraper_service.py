import asyncio
import json
from services.scraper import process_toonworld_url

async def main():
    url = "https://archive.toonworld4all.me/episode/liar-game-1x2"
    print(f"Testing process_toonworld_url for: {url}")
    result = await process_toonworld_url(url)
    print("\nExtraction Result:")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())

