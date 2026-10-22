import pytest

from textextractor.data.database import HistoryRepository


@pytest.fixture
def repo():
    now = [1_000_000.0]
    r = HistoryRepository(":memory:", clock=lambda: now[0])
    r.now = now
    yield r
    r.close()


def test_insert_and_get(repo):
    i = repo.insert("Hello world", "/tmp/a.png")
    e = repo.get(i)
    assert (e.text, e.image_path, e.is_favorite, e.title) == ("Hello world", "/tmp/a.png", False, None)
    assert repo.get(999) is None


def test_search_text_and_title_case_insensitive_and_literal(repo):
    a = repo.insert("Electricity bill March")
    repo.insert("Shopping list: eggs, milk")
    repo.insert("100% cotton_shirt")
    repo.rename(a, "Utilities")
    assert len(repo.search("ELECTRIC")) == 1
    assert len(repo.search("utilit")) == 1
    assert len(repo.search("milk")) == 1
    assert repo.search("nothing") == []
    assert len(repo.search("")) == 3
    assert len(repo.search("100%")) == 1       # % is literal, not a wildcard
    assert len(repo.search("%")) == 1
    assert len(repo.search("_")) == 1


def test_update_rename_favorite(repo):
    i = repo.insert("old")
    repo.now[0] += 10
    repo.update_text(i, "new text")
    repo.rename(i, "  My title ")
    repo.set_favorite(i, True)
    e = repo.get(i)
    assert (e.text, e.title, e.is_favorite) == ("new text", "My title", True)
    assert e.updated_at > e.created_at
    repo.rename(i, "   ")
    assert repo.get(i).title is None


def test_order_recent_delete_clear(repo):
    ids = []
    for t in ("first", "second", "third"):
        ids.append(repo.insert(t))
        repo.now[0] += 1
    assert [e.text for e in repo.search()] == ["third", "second", "first"]
    assert [e.text for e in repo.recent(2)] == ["third", "second"]
    repo.delete(ids[0])
    assert repo.count() == 2
    repo.clear_all()
    assert repo.count() == 0


def test_auto_clear_keeps_favorites_and_recent(repo):
    old_fav = repo.insert("old favorite")
    repo.set_favorite(old_fav, True)
    repo.insert("old plain")
    repo.now[0] += 40 * 86400
    repo.insert("fresh")
    assert repo.delete_older_than_days(30) == 1
    assert {e.text for e in repo.search()} == {"old favorite", "fresh"}


def test_restore_after_delete(repo):
    i = repo.insert("undo me")
    e = repo.get(i)
    repo.delete(i)
    assert repo.get(i) is None
    repo.restore(e)
    assert repo.get(i).text == "undo me"


def test_file_database_persists_and_is_owner_only(tmp_path):
    path = tmp_path / "sub" / "h.db"
    r = HistoryRepository(path)
    r.insert("persist me")
    r.close()
    assert HistoryRepository(path).search()[0].text == "persist me"
    import os
    if os.name == "posix":
        assert (path.stat().st_mode & 0o077) == 0
