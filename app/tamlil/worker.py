"""The background worker: list sources, fetch captions, transcribe the rest.

One thing at a time, at the lowest CPU priority.
"""

import json
import logging
import os
import shutil
import sys
import time
import traceback

from . import config, fetch, transcribe, vtt
from .db import connect, save_transcript, set_status

log = logging.getLogger("tamlil.worker")

KNOWN_STOP = 5      # consecutive already-known videos that end an incremental listing
OLDER_STOP = 3      # consecutive videos older than date_from that end a listing
LIST_BATCH = 10     # new videos per listing pass; their transcripts come before the next pass
MAX_ATTEMPTS = 3
BLOCK_WAIT = 45 * 60      # how long to leave YouTube alone after it turns this address away
SWITCH_GAP = 20 * 60      # at most one VPN server change in this long


class Paused(Exception):
    """Its channel was paused partway through Whisper; the video goes back in line."""


def _kv(db, key, value=None):
    if value is None:
        row = db.execute("select value from kv where key=?", (key,)).fetchone()
        return row["value"] if row else None
    db.execute("insert into kv(key, value) values (?, ?) on conflict(key) do update set value=excluded.value",
               (key, str(value)))


def _new_address() -> bool:
    """Ask gluetun to reconnect, which picks another server, and wait for the new address."""
    import httpx

    url, head = config.GLUETUN_URL, {"X-API-Key": config.GLUETUN_KEY}
    try:
        with httpx.Client(timeout=20, headers=head) as c:
            before = c.get(f"{url}/v1/publicip/ip").json().get("public_ip")
            c.put(f"{url}/v1/vpn/status", json={"status": "stopped"}).raise_for_status()
            time.sleep(3)
            c.put(f"{url}/v1/vpn/status", json={"status": "running"}).raise_for_status()
            for _ in range(30):
                time.sleep(4)
                try:
                    now = c.get(f"{url}/v1/publicip/ip").json().get("public_ip")
                except (httpx.HTTPError, ValueError):
                    continue
                if now and now != before:
                    log.info("new VPN address")
                    return True
    except (httpx.HTTPError, ValueError) as e:
        log.warning("couldn't change the VPN server: %s", e)
    return False


def _blocked(db, err) -> None:
    """YouTube is turning this address away. Nothing is marked failed: move to another VPN server
    when that's set up and wasn't just tried, and otherwise leave YouTube alone for a while."""
    log.warning("YouTube turned us away: %s", _short(err))
    now = time.time()
    if config.GLUETUN_URL and config.GLUETUN_KEY and now - float(_kv(db, "vpn_switched") or 0) > SWITCH_GAP:
        _kv(db, "vpn_switched", now)
        set_status(db, doing="switching")
        if _new_address():
            return
    _kv(db, "blocked_until", now + BLOCK_WAIT)


def held(db) -> bool:
    """True while the worker is leaving YouTube alone."""
    until = float(_kv(db, "blocked_until") or 0)
    if until <= time.time():
        return False
    set_status(db, doing="blocked", until=until)
    return True


def _short(err: BaseException) -> str:
    msg = str(err).strip().splitlines()[0] if str(err).strip() else type(err).__name__
    return msg.replace("ERROR: ", "")[:300]


def _ymd(d: str | None) -> str | None:
    return d.replace("-", "") if d else None


def refresh_due(db) -> bool:
    src = db.execute(
        """select * from source
           where not paused and (state='new' or (checked_at is null and state != 'more')
              or (state='more' and not exists (select 1 from video join source s on s.id=video.source_id
                                               where video.state='new' and not s.paused))
              or (state='ok' and coalesce(kind, '') != 'video' and checked_at < datetime('now', ?))
              or (state='error' and checked_at < datetime('now', '-1 hour')))
           order by checked_at is not null, checked_at limit 1""",
        (f"-{int(config.REFRESH_HOURS * 60)} minutes",),
    ).fetchone()
    if not src:
        return False
    set_status(db, doing="listing", source=src["id"], title=src["title"] or src["url"])
    db.execute("update source set state='listing' where id=?", (src["id"],))
    try:
        if _list_source(db, src, continuing=src["state"] == "more"):
            db.execute("update source set state='more', error=null where id=?", (src["id"],))
        else:
            db.execute("update source set state='ok', error=null, checked_at=datetime('now') where id=?", (src["id"],))
    except Exception as e:  # noqa: BLE001
        if fetch.blocked(e):          # not the source's fault: it's listed again once YouTube lets us
            db.execute("update source set state=? where id=?", (src["state"], src["id"]))
            _blocked(db, e)
            return True
        log.warning("listing %s failed: %s", src["url"], e)
        db.execute(
            "update source set state='error', error=?, checked_at=datetime('now') where id=?",
            (_short(e), src["id"]),
        )
    return True


