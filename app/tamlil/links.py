"""Any link to a YouTube video, playlist or channel, as YouTube's own link.

Besides youtube.com and youtu.be, this takes links from Invidious (which keeps YouTube's paths:
/watch?v=, /playlist?list=, /channel/UC…, /@handle) and from Materialious (/watch/ID,
/playlist/ID, /channel/UC…), on any instance. Only the ID is read out of the link; the other
site is never contacted, and everything after that goes to YouTube itself.
"""

import re
from urllib.parse import parse_qs, urlsplit

VIDEO = re.compile(r"^[A-Za-z0-9_-]{11}$")
LIST = re.compile(r"^[A-Za-z0-9_-]{10,64}$")
CHANNEL = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
NAME = re.compile(r"^[A-Za-z0-9._%-]{1,100}$")


def watch(vid: str) -> str:
    return f"https://www.youtube.com/watch?v={vid}"


def to_youtube(link: str) -> str | None:
    """The youtube.com link for a video, playlist or channel link from YouTube, Invidious or
    Materialious, or None when it isn't one of those."""
    s = (link or "").strip()
    if not s or " " in s:
        return None
    if not re.match(r"^https?://", s, re.I):
        s = "https://" + s
    try:
        u = urlsplit(s)
        host = (u.hostname or "").lower()
    except ValueError:
        return None
    if not host or "." not in host:
        return None
    q = {k: v[0] for k, v in parse_qs(u.query).items() if v}
    parts = [p for p in u.path.split("/") if p]
    head = parts[0].lower() if parts else ""

    # a video, wherever its ID is
    if VIDEO.match(q.get("v", "")):
        return watch(q["v"])
    if head in ("watch", "embed", "shorts", "live", "v", "e") and len(parts) > 1 and VIDEO.match(parts[1]):
        return watch(parts[1])                                   # Materialious /watch/ID, and the rest
    if host.endswith("youtu.be") and parts and VIDEO.match(parts[0]):
        return watch(parts[0])

    # a playlist
    if head == "playlist":
        lid = parts[1] if len(parts) > 1 else q.get("list", "")  # Materialious /playlist/ID or ?list=
        return f"https://www.youtube.com/playlist?list={lid}" if LIST.match(lid) else None

    # a channel (its tabs, like /videos, fall back to the channel)
    if head == "channel" and len(parts) > 1 and CHANNEL.match(parts[1]):
        return f"https://www.youtube.com/channel/{parts[1]}"
    if parts and parts[0].startswith("@") and NAME.match(parts[0][1:]):
        return f"https://www.youtube.com/{parts[0]}"
    if head in ("c", "user") and len(parts) > 1 and NAME.match(parts[1]):
        return f"https://www.youtube.com/{head}/{parts[1]}"

    # Invidious also answers /VIDEO_ID on its own
    if len(parts) == 1 and VIDEO.match(parts[0]) and not host.endswith("youtube.com"):
        return watch(parts[0])
    return None
