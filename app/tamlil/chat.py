"""Chat about the transcripts, with Claude.

The owner picks how Tamlil reaches Claude, in Settings:

- an API key: the Anthropic SDK calls Claude, and the key's account pays for it;
- a Claude Code token (from `claude setup-token`): the Claude Agent SDK runs Claude Code on the owner's
  own plan, with every one of its built-in tools turned off.

Either way Claude gets the same three tools, which only read the library: search (the same Hebrew-aware
search as the search box), transcript (a video's lines with their times) and videos (what's in it).
Each chat is kept, with what its person asked and what Claude answered, and only its person sees it.
"""

import asyncio
import json
import logging
import os
import re
import tempfile
import threading
import time
from pathlib import Path

import anyio

from . import config
from .db import connect
from .search import search as word_search, video_hits

log = logging.getLogger("tamlil.chat")

MODELS = {"claude-sonnet-5-5": "Sonnet 5.5", "claude-opus-5-5": "Opus 5.5", "claude-haiku-5-5": "Haiku 5.5"}
DEFAULT_MODEL = "claude-sonnet-5-5"
ENGINES = ("off", "api", "claude")
# Dollars per million tokens: input, output, cache write (5 minutes), cache read.
PRICES = {"claude-sonnet-5-5": (2.0, 10.0, 2.5, 0.2), "claude-opus-5-5": (4.0, 20.0, 5.0, 0.2),
          "claude-haiku-5-5": (0.1, 0.5, 0.125, 0.01)}
ROUNDS = 12          # rounds of tool calls in one answer, at most; the last one has to answer
PER_DAY = 60         # questions a day for anyone but the owner
QUESTION = 4000      # characters in one question
PART = 40_000        # characters of transcript the transcript tool hands back at a time
INLINE = 400_000     # a chat about one video carries its whole transcript, up to this many characters
LANG = {"he": "Hebrew", "en": "English"}
ORIGIN = {"uploader": "the uploader's captions", "youtube_auto": "YouTube's automatic captions",
          "whisper": "Whisper (automatic transcription)"}

SYSTEM = """You are the chat in Tamlil, a private search over the transcripts of a few YouTube channels, in Hebrew and English. People ask you about what is said in these videos: where something was said, what a video or a series says about a subject, how two videos differ, or to explain an idea from them.

Work from the transcripts, not from memory. Use the tools to look things up before you answer, even when you think you know: search finds moments by their words, transcript reads a video's lines with their times, and videos lists what is in the library. Search with the words the speakers would actually say, in the language of the videos (Hebrew words for Hebrew channels, even when the question is in English); the search already handles Hebrew prefixes, spelling variants and niqqud. If a search finds little, try other words, a synonym or a shorter phrase before you conclude it isn't there. Read the transcript around a moment before you rely on it.

The transcripts come from captions or from automatic transcription, so they have mistakes, most of all in names and rare words. When a line looks garbled, say what it most likely says, and that the transcript is unclear there.

Cite what you say with the moment it comes from, as a markdown link whose text is the time and whose target is # then the video id, @ and the same time, for example [12:48](#dQw4w9WgXcQ@12:48). Use the time at the start of the line. When you mention a video, use its title. If the library doesn't have the answer, say so plainly.

Answer in the language the question is written in (an English question gets an English answer, a Hebrew one a Hebrew answer), whatever language the videos are in. Keep it as short as the question allows, in short paragraphs, with a list only when it helps. Don't describe your searching; just answer."""

