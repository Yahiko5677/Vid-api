import asyncio
import re
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def test_exeygo_post():
    session = cffi_requests.AsyncSession(impersonate="chrome120")
    url = "https://exeygo.com/ysTfB"
    
    # 1. GET page to get CSRF token and form fields
    resp1 = await session.get(url, headers={"User-Agent": DEFAULT_UA}, allow_redirects=True)
    soup1 = BeautifulSoup(resp1.text, "html.parser")
    form = soup1.find("form")
    
    if not form:
        print("No form found")
        return
        
    data = {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        val = inp.get("value", "")
        if name:
            data[name] = val
            
    print("Submitting POST data:", data)
    
    # 2. POST form back to exeygo
    resp2 = await session.post(
        url,
        data=data,
        headers={
            "User-Agent": DEFAULT_UA,
            "Referer": url,
            "Origin": "https://exeygo.com"
        },
        allow_redirects=True
    )
    print("POST Response URL:", resp2.url)
    print("POST Response Status:", resp2.status_code)
    
    soup2 = BeautifulSoup(resp2.text, "html.parser")
    print("Title of step 2:", soup2.find("title").text if soup2.find("title") else "N/A")
    
    # Look for links or forms in step 2
    for a in soup2.find_all("a", href=True):
        print("  Found Link step 2:", a.text.strip(), "->", a["href"])
        
    form2 = soup2.find("form")
    if form2:
        print("Step 2 Form found with action:", form2.get("action"))
        data2 = {inp.get("name"): inp.get("value", "") for inp in form2.find_all("input") if inp.get("name")}
        print("Step 2 Form data:", data2)
        resp3 = await session.post(
            url,
            data=data2,
            headers={
                "User-Agent": DEFAULT_UA,
                "Referer": url,
                "Origin": "https://exeygo.com"
            },
            allow_redirects=True
        )
        print("Step 3 Response URL:", resp3.url)
        soup3 = BeautifulSoup(resp3.text, "html.parser")
        for a in soup3.find_all("a", href=True):
            print("  Found Link step 3:", a.text.strip(), "->", a["href"])

if __name__ == "__main__":
    asyncio.run(test_exeygo_post())
