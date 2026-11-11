import json

from tamlil import config, db as dbm, fetch, transcribe, worker

DUBS = ["ar-orig", "de-orig", "en-orig", "iw-orig", "ru-orig"]


def test_a_dubbed_video_speaks_its_original_language():
    info = {"language": "ar", "formats": [
        {"language": "ar", "format_note": "Arabic, low"},
        {"language": "en-US", "format_note": "English (US) original (default), low"},
    ]}
    assert fetch.spoken(info) == "en-US"
    assert fetch.spoken({"language": "iw", "formats": [{"format_note": "medium"}]}) == "iw"


def test_dubbed_captions_dont_decide_the_language():
    assert fetch.pick_track(None, [], DUBS) == (None, None)
    assert fetch.pick_track(None, [], ["en-orig", "en", "fr"]) == (("youtube_auto", "en-orig"), "en")
    assert fetch.pick_track("en", [], DUBS) == (("youtube_auto", "en-orig"), "en")


def test_with_detect_whisper_listens_for_itself(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "TMP", tmp_path / "tmp")
    monkeypatch.setattr(fetch, "download_audio", lambda vid, work: work / "a.m4a")
    told = []

    def whisper(path, lang, prompt="", progress=None):
        told.append(lang)
        return [{"start_ms": 0, "end_ms": 1000, "text": "Go ahead with your question."}], lang or "en", "m"
    monkeypatch.setattr(transcribe, "transcribe", whisper)
    db = dbm.connect()
    db.execute("insert into source(url, lang) values ('https://www.youtube.com/@a', 'auto')")
    db.execute("insert into source(url, lang) values ('https://www.youtube.com/@b', 'he')")
    tracks = json.dumps({"manual": [], "auto": []})
    db.execute("insert into video(id, source_id, state, lang, tracks, upload_date) values ('d', 1, 'new', 'ar', ?, '2')",
               (tracks,))
    db.execute("insert into video(id, source_id, state, lang, tracks, upload_date) values ('h', 2, 'new', 'ar', ?, '1')",
               (tracks,))

    assert worker.process_next(db) and worker.process_next(db)
    assert told == [None, "he"]           # Detect: Whisper decides. A source set to עברית: Hebrew.
    assert db.execute("select lang from video where id='d'").fetchone()[0] == "en"