TOOLS = [
    {
        "name": "search",
        "description": (
            "Search every transcript in the library for words or a phrase. Returns the videos that say it, "
            "best match first: each video's id, title, channel, date and length, its best lines with their "
            "start times, and the times of all its other matches. Hebrew words match with their prefixes "
            "(ה ו ב ל מ ש כ), with or without niqqud, and in either spelling (with or without extra ו and י). "
            "Several words find the places where they all come close together. With video_id it returns "
            "every matching line in that one video instead."),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The words to find, as the speakers would say them."},
                "video_id": {"type": "string", "description": "Only this video: every line that matches."},
                "source_id": {"type": "integer", "description": "Only this channel (its source_id)."},
                "title": {"type": "string", "description": "Only videos with these words in the title."},
                "date_from": {"type": "string", "description": "Only videos uploaded on or after this day, YYYY-MM-DD."},
                "date_to": {"type": "string", "description": "Only videos uploaded on or before this day, YYYY-MM-DD."},
                "sort": {"type": "string", "enum": ["best", "newest", "oldest", "moments"]},
                "limit": {"type": "integer", "description": "How many videos, 1 to 20 (8 if left out)."},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "transcript",
        "description": (
            "Read one video's transcript: its title, channel, date, length, language and where the text came "
            "from, then its lines, each with its start time. A long video comes back in parts, and the end of "
            "each part says the from_seconds to ask for next. from_seconds and to_seconds read just one stretch."),
        "input_schema": {
            "type": "object",
            "properties": {
                "video_id": {"type": "string"},
                "from_seconds": {"type": "integer", "description": "Start here (0 if left out)."},
                "to_seconds": {"type": "integer", "description": "Stop here (the end if left out)."},
            },
            "required": ["video_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "videos",
        "description": (
            "List the videos in the library that have transcripts, newest first: id, date, length, title and "
            "channel, and how many there are in all. Narrow it by channel, words in the title, or dates."),
        "input_schema": {
            "type": "object",
            "properties": {
                "source_id": {"type": "integer"},
                "title": {"type": "string"},
                "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD"},
                "oldest_first": {"type": "boolean"},
                "limit": {"type": "integer", "description": "1 to 100 (30 if left out)."},
            },
            "additionalProperties": False,
        },
    },
]


class Refused(Exception):
    """A request we won't do, with a short code the page turns into words."""


# ---------- settings (data/chat.json, readable by its owner only) ----------

def _path() -> Path:
    return config.DATA / "chat.json"


def _read() -> dict:
    try:
        d = json.loads(_path().read_text())
    except (OSError, ValueError):
        d = {}
    d.setdefault("engine", "off")
    d.setdefault("api_key", "")
    d.setdefault("token", "")
    d.setdefault("model", DEFAULT_MODEL)
    d.setdefault("everyone", False)
    if d["model"] not in MODELS:
        d["model"] = DEFAULT_MODEL
    return d


def _write(d: dict) -> None:
    _path().parent.mkdir(parents=True, exist_ok=True)
    tmp = _path().with_suffix(".tmp")
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump(d, f, indent=1)
    tmp.replace(_path())


def _tail(secret: str) -> str | None:
    return "…" + secret[-4:] if secret else None


def _usable(d: dict) -> str | None:
    """The engine that will answer, or None when chat is off or its key is missing."""
    if d["engine"] == "api" and d["api_key"]:
        return "api"
    if d["engine"] == "claude" and d["token"]:
        return "claude"
    return None


def settings() -> dict:
    d = _read()
    since = time.mktime(time.localtime()[:2] + (1, 0, 0, 0, 0, 0, -1))      # the 1st of this month
    row = _db().execute("select count(*) n, sum(cost) cost from chat_msg where role='assistant' and at>=?",
                        (int(since),)).fetchone()
    return {"engine": d["engine"], "model": d["model"], "everyone": d["everyone"], "ready": bool(_usable(d)),
            "api_key": _tail(d["api_key"]), "token": _tail(d["token"]), "models": MODELS,
            "month": {"answers": row["n"] or 0, "cost": round(row["cost"] or 0, 4)}}


_SECRET = re.compile(r"^[A-Za-z0-9_\-]{20,400}$")


def set_settings(*, engine=None, api_key=None, token=None, model=None, everyone=None) -> dict:
    d = _read()
    if engine is not None:
        if engine not in ENGINES:
            raise Refused("engine")
        d["engine"] = engine
    for name, value in (("api_key", api_key), ("token", token)):
        if value is not None:
            value = value.strip()
            if value and not _SECRET.match(value):
                raise Refused(name)
            d[name] = value
    if model is not None:
        if model not in MODELS:
            raise Refused("model")
        d["model"] = model
    if everyone is not None:
        d["everyone"] = bool(everyone)
    _write(d)
    return settings()


def allowed(person: dict | None, tailnet: bool) -> bool:
    d = _read()
    if not _usable(d):
        return False
    return bool(tailnet or (person and person["owner"]) or (person and d["everyone"]))


# ---------- chats ----------

_local = threading.local()


def _db():
    if not hasattr(_local, "db"):
        _local.db = connect()
    return _local.db


def _short(ms: int) -> str:
    s = max(0, int(ms)) // 1000
    h, m, s = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _day(d: str | None) -> str:
    return f"{d[:4]}-{d[4:6]}-{d[6:]}" if d and len(d) == 8 else "?"


def _ymd(s) -> str | None:
    s = str(s or "").replace("-", "")
    return s if len(s) == 8 and s.isdigit() else None


def _context(db, video_id: str | None, source_id: int | None) -> str:
    """What Claude is told about the library when a chat starts. It's kept with the chat, so every later
    question in it sends the very same words (and the cache keeps working)."""
    out = [f"Today is {time.strftime('%Y-%m-%d')}.", "",
           "The library's channels (source_id · name · language · videos with transcripts · first and last upload):"]
    for s in db.execute(
            "select source.id, source.title, source.url, source.lang, count(video.id) n,"
            " min(video.upload_date) a, max(video.upload_date) b from source"
            " left join video on video.source_id=source.id and video.state='ready'"
            " group by source.id order by source.id"):
        out.append(f"- {s['id']} · {s['title'] or s['url']} · {LANG.get(s['lang'], 'detected per video')}"
                   f" · {s['n']} · {_day(s['a'])} to {_day(s['b'])}")
    if source_id:
        s = db.execute("select id, title, url from source where id=?", (source_id,)).fetchone()
        out += ["", f"This chat is about one channel: {s['title'] or s['url']} (source_id {s['id']}). "
                    f"Search it with source_id {s['id']}, unless the question is about the others."]
    if video_id:
        v = db.execute("select * from video where id=?", (video_id,)).fetchone()
        segs = db.execute("select start_ms, text from segment where video_id=? order by idx", (video_id,)).fetchall()
        lines = "\n".join(f"[{_short(s['start_ms'])}] {s['text']}" for s in segs)
        out += ["", "This chat is about one video:", _header(v)]
        if len(lines) <= INLINE:
            out += ["", "Its whole transcript, each line with its start time:", lines]
        else:
            out += ["", "Its transcript is too long to put here; read it with the transcript tool, part by part."]
    return "\n".join(out)


def _header(v) -> str:
    return "\n".join([
        f"Video id: {v['id']}", f"Title: {v['title']}", f"Channel: {v['channel']}", f"Uploaded: {_day(v['upload_date'])}",
        f"Length: {_short((v['duration'] or 0) * 1000)}", f"Language: {LANG.get(v['lang'], v['lang'] or '?')}",
        f"Text from: {ORIGIN.get(v['origin'], v['origin'] or '?')}"])


def chats(who: str) -> list[dict]:
    rows = _db().execute(
        "select chat.id, chat.title, chat.video_id, chat.source_id, chat.updated_at, video.title video_title,"
        " source.title source_title from chat left join video on video.id=chat.video_id"
        " left join source on source.id=chat.source_id where chat.who=? and chat.title is not null"
        " order by chat.updated_at desc limit 300", (who,)).fetchall()
    return [dict(r) for r in rows]


def new_chat(who: str, video_id: str | None = None, source_id: int | None = None) -> dict:
    db = _db()
    if video_id and not db.execute("select 1 from video where id=? and state='ready'", (video_id,)).fetchone():
        raise Refused("video")
    if source_id and not db.execute("select 1 from source where id=?", (source_id,)).fetchone():
        raise Refused("source")
    db.execute("delete from chat where who=? and title is null and made_at<?", (who, int(time.time()) - 86400))
    now = int(time.time())
    cur = db.execute("insert into chat(who, video_id, source_id, context, made_at, updated_at) values (?,?,?,?,?,?)",
                     (who, video_id or None, source_id or None, _context(db, video_id, source_id), now, now))
    return get_chat(who, cur.lastrowid)


def _chat_row(who: str, chat_id: int):
    row = _db().execute("select * from chat where id=? and who=?", (chat_id, who)).fetchone()
    if not row:
        raise Refused("missing")
    return row


def get_chat(who: str, chat_id: int) -> dict:
    db = _db()
    c = _chat_row(who, chat_id)
    msgs = db.execute("select id, role, text, refs, at from chat_msg where chat_id=? order by id", (chat_id,)).fetchall()
    video = db.execute("select id, title, channel, upload_date, duration from video where id=?",
                       (c["video_id"],)).fetchone() if c["video_id"] else None
    source = db.execute("select id, title from source where id=?", (c["source_id"],)).fetchone() if c["source_id"] else None
    return {"id": c["id"], "title": c["title"], "video": dict(video) if video else None,
            "source": dict(source) if source else None,
            "messages": [{**dict(m), "refs": json.loads(m["refs"] or "{}")} for m in msgs]}


def delete_chat(who: str, chat_id: int) -> None:
    _db().execute("delete from chat where id=? and who=?", (chat_id, who))


def forget(who: str) -> None:
    """Someone was taken off the list: their chats go too."""
    _db().execute("delete from chat where who=?", (who,))


# ---------- the tools Claude gets (they only read) ----------

def _int(a: dict, key: str, default, lo: int, hi: int):
    v = a.get(key, default)
    if v is None:
        return default
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        v = int(v.strip())
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"{key} must be a whole number")
    return max(lo, min(hi, int(v)))


