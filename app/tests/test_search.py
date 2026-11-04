import pytest

from tamlil import config, db as dbm
from tamlil.search import search


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    d = dbm.connect()
    d.execute("insert into source(id, url, lang) values (1, 'https://a', 'he'), (2, 'https://b', 'en')")
    videos = [
        ("a1", 1, "בריאת הרקיע · שיעור 3", "20261028", ["ויאמר אלהים יהי רקיע", "ויקרא אלהים לרקיע שמים", "השמים מספרים"]),
        ("a2", 1, "המים העליונים", "20261021", ["המים אשר מעל לרקיע"]),
        ("a3", 1, "אור ביום הראשון", "20261007", ["שוב הבדלה כמו ברקיע"]),
        ("b1", 2, "Day Two: The Firmament", "20261030", ["let there be a firmament", "the firmament is stretched out"]),
    ]
    for vid, src, title, day, lines in videos:
        d.execute("insert into video(id, source_id, title, upload_date, lang) values (?,?,?,?,?)",
                  (vid, src, title, day, "en" if src == 2 else "he"))
        segs = [{"start_ms": i * 10_000, "end_ms": i * 10_000 + 5000, "text": t} for i, t in enumerate(lines)]
        dbm.save_transcript(d, vid, segs, "uploader", None, None)
    return d


def ids(r):
    return [x["video"]["id"] for x in r["results"]]


def test_source_title_and_dates(db):
    assert set(ids(search(db, "רקיע"))) == {"a1", "a2", "a3"}
    assert ids(search(db, "רקיע", source=2)) == []
    assert ids(search(db, "firmament", source=2)) == ["b1"]
    assert ids(search(db, "רקיע", title="שיעור")) == ["a1"]
    assert ids(search(db, "רקיע", title="המים העליונים")) == ["a2"]          # every word, anywhere in the title
    assert ids(search(db, "רקיע", title="100%")) == []                       # % is a letter here, not a wildcard
    assert set(ids(search(db, "רקיע", date_from="2026-10-15"))) == {"a1", "a2"}
    assert ids(search(db, "רקיע", date_from="2026-10-15", date_to="2026-10-25")) == ["a2"]
    assert set(ids(search(db, "רקיע", date_to="nonsense"))) == {"a1", "a2", "a3"}   # a bad date is no limit


def test_sorting(db):
    assert ids(search(db, "רקיע", sort="newest")) == ["a1", "a2", "a3"]
    assert ids(search(db, "רקיע", sort="oldest")) == ["a3", "a2", "a1"]
    assert ids(search(db, "רקיע", sort="moments"))[0] == "a1"                 # two lines say it there
    assert set(ids(search(db, "רקיע", sort="whatever"))) == {"a1", "a2", "a3"}
