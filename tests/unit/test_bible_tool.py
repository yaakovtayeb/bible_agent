"""
Unit tests for fetch_local_bible.
All tests use tmp_path to create fake bible files — no real files, no network calls.
"""

from pathlib import Path
from unittest.mock import patch

import agent.tools.bible as bible_module
from agent.tools.bible import fetch_local_bible


def make_bible_dir(tmp_path: Path, books: dict) -> Path:
    bible_dir = tmp_path / "bible_md"
    bible_dir.mkdir()
    for name, content in books.items():
        (bible_dir / name).write_text(content, encoding="utf-8")
    return bible_dir


def test_returns_text(tmp_path):
    bible_dir = make_bible_dir(
        tmp_path,
        {
            "בראשית.md": "# בראשית\nבְּרֵאשִׁית בָּרָא אֱלֹהִים",
            "שמות.md": "# שמות\nוְאֵלֶּה שְׁמוֹת",
            "ויקרא.md": "# ויקרא\nוַיִּקְרָא אֶל מֹשֶׁה",
        },
    )
    with patch.object(bible_module, "BIBLE_DIR", bible_dir):
        result = fetch_local_bible()
    assert isinstance(result, str)
    assert len(result) > 0


def test_truncates_to_3000(tmp_path):
    bible_dir = make_bible_dir(tmp_path, {f"book{i}.md": "א" * 2000 for i in range(3)})
    with patch.object(bible_module, "BIBLE_DIR", bible_dir):
        result = fetch_local_bible()
    assert len(result) <= 3000


def test_returns_error_when_no_files(tmp_path):
    empty_dir = tmp_path / "bible_md"
    empty_dir.mkdir()
    with patch.object(bible_module, "BIBLE_DIR", empty_dir):
        result = fetch_local_bible()
    assert "Error" in result
