"""Everything that talks to YouTube, through yt-dlp and the stack's proxy."""

import re
import time
from pathlib import Path

import yt_dlp

from . import config

HE = {"he", "iw"}


def _opts(**extra) -> dict:
    o = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": 30,
        "retries": 3,
        "extractor_retries": 2,
        "sleep_interval_requests": min(config.REQUEST_GAP, 2),
    }
    if config.PROXY:
        o["proxy"] = config.PROXY
    o.update(extra)
    return o


def lang_code(code: str | None) -> str | None:
    """YouTube writes Hebrew as 'iw'. Keep the base language only."""
    if not code:
        return None
    base = code.split("-")[0].lower()
    return "he" if base in HE else base


def classify(url: str) -> tuple[str, str]:
    """(kind, url to list). Channel roots go to their Videos tab."""
    u = url.strip()
    if re.search(r"[?&]list=", u) and "watch?v=" not in u:
        return "playlist", u
    if re.search(r"(youtu\.be/|watch\?v=|/shorts/|/live/)", u):
        return "video", u
    if re.search(r"youtube\.com/(@[^/]+|channel/[^/]+|c/[^/]+|user/[^/]+)/?$", u):
        return "channel", u.rstrip("/") + "/videos"
    return "channel", u


def list_entries(url: str):
    """(title, entries) where entries are flat {'id', 'title'} in the order YouTube lists them."""
    kind, target = classify(url)
    with yt_dlp.YoutubeDL(_opts(extract_flat="in_playlist", lazy_playlist=True)) as y:
        info = y.extract_info(target, download=False, process=False)
    if kind == "video":
        return kind, info.get("title"), [{"id": info["id"], "title": info.get("title")}]
    title = info.get("channel") or info.get("uploader") or info.get("title")
    entries = ({"id": e["id"], "title": e.get("title")} for e in info.get("entries") or [] if e and e.get("id"))
    return kind, title, entries


def video_info(video_id: str) -> dict:
    with yt_dlp.YoutubeDL(_opts(skip_download=True)) as y:
        info = y.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    time.sleep(config.REQUEST_GAP)
    manual = sorted((info.get("subtitles") or {}).keys())
    auto = sorted((info.get("automatic_captions") or {}).keys())
    return {
        "id": info["id"],
        "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "upload_date": info.get("upload_date"),
        "duration": info.get("duration"),
        "description": (info.get("description") or "")[:4000],
        "language": lang_code(info.get("language")),
        "live_status": info.get("live_status"),
        "availability": info.get("availability"),
        "manual": manual,
        "auto": auto,
    }


def pick_track(lang: str | None, manual: list[str], auto: list[str]):
    """Which caption track to trust, or None to transcribe.

    Uploader captions in the spoken language win. YouTube's own speech
    recognition is accepted for English only. Translated tracks never count.
    """
    if not lang:
        langs = {lang_code(c) for c in manual if lang_code(c) in ("he", "en")}
        if len(langs) == 1:
            lang = langs.pop()
        else:
            orig = [c for c in auto if c.endswith("-orig")]
            if orig:
                lang = lang_code(orig[0])
    if not lang:
        return None, None
    for c in manual:
        if lang_code(c) == lang and "live_chat" not in c:
            return ("uploader", c), lang
    if lang == "en":
        for want in ("en-orig", "en"):
            if want in auto:
                return ("youtube_auto", want), lang
    return None, lang


def download_captions(video_id: str, origin: str, code: str, workdir: Path) -> str:
    workdir.mkdir(parents=True, exist_ok=True)
    opts = _opts(
        skip_download=True,
        writesubtitles=origin == "uploader",
        writeautomaticsub=origin == "youtube_auto",
        subtitleslangs=[code],
        subtitlesformat="vtt",
        outtmpl=str(workdir / "%(id)s.%(ext)s"),
    )
    with yt_dlp.YoutubeDL(opts) as y:
        y.download([f"https://www.youtube.com/watch?v={video_id}"])
    time.sleep(config.REQUEST_GAP)
    files = sorted(workdir.glob(f"{video_id}*.vtt"))
    if not files:
        raise RuntimeError(f"no {code} caption file came back")
    text = files[0].read_text(encoding="utf-8", errors="replace")
    for f in files:
        f.unlink(missing_ok=True)
    return text


def download_audio(video_id: str, workdir: Path) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    opts = _opts(
        format="bestaudio[abr<=72]/bestaudio/best",
        outtmpl=str(workdir / "%(id)s.%(ext)s"),
        noplaylist=True,
    )
    with yt_dlp.YoutubeDL(opts) as y:
        y.download([f"https://www.youtube.com/watch?v={video_id}"])
    time.sleep(config.REQUEST_GAP)
    files = [f for f in workdir.glob(f"{video_id}.*") if not f.name.endswith((".part", ".ytdl"))]
    if not files:
        raise RuntimeError("no audio file came back")
    return files[0]
