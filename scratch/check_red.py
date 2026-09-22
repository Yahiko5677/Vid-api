import asyncio
import json
import re
from curl_cffi import requests as cffi_requests

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def check():
    session = cffi_requests.AsyncSession(impersonate="chrome120")
    url = "https://archive.toonworld4all.me/redirect/65c54e53cfb546dca74c299a45b7d633e1ff7ac5f178c86139d2870ce810ea93a322749081fad46b84dfdbd40f7f7354af11e43d7e2b6d5492544003788eb0f02b1253dc1f0c4b9e058f80de0bb607e9"
    resp = await session.get(url, headers={"User-Agent": DEFAULT_UA})
    m = re.search(r'window\.__PROPS__\s*=\s*(\{.*?\});', resp.text)
    if m:
        props = json.loads(m.group(1))
        print("PROPS DATA:")
        print(json.dumps(props, indent=2))
    else:
        print("No window.__PROPS__ found")

if __name__ == "__main__":
    asyncio.run(check())
