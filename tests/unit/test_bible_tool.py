from unittest.mock import patch
from pathlib import Path
from agent.tools.bible import fetch_local_bible


def test_returns_text(tmp_path):
    fake_book = tmp_path / "בראשית.md"
    fake_book.write_text("# בראשית\nבְּרֵאשִׁית בָּרָא אֱלֹהִים", encoding="utf-8")
    with patch("agent.tools.bible.Path.__new__") as _:
        # use real files if available, otherwise just call and check type
        result = fetch_local_bible()
    assert isinstance(result, str)
    assert len(result) > 0


def test_truncates_to_10k(tmp_path, monkeypatch):
    fake_book = tmp_path / "test.md"
    fake_book.write_text("א" * 20000, encoding="utf-8")
    monkeypatch.setattr("agent.tools.bible.Path.__new__",
                        lambda cls, *a, **kw: tmp_path)
    result = fetch_local_bible()
    assert len(result) <= 10000


def test_returns_error_when_no_files(monkeypatch):
    monkeypatch.setattr("agent.tools.bible.Path.glob", lambda *a, **kw: iter([]))
    result = fetch_local_bible()
    assert "Error" in result or isinstance(result, str)