def _str(a: dict, key: str, most: int = 200, need: bool = False) -> str:
    v = a.get(key)
    if v is None or v == "":
        if need:
            raise ValueError(f"{key} is required")
        return ""
    if not isinstance(v, str):
        raise ValueError(f"{key} must be text")
    return v.strip()[:most]


def _video(db, video_id: str):
    v = db.execute("select * from video where id=?", (video_id,)).fetchone()
    if not v:
        raise ValueError(f"no video with id {video_id}")
    if v["state"] != "ready":
        raise ValueError(f"video {video_id} has no transcript yet")
    return v


def _search(db, a: dict) -> str:
    q = _str(a, "query", need=True)
    vid = _str(a, "video_id", 20)
    if vid:
        v = _video(db, vid)
        hits = video_hits(db, vid, q)
        if not hits:
            return f'"{q}" isn\'t in {v["title"]}.'
        idx = [h["idx"] for h in hits][:80]
        segs = db.execute(f"select start_ms, text from segment where video_id=? and idx in ({','.join('?' * len(idx))})"
                          " order by idx", (vid, *idx)).fetchall()
        more = f" (the first {len(idx)} shown)" if len(hits) > len(idx) else ""
        return "\n".join([f"{len(hits)} lines in {v['title']} ({vid}){more}:"]
                         + [f"[{_short(s['start_ms'])}] {s['text']}" for s in segs])
    sort = a.get("sort") if a.get("sort") in ("best", "newest", "oldest", "moments") else "best"
    res = word_search(db, q, None, _int(a, "source_id", None, 1, 10**9), _int(a, "limit", 8, 1, 20),
                      title=_str(a, "title"), date_from=_ymd(a.get("date_from")), date_to=_ymd(a.get("date_to")), sort=sort)
    if not res["results"]:
        return f'Nothing in the library says "{q}" (with these filters).'
    out = [f'{len(res["results"])} videos, {res["moments"]} moments:']
    for r in res["results"]:
        v = r["video"]
        out += ["", f"{v['id']} · {v['title']} · {v['channel']} · {_day(v['upload_date'])} · "
                    f"{_short((v['duration'] or 0) * 1000)} · {r['moments']} moments"]
        out += [f"  [{_short(m['start_ms'])}] {m['text']}" for m in r["top"]]
        rest = [ms for ms in r["marks"] if ms not in {m["start_ms"] for m in r["top"]}]
        if rest:
            out.append("  also at " + ", ".join(_short(ms) for ms in rest[:40]) + (" …" if len(rest) > 40 else ""))
    return "\n".join(out)


