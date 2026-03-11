import random
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from strands import tool

WEIRD_CHARS = str.maketrans({"\xa0": " ", "\u200f": "", "\u200e": ""})
MARKERS = re.compile(r"\{[פשס]\}")
VERSE_NUMS = re.compile(r"[\u05d0-\u05ea]{1,3},[\u05d0-\u05ea]{1,3}\s*")

BIBLE_DIR = Path(__file__).parent.parent.parent / "resources" / "bible_md"


def _clean(text: str) -> str:
    text = MARKERS.sub("", text.translate(WEIRD_CHARS))
    text = VERSE_NUMS.sub("", text)
    return re.sub(r" {2,}", " ", text).strip()


@tool
def fetch_bible_text(query: str) -> str:
    """Fetch relevant biblical text from mechon-mamre. Args: query: topic or keyword to look for."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "he,en-US;q=0.9"}
    try:
        resp = requests.get("https://mechon-mamre.org/i/t/t15.htm", headers=headers, timeout=30)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        return _clean(soup.get_text(separator=" ", strip=True))[:3000]
    except Exception as e:
        return f"Error: {e}"


@tool
def fetch_local_bible() -> str:
    """Return up to 3,000 characters from three randomly selected local bible books."""
    books = list(BIBLE_DIR.glob("*.md"))
    if not books:
        return "Error: no local bible files found"
    selected = random.sample(books, min(3, len(books)))
    combined = "\n\n".join(f.read_text(encoding="utf-8") for f in selected)
    return combined[:3000]