def _list_source(db, src, continuing=False) -> bool:
    """One pass: up to LIST_BATCH new videos. True when there's more to list after them."""
    kind, title, entries = fetch.list_entries(src["url"])
    db.execute("update source set kind=?, title=coalesce(?, title) where id=?", (kind, title, src["id"]))
    date_from, date_to = _ymd(src["date_from"]), _ymd(src["date_to"])
    in_range = db.execute(
        "select count(*) from video where source_id=? and state not in ('out_of_range','skipped')", (src["id"],)
    ).fetchone()[0]
    first_listing = src["checked_at"] is None
    known_run = older_run = added = 0
    for e in entries:
        if added >= LIST_BATCH:
            return True
        if src["max_videos"] and in_range >= src["max_videos"]:
            break
        if db.execute("select 1 from video where id=?", (e["id"],)).fetchone():
            known_run += 1
            if kind == "channel" and not first_listing and not continuing and known_run >= KNOWN_STOP:
                break
            continue
        known_run = 0
        added += 1
        set_status(db, doing="listing", source=src["id"], title=title, video=e.get("title"))
        try:
            info = fetch.video_info(e["id"])
        except Exception as err:  # noqa: BLE001
            if fetch.blocked(err):
                raise
            msg = _short(err)
            state = "skipped" if any(w in msg.lower() for w in ("private", "members", "unavailable", "removed")) else "error"
            db.execute(
                "insert or ignore into video(id, source_id, title, state, error, attempts, retry_at)"
                " values (?,?,?,?,?,1,?)",
                (e["id"], src["id"], e.get("title"), state, msg, time.time() + 1800),
            )
            continue
        day = info["upload_date"]
        older = bool(date_from and day and day < date_from)
        older_run = older_run + 1 if older else 0
        state = "new"
        if info["live_status"] in ("is_live", "is_upcoming", "post_live"):
            state = "skipped"
        elif older or (date_to and day and day > date_to):
            state = "out_of_range"
        db.execute(
            """insert or ignore into video(id, source_id, title, channel, upload_date, duration,
                   description, lang, tracks, state) values (?,?,?,?,?,?,?,?,?,?)""",
            (
                info["id"], src["id"], info["title"], info["channel"], day, info["duration"],
                info["description"], info["language"],
                json.dumps({"manual": info["manual"], "auto": info["auto"]}), state,
            ),
        )
        if state == "new":
            in_range += 1
        if kind == "channel" and older_run >= OLDER_STOP:
            break
    return False


PICK = """select video.*, source.lang as source_lang, source.date_from as source_from, source.date_to as source_to
           from video join source on source.id = video.source_id"""


