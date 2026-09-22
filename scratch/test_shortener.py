import asyncio
from services.scraper import bypass_with_playwright

async def test_shortener():
    short_url = "https://exe.io/ysTfB"
    print(f"Testing real shortener bypass for: {short_url}")
    final_url = await bypass_with_playwright(short_url)
    print(f"Final URL after shortener bypass: {final_url}")

if __name__ == "__main__":
    asyncio.run(test_shortener())
