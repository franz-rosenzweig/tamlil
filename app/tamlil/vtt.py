"""WebVTT → timed lines.

Uploader captions: one cue is one line of speech (its text lines are joined).
YouTube auto-captions roll up: each cue repeats the previous line and adds a
new one, with <c> word-timing tags. For those we keep each line once, timed
from the cue where it first appears.
"""

import html
import re

_TIME = re.compile(r"(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})")
_CUE = re.compile(r"^\s*(\S+)\s+-->\s+(\S+)")
_TAGS = re.compile(r"<[^>]+>")
_ONLY_SOUND = re.compile(r"^\s*[\[(][^\])]*[\])]\s*$")


def _ms(stamp: str) -> int:
    m = _TIME.match(stamp)
    if not m:
        raise ValueError(stamp)
    h, mi, s, ms = m.groups()
    return ((int(h or 0) * 60 + int(mi)) * 60 + int(s)) * 1000 + int(ms)


def _cues(text: str):
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    while i < len(lines):
        m = _CUE.match(lines[i])
        if not m:
            i += 1
            continue
        start, end = _ms(m.group(1)), _ms(m.group(2))
        i += 1
        body = []
        while i < len(lines) and not _CUE.match(lines[i]):
            body.append(lines[i])
            i += 1
        # Lines after the last blank one belong to the next cue (its identifier).
        if i < len(lines) and "" in body:
            body = body[: len(body) - 1 - body[::-1].index("")]
        yield start, end, body


def _clean(line: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAGS.sub("", line))).strip()


def parse(text: str) -> list[dict]:
    """Return [{'start_ms', 'end_ms', 'text'}] in order."""
    rolling = "<c>" in text or "</c>" in text
    out: list[dict] = []
    if rolling:
        last = None
        for start, end, body in _cues(text):
            for raw in body:
                line = _clean(raw)
                if not line or line == last:
                    continue
                if out and out[-1]["text"] == line:
                    continue
                out.append({"start_ms": start, "end_ms": end, "text": line})
                last = line
    else:
        for start, end, body in _cues(text):
            line = _clean(" ".join(body))
            if not line:
                continue
            if out and out[-1]["text"] == line:
                out[-1]["end_ms"] = end
                continue
            out.append({"start_ms": start, "end_ms": end, "text": line})
    out = [s for s in out if not _ONLY_SOUND.match(s["text"])]
    for a, b in zip(out, out[1:]):
        if a["end_ms"] > b["start_ms"] or a["end_ms"] - a["start_ms"] < 50:
            a["end_ms"] = max(b["start_ms"], a["start_ms"] + 50)
    return out
