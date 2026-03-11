import re
import requests
from bs4 import BeautifulSoup
from strands import tool


@tool
def fetch_bible_text(query: str) -> str:
    """Fetch relevant biblical text from mechon-mamre. Args: query: topic or keyword to look for."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "he,en-US;q=0.9"}
    try:
        resp = requests.get("https://mechon-mamre.org/i/t/t15.htm", headers=headers, timeout=30)
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        return re.sub(r" {3,}", " ", text).strip()[:3000]
    except Exception as e:
        return f"Error: {e}"
