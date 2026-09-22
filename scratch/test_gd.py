import asyncio
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def test_gd():
    session = cffi_requests.AsyncSession(impersonate="chrome120")
    url = "https://gdflix.dev/file/qpn9r1pelvcb1k9"
    resp = await session.get(url, headers={"User-Agent": DEFAULT_UA}, allow_redirects=True)
    print("Final GDFlix URL:", resp.url)
    print("Status code:", resp.status_code)
    
    if resp.status_code == 404:
        for alt in ["new4.gdflix.io", "gdflix.top", "gdflix.pro"]:
            alt_url = f"https://{alt}/file/qpn9r1pelvcb1k9"
            print(f"Trying alt GDFlix: {alt_url}")
            r_alt = await session.get(alt_url, headers={"User-Agent": DEFAULT_UA}, allow_redirects=True)
            print(f"Alt {alt} status:", r_alt.status_code)
            if r_alt.status_code == 200:
                print("Found working page!")
                soup = BeautifulSoup(r_alt.text, "html.parser")
                print("Title:", soup.find("title").text if soup.find("title") else "N/A")
                for a in soup.find_all("a", href=True):
                    print("  Found Link:", a.text.strip(), "->", a["href"])

if __name__ == "__main__":
    asyncio.run(test_gd())
