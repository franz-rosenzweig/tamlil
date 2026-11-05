"""A transcript as a file: plain text with timestamps, subtitles (SRT or WebVTT), or JSON.
A whole channel comes as a zip with one file per video."""
import io
import json
import re
import zipfile

FORMATS = {"txt": "text/plain", "srt": "application/x-subrip", "vtt": "text/vtt", "json": "application/json"}


def _clock(ms: int, sep: str = ".") -> str:
    h, rest = divmod(max(0, int(ms)), 3_600_000)
    m, rest = divmod(rest, 60_000)
    s, ms = divmod(rest, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _short(ms: int) -> str:
    s = max(0, int(ms)) // 1000
    h, m, s = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _day(d: str | None) -> str:
    return f"{d[:4]}-{d[4:6]}-{d[6:]}" if d and len(d) == 8 else ""


def filename(video: dict, fmt: str) -> str:
    """The title, made safe for every system, with the video's ID so two of the same name don't clash."""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", video.get("title") or "").strip(" .")
    name = re.sub(r"\s+", " ", name)[:90].strip()
    return f"{name} [{video['id']}].{fmt}" if name else f"{video['id']}.{fmt}"


def render(video: dict, segments: list[dict], fmt: str) -> str:
    if fmt == "srt":
        return "\n".join(f"{i}\n{_clock(s['start_ms'], ',')} --> {_clock(s['end_ms'], ',')}\n{s['text']}\n"
                         for i, s in enumerate(segments, 1))
    if fmt == "vtt":
        return "WEBVTT\n\n" + "\n".join(f"{_clock(s['start_ms'])} --> {_clock(s['end_ms'])}\n{s['text']}\n"
                                        for s in segments)
    if fmt == "json":
        keep = ("id", "title", "channel", "upload_date", "duration", "lang", "origin", "model")
        return json.dumps({"video": {k: video.get(k) for k in keep},
                           "url": f"https://www.youtube.com/watch?v={video['id']}",
                           "segments": [{"start_ms": s["start_ms"], "end_ms": s["end_ms"], "text": s["text"]}
                                        for s in segments]}, ensure_ascii=False, indent=1)
    head = [video.get("title") or video["id"],
            " · ".join(x for x in (video.get("channel"), _day(video.get("upload_date"))) if x),
            f"https://www.youtube.com/watch?v={video['id']}", ""]
    return "\n".join(head + [f"[{_short(s['start_ms'])}] {s['text']}" for s in segments]) + "\n"


def bundle(items: list[tuple[dict, list[dict]]], fmt: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for video, segments in items:
            z.writestr(filename(video, fmt), render(video, segments, fmt))
    return buf.getvalue()
