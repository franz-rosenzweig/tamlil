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


BOT = "ERROR: [youtube] abc: Sign in to confirm you're not a bot. Use --cookies-from-browser"


def _info(vid, day="20260101"):
    return {"id": vid, "title": vid, "channel": "Chan", "upload_date": day, "duration": 60, "description": "",
            "language": "en", "manual": {}, "auto": {}, "live_status": None}


def test_a_bot_check_waits_instead_of_failing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "GLUETUN_URL", "")
    monkeypatch.setattr(fetch, "list_entries", lambda url: ("channel", "Chan", [{"id": "a"}, {"id": "b"}]))

    def blocked(vid):
        raise RuntimeError(BOT)
    monkeypatch.setattr(fetch, "video_info", blocked)
    db = dbm.connect()
    db.execute("insert into source(url, lang) values ('https://www.youtube.com/@chan', 'en')")

    # listing: nothing is written down as an error, the source stays new, and the worker holds off
    assert worker.refresh_due(db)
    assert db.execute("select count(*) from video").fetchone()[0] == 0
    assert db.execute("select state, error from source").fetchone()[:] == ("new", None)
    assert worker.held(db) and dbm.get_status(db)["doing"] == "blocked"

    # a video that was waiting stays waiting, with no attempt counted
    db.execute("insert into video(id, source_id, state, tracks) values ('w', 1, 'new', null)")
    db.execute("delete from kv where key='blocked_until'")
    db.execute("update source set state='ok', checked_at=datetime('now')")
    assert not worker.held(db)
    assert worker.process_next(db)
    assert db.execute("select state, attempts, error from video where id='w'").fetchone()[:] == ("new", 0, None)
    assert worker.held(db)


def test_a_single_video_isnt_listed_again(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    db = dbm.connect()
    db.execute("insert into source(url, kind, state, checked_at) values"
               " ('https://www.youtube.com/watch?v=x', 'video', 'ok', datetime('now', '-3 days'))")
    assert not worker.refresh_due(db)


def test_a_video_listed_without_details_still_gets_its_range_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(fetch, "video_info", lambda vid: _info(vid, day="20250301"))
    db = dbm.connect()
    db.execute("insert into source(url, lang, date_from, state, checked_at) values"
               " ('https://www.youtube.com/@chan', 'en', '2026-06-01', 'ok', datetime('now'))")
    db.execute("insert into video(id, source_id, state, attempts, retry_at) values ('old', 1, 'error', 1, 0)")
    assert worker.process_next(db)
    assert db.execute("select state from video").fetchone()[0] == "out_of_range"


PROXY = ("ERROR: [youtube] abc: Unable to download API page: ('Unable to connect to proxy', "
         "OSError('Tunnel connection failed: 503 Service Unavailable'))")


def test_no_connection_through_the_vpn_counts_nothing_and_turns_it_on(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "GLUETUN_URL", "http://gluetun:8000")
    monkeypatch.setattr(config, "GLUETUN_KEY", "k")
    calls = []

    def gluetun(method, path, **kw):
        calls.append((method, kw.get("json")))
        return {"status": "stopped"}
    monkeypatch.setattr(worker, "_gluetun", gluetun)

    def down(*a):
        raise RuntimeError(PROXY)
    monkeypatch.setattr(fetch, "list_entries", down)
    monkeypatch.setattr(fetch, "video_info", down)
    db = dbm.connect()
    db.execute("insert into source(url, lang) values ('https://www.youtube.com/@chan', 'en')")

    assert worker.refresh_due(db)
    assert db.execute("select state, error from source").fetchone()[:] == ("new", None)
    assert worker.held(db) and dbm.get_status(db)["doing"] == "offline"
    assert ("PUT", {"status": "running"}) in calls

    db.execute("delete from kv where key='offline_until'")
    db.execute("update source set state='ok', checked_at=datetime('now')")
    db.execute("insert into video(id, source_id, state, tracks) values ('w', 1, 'new', null)")
    assert worker.process_next(db)
    assert db.execute("select state, attempts, error from video").fetchone()[:] == ("new", 0, None)


def test_changing_server_always_leaves_the_vpn_on(monkeypatch):
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)
    calls, state = [], {"vpn": "running"}

    def gluetun(method, path, **kw):
        import httpx
        calls.append((method, path, kw.get("json")))
        if method == "PUT" and kw["json"]["status"] == "stopped":
            state["vpn"] = "stopped"
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
        if method == "PUT":
            state["vpn"] = "running"
        if path == "/v1/vpn/status":
            return {"status": state["vpn"]}
        return {"public_ip": "1.1.1.1" if len(calls) < 3 else "2.2.2.2"}
    monkeypatch.setattr(worker, "_gluetun", gluetun)

    assert worker._new_address()
    assert state["vpn"] == "running"


def test_a_video_that_keeps_stopping_the_worker_gives_up_after_three(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    db = dbm.connect()
    db.execute("insert into source(url, lang) values ('https://www.youtube.com/@chan', 'en')")
    db.execute("insert into video(id, source_id, state) values ('long', 1, 'transcribing')")
    row = lambda: db.execute("select state, attempts, error from video").fetchone()[:]

    worker.restarted(db)
    assert row() == ("new", 1, None)
    db.execute("update video set state='transcribing'")
    worker.restarted(db)
    db.execute("update video set state='transcribing'")
    worker.restarted(db)
    assert row() == ("error", 3, "Stopped partway through, 3 times")