def _transcript(db, a: dict) -> str:
    v = _video(db, _str(a, "video_id", 20, need=True))
    start = _int(a, "from_seconds", 0, 0, 10**7) * 1000
    end = _int(a, "to_seconds", None, 0, 10**7)
    segs = db.execute("select start_ms, text from segment where video_id=? and start_ms>=? and (? is null or start_ms<=?)"
                      " order by idx", (v["id"], start, end and end * 1000, end and end * 1000)).fetchall()
    out, size, cut = [_header(v), ""], 0, None
    for s in segs:
        line = f"[{_short(s['start_ms'])}] {s['text']}"
        if size + len(line) > PART and size:
            cut = s["start_ms"] // 1000
            break
        out.append(line)
        size += len(line) + 1
    if not segs:
        out.append("(no lines in that stretch)")
    if cut is not None:
        out += ["", f"(continues: ask again with from_seconds={cut})"]
    return "\n".join(out)


def _videos(db, a: dict) -> str:
    where, args = "state='ready'", []
    src = _int(a, "source_id", None, 1, 10**9)
    if src:
        where += " and source_id=?"
        args.append(src)
    for w in _str(a, "title").lower().split()[:6]:
        where += " and lower(title) like ? escape '\\'"
        args.append("%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    for key, op in (("date_from", ">="), ("date_to", "<=")):
        if _ymd(a.get(key)):
            where += f" and upload_date {op} ?"
            args.append(_ymd(a.get(key)))
    total = db.execute(f"select count(*) from video where {where}", args).fetchone()[0]
    order = "asc" if a.get("oldest_first") is True else "desc"
    rows = db.execute(f"select id, title, channel, upload_date, duration from video where {where}"
                      f" order by upload_date {order} limit ?", (*args, _int(a, "limit", 30, 1, 100))).fetchall()
    if not rows:
        return "No videos with transcripts match."
    return "\n".join([f"{total} videos match; {len(rows)} shown:"] + [
        f"{r['id']} · {_day(r['upload_date'])} · {_short((r['duration'] or 0) * 1000)} · {r['title']} · {r['channel']}"
        for r in rows])


RUN = {"search": _search, "transcript": _transcript, "videos": _videos}


def run_tool(name: str, args) -> tuple[str, bool]:
    """A tool's answer as text, and whether it's an error. Runs in a worker thread."""
    if name not in RUN:
        return f"There's no tool called {name}.", True
    if not isinstance(args, dict):
        return "The tool's input wasn't an object.", True
    try:
        return RUN[name](_db(), args), False
    except ValueError as e:
        return str(e), True
    except Exception:                       # a bug here shouldn't end the answer
        log.exception("tool %s failed", name)
        return "That didn't work.", True


def label(name: str, args) -> str:
    """What the page shows while a tool runs."""
    a = args if isinstance(args, dict) else {}
    if name == "search":
        return f"search\t{str(a.get('query') or '')[:80]}"
    if name == "transcript":
        row = _db().execute("select title from video where id=?", (str(a.get("video_id") or ""),)).fetchone()
        return f"read\t{row['title'] if row else ''}"
    return "list\t"


# ---------- the two ways to reach Claude ----------

def _cost(model: str, usage) -> float:
    p = PRICES.get(model, PRICES[DEFAULT_MODEL])
    get = (lambda k: (getattr(usage, k, None) or 0))
    return (get("input_tokens") * p[0] + get("output_tokens") * p[1]
            + get("cache_creation_input_tokens") * p[2] + get("cache_read_input_tokens") * p[3]) / 1e6


async def _via_api(cfg: dict, context: str, history: list[tuple[str, str]], question: str):
    """The Anthropic SDK, with a hand-written tool loop so every word streams to the page."""
    import anthropic

    model = cfg["model"]
    client = anthropic.AsyncAnthropic(api_key=cfg["api_key"], max_retries=2)
    messages = []
    for i, (role, text) in enumerate(history + [("user", question)]):
        if i == 0:      # the library (and the video) goes first, and never changes, so it stays cached
            messages.append({"role": "user", "content": [{"type": "text", "text": context}, {"type": "text", "text": text}]})
        else:
            messages.append({"role": role, "content": text})
    tools = [{**t, "eager_input_streaming": True} for t in TOOLS]
    extra = {} if model == "claude-haiku-5-5" else {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    cost, rnd, bad = 0.0, 0, 0
    try:
        while True:
            text = ""
            try:
                async with client.beta.messages.stream(
                        model=model, max_tokens=16000,
                        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
                        tools=tools, messages=messages, cache_control={"type": "ephemeral"},
                        output_config={"effort": "medium"},
                        **({"tool_choice": {"type": "none"}} if rnd >= ROUNDS else {}), **extra) as stream:
                    async for ev in stream:
                        if ev.type == "text":
                            text += ev.text
                            yield ("text", ev.text)
                    msg = await stream.get_final_message()
                bad = 0
            except ValueError:
                # A tool input the SDK couldn't parse at all: there's no tool_use id to answer, so ask again.
                bad += 1
                if bad > 2:
                    raise
                yield ("reset", None)
                continue
            cost += _cost(model, msg.usage)
            if msg.stop_reason == "refusal":
                yield ("error", "refused")
                return
            uses = [b for b in msg.content if b.type == "tool_use"]
            if not uses:
                yield ("done", {"text": text, "cost": cost})
                return
            if msg.stop_reason == "max_tokens":
                yield ("error", "long")
                return
            results = []
            for b in uses:
                yield ("tool", await asyncio.to_thread(label, b.name, b.input))
                out, err = await asyncio.to_thread(run_tool, b.name, b.input)
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": out, **({"is_error": True} if err else {})})
            messages.append({"role": "assistant", "content": msg.content})
            messages.append({"role": "user", "content": results})
            rnd += 1
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
        yield ("error", "key")
    except anthropic.NotFoundError:
        yield ("error", "model")
    except anthropic.RateLimitError:
        yield ("error", "limit")
    except anthropic.BadRequestError as e:
        log.warning("chat: %s", e.message)
        yield ("error", "credit" if "credit" in (e.message or "").lower() else "request")
    except anthropic.APIStatusError as e:
        log.warning("chat: %s %s", e.status_code, e.message)
        yield ("error", "down")
    except anthropic.APIConnectionError:
        yield ("error", "network")


_gate = None


def _claude_dirs() -> tuple[Path, Path]:
    home = Path(tempfile.gettempdir()) / "tamlil-claude"
    work = home / "empty"                   # Claude Code starts here; there's nothing in it, and no tool to look
    work.mkdir(parents=True, exist_ok=True)
    return home, work


async def _via_claude(cfg: dict, context: str, history: list[tuple[str, str]], question: str):
    """Claude Code on the owner's plan, through the Claude Agent SDK. Its own tools are all off; it only
    has ours, served in this process."""
    global _gate
    from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKError, ResultMessage,
                                  StreamEvent, ToolUseBlock, create_sdk_mcp_server, query, tool)

    def make(t):
        @tool(t["name"], t["description"], t["input_schema"])
        async def run(args):
            out, err = await asyncio.to_thread(run_tool, t["name"], args)
            return {"content": [{"type": "text", "text": out}], **({"is_error": True} if err else {})}
        return run

    server = create_sdk_mcp_server(name="tamlil", version="1.0.0", tools=[make(t) for t in TOOLS])
    home, work = _claude_dirs()
    stderr = []
    # The library (and a whole transcript) is too long for a command-line argument, so it goes in a file.
    fd, sysfile = tempfile.mkstemp(prefix="system-", suffix=".md", dir=home)
    with os.fdopen(fd, "w") as f:
        f.write(SYSTEM + "\n\n" + context)
    options = ClaudeAgentOptions(
        tools=[], mcp_servers={"tamlil": server}, strict_mcp_config=True,
        allowed_tools=[f"mcp__tamlil__{t['name']}" for t in TOOLS], permission_mode="dontAsk",
        setting_sources=[], system_prompt={"type": "file", "path": sysfile}, model=cfg["model"], effort="medium",
        max_turns=ROUNDS + 2, include_partial_messages=True, cwd=str(work),
        verbatim_prompts=True,                  # an @path or a /command in a question stays plain text
        env={"CLAUDE_CODE_OAUTH_TOKEN": cfg["token"], "CLAUDE_CONFIG_DIR": str(home / "config"), "HOME": str(home),
             "DISABLE_AUTOUPDATER": "1", "DISABLE_TELEMETRY": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"},
        stderr=lambda line: stderr.append(line[:300]),
    )
    if history:
        prompt = "\n\n".join(["Earlier in this chat:"] + [f"<{role}>\n{text}\n</{role}>" for role, text in history]
                             + ["The question now:\n" + question])
    else:
        prompt = question
    if _gate is None:
        _gate = asyncio.Semaphore(2)            # each answer is a Claude Code process; two at a time
    text, cost = "", None
    async with _gate:
        stream = query(prompt=prompt, options=options)
        try:
            async for m in stream:
                if isinstance(m, StreamEvent):
                    e = m.event
                    if m.parent_tool_use_id is None and e.get("type") == "content_block_delta" \
                            and e.get("delta", {}).get("type") == "text_delta":
                        text += e["delta"]["text"]
                        yield ("text", e["delta"]["text"])
                elif isinstance(m, AssistantMessage):
                    if m.error:
                        yield ("error", {"authentication_failed": "token", "rate_limit": "limit",
                                         "billing_error": "plan"}.get(m.error, "down"))
                        return
                    for b in m.content:
                        if isinstance(b, ToolUseBlock):
                            text = ""
                            yield ("tool", await asyncio.to_thread(label, b.name.removeprefix("mcp__tamlil__"), b.input))
                elif isinstance(m, ResultMessage):
                    cost = m.total_cost_usd
                    if m.is_error and not text:
                        log.warning("chat: claude code %s %s %s", m.subtype, m.api_error_status, (m.errors or [])[:3])
                        yield ("error", "token" if m.api_error_status == 401 else "long" if m.subtype == "error_max_turns" else "down")
                        return
                    if not text and m.result:
                        text = m.result
        except ClaudeSDKError as e:
            log.warning("chat: claude code failed: %s | %s", e, " / ".join(stderr[-5:]))
            yield ("error", "claude")
            return
        finally:
            with anyio.CancelScope(shield=True):        # stop Claude Code even when the page went away
                await stream.aclose()
            Path(sysfile).unlink(missing_ok=True)
    yield ("done", {"text": text, "cost": None, "notional": cost})


# ---------- one question ----------

_running: dict[str, dict] = {}      # whose answer is being written, and a flag that stops it
_CITE = re.compile(r"\]\(#([A-Za-z0-9_-]{1,20})@[\d:]+\)")


def _refs(text: str) -> dict:
    ids = list(dict.fromkeys(_CITE.findall(text or "")))[:60]
    if not ids:
        return {}
    rows = _db().execute(f"select id, title, channel, upload_date from video where id in ({','.join('?' * len(ids))})",
                         ids).fetchall()
    return {r["id"]: {"title": r["title"], "channel": r["channel"], "upload_date": r["upload_date"]} for r in rows}


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def start(who: str, chat_id: int, question: str, owner: bool) -> tuple:
    """Checks a question before the answer starts streaming, so a refusal is a plain HTTP error."""
    question = (question or "").strip()
    if not question:
        raise Refused("empty")
    if len(question) > QUESTION:
        raise Refused("too-long")
    c = _chat_row(who, chat_id)
    cfg = _read()
    engine = _usable(cfg)
    if not engine:
        raise Refused("off")
    stop(who)                          # a new question ends one that was stopped or left behind
    if not owner:
        day = _db().execute("select count(*) from chat_msg join chat on chat.id=chat_msg.chat_id"
                            " where chat.who=? and chat_msg.role='user' and chat_msg.at>?",
                            (who, int(time.time()) - 86400)).fetchone()[0]
        if day >= PER_DAY:
            raise Refused("day")
    return c, cfg, engine, question


def stop(who: str) -> None:
    if who in _running:
        _running[who]["stop"] = True


async def answer(who: str, chat, cfg: dict, engine: str, question: str, gone=None):
    """The answer as server-sent events: tool (what it's looking at), text (the answer as it's written),
    reset (throw away the draft), error, and done (the saved answer, with the videos it cites).
    It stops early when stop() is called, or when gone() says the page has gone away."""
    db = _db()
    history = [(m["role"], m["text"]) for m in db.execute(
        "select role, text from chat_msg where chat_id=? and text!='' order by id", (chat["id"],))]
    now = int(time.time())
    db.execute("insert into chat_msg(chat_id, role, text, at) values (?,?,?,?)", (chat["id"], "user", question, now))
    title = chat["title"] or re.sub(r"\s+", " ", question)[:90]
    db.execute("update chat set title=?, updated_at=? where id=?", (title, now, chat["id"]))
    flag = _running[who] = {"stop": False}
    gen = (_via_api if engine == "api" else _via_claude)(cfg, chat["context"], history, question)
    draft, final, cost, failed = "", None, None, None
    try:
        yield _sse("start", {"title": title})
        try:
            async for kind, data in gen:
                if kind == "text":
                    draft += data
                    yield _sse("text", {"t": data})
                elif kind == "tool":
                    draft = ""
                    what, _, arg = data.partition("\t")
                    yield _sse("tool", {"what": what, "arg": arg})
                elif kind == "reset":
                    draft = ""
                    yield _sse("reset", {})
                elif kind == "error":
                    failed = data
                elif kind == "done":
                    final, cost = data["text"], data.get("cost")
                if flag["stop"] or (gone and await gone()):
                    break
        except Exception:
            log.exception("chat: the answer failed")
            failed = "down"
        if failed:
            yield _sse("error", {"code": failed})
    finally:
        if _running.get(who) is flag:
            del _running[who]
        with anyio.CancelScope(shield=True):
            await gen.aclose()
        text = (final if final is not None else draft).strip()
        refs = _refs(text)
        msg_id = None
        if text:
            cur = db.execute("insert into chat_msg(chat_id, role, text, refs, engine, model, cost, at) values (?,?,?,?,?,?,?,?)",
                             (chat["id"], "assistant", text, json.dumps(refs, ensure_ascii=False), engine, cfg["model"],
                              cost, int(time.time())))
            msg_id = cur.lastrowid
            db.execute("update chat set updated_at=? where id=?", (int(time.time()), chat["id"]))
    yield _sse("done", {"id": msg_id, "text": text, "refs": refs})