def process_next(db) -> bool:
    v = db.execute(
        PICK + """ where not source.paused and (video.state='new'
              or (video.state='error' and video.attempts < ? and video.retry_at < ?))
           order by video.state='error', video.upload_date desc limit 1""",
        (MAX_ATTEMPTS, time.time()),
    ).fetchone()
    if not v:
        return False
    work = config.TMP / v["id"]
    try:
        _process(db, v, work)
    except Paused:
        log.info("paused partway through %s", v["id"])
        db.execute("update video set state='new', updated_at=datetime('now') where id=?", (v["id"],))
    except Exception as e:  # noqa: BLE001
        if fetch.blocked(e):          # the video's fine: it stays as it was, with no attempt counted
            db.execute("update video set state=? where id=?", (v["state"], v["id"]))
            _blocked(db, e)
            return True
        log.warning("video %s failed: %s\n%s", v["id"], e, traceback.format_exc())
        db.execute(
            "update video set state='error', error=?, attempts=attempts+1, retry_at=?, updated_at=datetime('now')"
            " where id=?",
            (_short(e), time.time() + 1800 * (v["attempts"] + 1), v["id"]),
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return True


def _process(db, v, work):
    tracks = json.loads(v["tracks"] or "{}")
    if not tracks:
        info = fetch.video_info(v["id"])
        tracks = {"manual": info["manual"], "auto": info["auto"]}
        db.execute(
            "update video set title=?, channel=?, upload_date=?, duration=?, description=?, lang=coalesce(lang, ?),"
            " tracks=? where id=?",
            (info["title"], info["channel"], info["upload_date"], info["duration"], info["description"],
             info["language"], json.dumps(tracks), v["id"]),
        )
        # Listing couldn't read it the first time, so its date and live status weren't checked then.
        day, lo, hi = info["upload_date"], _ymd(v["source_from"]), _ymd(v["source_to"])
        skip = ("skipped" if info["live_status"] in ("is_live", "is_upcoming", "post_live")
                else "out_of_range" if day and ((lo and day < lo) or (hi and day > hi)) else None)
        if skip:
            db.execute("update video set state=?, error=null, updated_at=datetime('now') where id=?", (skip, v["id"]))
            return
        v = db.execute(PICK + " where video.id=?", (v["id"],)).fetchone()
    lang = v["source_lang"] if v["source_lang"] in ("he", "en") else v["lang"]
    title = v["title"] or v["id"]

    track, lang = fetch.pick_track(lang, tracks.get("manual", []), tracks.get("auto", []))
    if track:
        origin, code = track
        set_status(db, doing="captions", video=v["id"], title=title)
        segments = vtt.parse(fetch.download_captions(v["id"], origin, code, work))
        enough = len(segments) >= 3 or (v["duration"] or 0) < 120
        if enough:
            save_transcript(db, v["id"], segments, origin, code, lang)
            return

    db.execute("update video set state='transcribing', updated_at=datetime('now') where id=?", (v["id"],))
    set_status(db, doing="audio", video=v["id"], title=title)
    audio = fetch.download_audio(v["id"], work)
    started = time.time()
    last = [0.0]

    def progress(frac):
        if time.time() - last[0] > 15:
            last[0] = time.time()
            if db.execute("select paused from source where id=?", (v["source_id"],)).fetchone()[0]:
                raise Paused()
            set_status(db, doing="transcribing", video=v["id"], title=title, progress=round(frac, 3),
                       started=started, duration=v["duration"])

    set_status(db, doing="transcribing", video=v["id"], title=title, progress=0, started=started,
               duration=v["duration"])
    segments, lang, model = transcribe.transcribe(audio, lang, prompt=title, progress=progress)
    save_transcript(db, v["id"], segments, "whisper", model, lang)
    elapsed = time.time() - started
    if v["duration"]:
        log.info("transcribed %s: %.0fs audio in %.0fs (%.1fx)", v["id"], v["duration"], elapsed,
                 v["duration"] / max(elapsed, 1))


PYLIB = config.DATA / "pylib"


def update_ytdlp(db) -> None:
    """Once a day, install the newest yt-dlp into /data/pylib (first on PYTHONPATH).

    YouTube breaks old yt-dlp releases often, and the image is only rebuilt by hand.
    When a newer version lands, exit so Docker restarts the worker on it.
    """
    row = db.execute("select value from kv where key='ytdlp_checked'").fetchone()
    if row and time.time() - float(row["value"]) < 86400:
        return
    db.execute("insert into kv(key, value) values ('ytdlp_checked', ?) on conflict(key) do update set value=excluded.value",
               (str(time.time()),))
    import subprocess
    import yt_dlp.version

    running = yt_dlp.version.__version__
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "--no-cache-dir", "--upgrade", "--no-deps",
         "--target", str(PYLIB), "yt-dlp", "yt-dlp-ejs"],
        capture_output=True, text=True, timeout=600,
    )
    if r.returncode != 0:
        log.warning("yt-dlp update failed: %s", (r.stderr or r.stdout).strip()[-300:])
        return
    vfile = PYLIB / "yt_dlp" / "version.py"
    installed = None
    if vfile.exists():
        for line in vfile.read_text().splitlines():
            if line.startswith("__version__"):
                installed = line.split("=", 1)[1].strip().strip("'\"")
    if installed and installed != running:
        log.info("yt-dlp %s -> %s; restarting", running, installed)
        sys.exit(0)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        os.nice(19)
    except OSError:
        pass
    db = connect()
    config.TMP.mkdir(parents=True, exist_ok=True)
    db.execute("update video set state='new' where state='transcribing'")
    db.execute("update source set state='new' where state='listing'")
    log.info("worker up; proxy=%s threads=%s", bool(config.PROXY), config.WHISPER_THREADS)
    while True:
        if held(db):
            time.sleep(30)
            continue
        worked = refresh_due(db) or process_next(db)
        if not worked:
            set_status(db, doing="idle")
            update_ytdlp(db)
            time.sleep(20)


if __name__ == "__main__":
    main()
