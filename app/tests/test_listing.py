from tamlil import config, db as dbm, fetch, worker


def test_channels_list_in_batches(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    uploads = [{"id": f"v{i:02d}", "title": f"Video {i}"} for i in range(25)]      # newest first
    monkeypatch.setattr(fetch, "list_entries", lambda url: ("channel", "Chan", list(uploads)))
    monkeypatch.setattr(fetch, "video_info", lambda vid: {
        "id": vid, "title": vid, "channel": "Chan", "upload_date": "20260101", "duration": 60,
        "description": "", "language": "en", "manual": {}, "auto": {}, "live_status": None})
    db = dbm.connect()
    db.execute("insert into source(url, lang) values ('https://www.youtube.com/@chan', 'en')")
    state = lambda: db.execute("select state from source").fetchone()[0]
    count = lambda: db.execute("select count(*) from video").fetchone()[0]

    assert worker.refresh_due(db) and count() == 10 and state() == "more"
    assert not worker.refresh_due(db)              # transcripts first: 10 videos are waiting
    db.execute("update video set state='ready'")
    assert worker.refresh_due(db) and count() == 20 and state() == "more"
    db.execute("update video set state='ready'")
    assert worker.refresh_due(db) and count() == 25 and state() == "ok"

    # six hours later, two new uploads on top: the incremental listing finds them and stops
    uploads[:0] = [{"id": "new1", "title": "N1"}, {"id": "new2", "title": "N2"}]
    db.execute("update video set state='ready'")
    db.execute("update source set checked_at=datetime('now', '-7 hours')")
    assert worker.refresh_due(db) and count() == 27 and state() == "ok"
