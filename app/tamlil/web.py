import re
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import accounts, chat, chatgpt, config, export
from .links import to_youtube
from .db import connect, get_status
from .search import search, video_hits

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Tamlil", docs_url=None, redoc_url=None)
_local = threading.local()


def db():
    if not hasattr(_local, "db"):
        _local.db = connect()
    return _local.db


# ---------- sign-in (the gateway asks /api/auth/check for every outside request) ----------
# On the tailnet the gateway skips that and sets X-Tamlil-Tailnet (and strips it from everyone else).

STATUS = {"not-on-list": 403, "owner": 403, "pending": 403, "closed": 403, "throttled": 429, "locked": 429,
          "mail": 502, "wrong": 401, "expired": 401, "login": 401, "current": 401, "taken": 409, "exists": 409,
          "username": 400, "need-username": 400, "email": 400, "name": 400, "short": 400, "long": 400}


def _client(request: Request) -> str:
    return (request.headers.get("cf-connecting-ip")
            or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
            or (request.client.host if request.client else "?"))


def _refused(e: accounts.Refused) -> HTTPException:
    return HTTPException(STATUS.get(str(e), 400), str(e))


def _set_cookie(r: Response, request: Request, value: str) -> None:
    r.set_cookie(accounts.COOKIE, value, max_age=accounts.DAYS * 86400, httponly=True,
                 secure=request.headers.get("x-forwarded-proto") == "https", samesite="lax", path="/")


def _me(request: Request):
    return accounts.who(request.cookies.get(accounts.COOKIE)), request.headers.get("x-tamlil-tailnet") == "1"


def _owner_only(request: Request) -> None:
    p, tailnet = _me(request)
    if not (tailnet or (p and p["owner"])):
        raise HTTPException(403, "owner")


def _mine(request: Request) -> dict:
    """The signed-in person, for things only an account has (the tailnet alone isn't one)."""
    p, _ = _me(request)
    if not p:
        raise HTTPException(401, "sign in")
    return p


def _do(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except accounts.Refused as e:
        raise _refused(e)


@app.get("/api/auth/check")
def auth_check(request: Request):
    if accounts.who(request.cookies.get(accounts.COOKIE)):        # never the tailnet header here
        return Response(status_code=204)
    wants_page = request.headers.get("x-forwarded-method", "GET") == "GET" and "text/html" in request.headers.get("accept", "")
    if wants_page:
        return RedirectResponse("/login", status_code=302)
    return JSONResponse({"detail": "sign in"}, status_code=401)


class CodeAsk(BaseModel):
    who: str


class CodeBack(BaseModel):
    who: str
    code: str
    username: str | None = None


@app.post("/api/auth/code")
def auth_code(body: CodeAsk, request: Request):
    try:
        return accounts.send_code(body.who, _client(request))
    except accounts.Refused as e:
        raise _refused(e)


@app.post("/api/auth/verify")
def auth_verify(body: CodeBack, request: Request):
    try:
        cookie = accounts.sign_in(body.who, body.code, body.username, _client(request))
    except accounts.Refused as e:
        raise _refused(e)
    r = JSONResponse({"ok": True})
    _set_cookie(r, request, cookie)
    return r


class PasswordIn(BaseModel):
    who: str
    password: str


@app.post("/api/auth/password")
def auth_password(body: PasswordIn, request: Request):
    cookie = _do(accounts.sign_in_password, body.who, body.password, _client(request))
    r = JSONResponse({"ok": True})
    _set_cookie(r, request, cookie)
    return r


@app.get("/api/auth/open")
def auth_open():
    return {"requests": accounts.settings()["requests"] and accounts.mail.available()}


class Ask(BaseModel):
    name: str
    email: str
    username: str
    password: str | None = None
    note: str | None = None


class AskBack(BaseModel):
    email: str
    code: str


@app.post("/api/auth/join")
def auth_join(body: Ask, request: Request):
    return _do(accounts.ask, name=body.name, email=body.email, username=body.username,
               password=body.password or None, note=body.note, ip=_client(request))


@app.post("/api/auth/join/verify")
def auth_join_verify(body: AskBack, request: Request):
    return _do(accounts.confirm, body.email, body.code, _client(request))


@app.post("/api/auth/logout")
def auth_logout():
    r = JSONResponse({"ok": True})
    r.delete_cookie(accounts.COOKIE, path="/")
    return r


@app.get("/login")
@app.get("/join")
def login_page():
    return FileResponse(STATIC / "login.html")


@app.get("/api/me")
def api_me(request: Request):
    p, tailnet = _me(request)
    admin = tailnet or bool(p and p["owner"])
    r = JSONResponse({"username": p and p["username"], "email": p and p["email"], "name": p and p["name"],
                      "password": bool(p and p["password"]), "owner": bool(p and p["owner"]),
                      "tailnet": tailnet, "admin": admin, "waiting": len(accounts.requests()) if admin else 0,
                      "chat": chat.allowed(p, tailnet)})
    if p and p["renew"]:                       # slide the 180 days forward, once a day
        _set_cookie(r, request, accounts.renew(request.cookies.get(accounts.COOKIE)))
    return r


class MeIn(BaseModel):
    name: str | None = None
    username: str | None = None


class NewPassword(BaseModel):
    password: str | None = None
    current: str | None = None


@app.post("/api/me")
def api_me_save(body: MeIn, request: Request):
    return _do(accounts.update, _mine(request)["email"], name=body.name, username=body.username)


@app.post("/api/me/password")
def api_me_password(body: NewPassword, request: Request):
    cookie = _do(accounts.set_password, _mine(request)["email"], body.password or "", body.current)
    r = JSONResponse({"ok": True})
    _set_cookie(r, request, cookie)
    return r


@app.post("/api/me/password/remove")
def api_me_password_remove(body: NewPassword, request: Request):
    _do(accounts.remove_password, _mine(request)["email"], body.current)
    return {"ok": True}


@app.post("/api/me/signout-others")
def api_me_signout_others(request: Request):
    cookie = _do(accounts.sign_out_others, _mine(request)["email"])
    r = JSONResponse({"ok": True})
    _set_cookie(r, request, cookie)
    return r


class Person(BaseModel):
    email: str
    name: str | None = None


@app.get("/api/people")
def api_people(request: Request):
    _owner_only(request)
    return {"people": accounts.people(), "requests": accounts.requests(), "settings": accounts.settings(),
            "mail": accounts.mail.available(), "join": config.PUBLIC_URL + "/join"}


@app.post("/api/people")
def api_people_add(body: Person, request: Request):
    _owner_only(request)
    return _do(accounts.allow, body.email, name=body.name)


@app.post("/api/people/{email}/invite")
def api_people_invite(email: str, request: Request):
    _owner_only(request)
    return _do(accounts.invite_again, email)


@app.delete("/api/people/{email}")
def api_people_remove(email: str, request: Request):
    _owner_only(request)
    _do(accounts.remove, email)
    chat.forget(accounts.clean_email(email))
    return {"ok": True}


@app.post("/api/requests/{email}/yes")
def api_request_yes(email: str, request: Request):
    _owner_only(request)
    return _do(accounts.approve, email)


@app.post("/api/requests/{email}/no")
def api_request_no(email: str, request: Request):
    _owner_only(request)
    accounts.decline(email)
    return {"ok": True}


class SettingsIn(BaseModel):
    requests: bool | None = None
    notify: bool | None = None


@app.post("/api/settings")
def api_settings(body: SettingsIn, request: Request):
    _owner_only(request)
    return accounts.set_settings(requests=body.requests, notify=body.notify)


@app.get("/api/config")
def get_config():
    return {"player": config.PLAYER_URL}


@app.get("/api/search")
def api_search(q: str = "", lang: str = "all", source: int | None = None, title: str = "",
               date_from: str = "", date_to: str = "", sort: str = "best"):
    return search(db(), q, None if lang == "all" else lang, source,
                  title=title, date_from=date_from, date_to=date_to, sort=sort)


@app.get("/api/videos/{video_id}")
def api_video(video_id: str, q: str = ""):
    v = db().execute("select * from video where id=?", (video_id,)).fetchone()
    if not v:
        raise HTTPException(404)
    segs = db().execute(
        "select idx, start_ms, end_ms, text from segment where video_id=? order by idx", (video_id,)
    ).fetchall()
    out = dict(v)
    out.pop("tracks", None)
    out.pop("description", None)
    return {"video": out, "segments": [dict(s) for s in segs], "hits": video_hits(db(), video_id, q)}


class NewSource(BaseModel):
    url: str
    lang: str = "auto"
    date_from: str | None = None
    date_to: str | None = None
    max_videos: int | None = None


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@app.post("/api/sources")
def add_source(s: NewSource):
    url = to_youtube(s.url)          # YouTube, Invidious or Materialious, kept as YouTube's own link
    if not url:
        raise HTTPException(400, "link")
    for d in (s.date_from, s.date_to):
        if d and not _DATE.match(d):
            raise HTTPException(400, "date")
    lang = s.lang if s.lang in ("auto", "he", "en") else "auto"
    try:
        cur = db().execute(
            "insert into source(url, lang, date_from, date_to, max_videos) values (?,?,?,?,?)",
            (url, lang, s.date_from or None, s.date_to or None, s.max_videos or None),
        )
    except Exception:
        raise HTTPException(409, "exists")
    return {"id": cur.lastrowid}


@app.patch("/api/sources/{source_id}")
def edit_source(source_id: int, s: NewSource):
    db().execute(
        "update source set lang=?, date_from=?, date_to=?, max_videos=?, state='new', checked_at=null where id=?",
        (s.lang, s.date_from or None, s.date_to or None, s.max_videos or None, source_id),
    )
    return {"ok": True}


@app.delete("/api/sources/{source_id}")
def delete_source(source_id: int):
    d = db()
    d.execute("begin")
    d.execute(
        "delete from chunk_fts where rowid in (select chunk.id from chunk join video on video.id=chunk.video_id"
        " where video.source_id=?)", (source_id,))
    d.execute("delete from source where id=?", (source_id,))
    d.execute("commit")
    return {"ok": True}


@app.post("/api/sources/{source_id}/refresh")
def refresh_source(source_id: int):
    db().execute("update source set checked_at=null where id=?", (source_id,))
    return {"ok": True}


@app.get("/api/sources")
def list_sources():
    rows = db().execute(
        """select source.*,
             sum(video.state not in ('out_of_range','skipped')) as videos,
             sum(video.state='ready') as ready,
             sum(video.state='ready' and video.origin='whisper') as whisper,
             sum(video.state='ready' and video.origin!='whisper') as captions,
             sum(video.state in ('new','transcribing')) as waiting,
             sum(video.state='error') as errors,
             sum(case when video.state='ready' then video.duration else 0 end) as seconds
           from source left join video on video.source_id = source.id
           group by source.id order by source.added_at"""
    ).fetchall()
    return {"sources": [dict(r) for r in rows], "worker": get_status(db())}


@app.get("/api/sources/{source_id}/videos")
def source_videos(source_id: int):
    rows = db().execute(
        "select id, title, upload_date, duration, lang, state, origin, model, error, attempts from video"
        " where source_id=? and state!='out_of_range' order by upload_date desc", (source_id,)
    ).fetchall()
    return {"videos": [dict(r) for r in rows]}


@app.post("/api/videos/{video_id}/retry")
def retry_video(video_id: str):
    db().execute("update video set state='new', attempts=0, retry_at=0, error=null where id=?", (video_id,))
    return {"ok": True}


class PauseIn(BaseModel):
    paused: bool


@app.post("/api/sources/{source_id}/pause")
def pause_source(source_id: int, body: PauseIn):
    """A paused channel keeps everything it has, and the worker skips it (Whisper stops partway)."""
    db().execute("update source set paused=? where id=?", (int(body.paused), source_id))
    return {"ok": True}


# ---------- export ----------

def _download(data, name: str, kind: str) -> Response:
    ascii_name = re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9._ \[\]()-]+", "", name)).strip(" .")
    if not re.search(r"[A-Za-z]{2}", ascii_name.rsplit(".", 1)[0]):     # a Hebrew title: the plain name only
        ascii_name = "tamlil." + name.rsplit(".", 1)[-1]
    return Response(data, media_type=kind + ("; charset=utf-8" if kind.startswith(("text", "application/j", "application/x")) else ""),
                    headers={"content-disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"})


def _transcript(video_id: str):
    v = db().execute("select * from video where id=? and state='ready'", (video_id,)).fetchone()
    if not v:
        raise HTTPException(404)
    segs = db().execute("select start_ms, end_ms, text from segment where video_id=? order by idx", (video_id,)).fetchall()
    return dict(v), [dict(s) for s in segs]


def _fmt(fmt: str) -> str:
    if fmt not in export.FORMATS:
        raise HTTPException(400, "format")
    return fmt


@app.get("/api/videos/{video_id}/export")
def export_video(video_id: str, format: str = "txt"):
    fmt = _fmt(format)
    v, segs = _transcript(video_id)
    return _download(export.render(v, segs, fmt), export.filename(v, fmt), export.FORMATS[fmt])


@app.get("/api/sources/{source_id}/export")
def export_source(source_id: int, format: str = "txt"):
    fmt = _fmt(format)
    src = db().execute("select * from source where id=?", (source_id,)).fetchone()
    if not src:
        raise HTTPException(404)
    ids = [r["id"] for r in db().execute(
        "select id from video where source_id=? and state='ready' order by upload_date desc", (source_id,))]
    data = export.bundle([_transcript(i) for i in ids], fmt)
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", src["title"] or f"source-{source_id}").strip()[:80] or f"source-{source_id}"
    return _download(data, f"{name} ({fmt}).zip", "application/zip")


# ---------- sharing: a link anyone can open, for one video's transcript ----------

def _share_url(token: str) -> str:
    return f"{config.PUBLIC_URL}/s/{token}"


@app.post("/api/videos/{video_id}/share")
def share_video(video_id: str, request: Request):
    _transcript(video_id)
    row = db().execute("select token from share where video_id=?", (video_id,)).fetchone()
    if row:
        return {"token": row["token"], "url": _share_url(row["token"])}
    p, _ = _me(request)
    token = secrets.token_urlsafe(12)
    db().execute("insert into share(token, video_id, made_by, made_at) values (?,?,?,?)",
                 (token, video_id, (p and p["username"]) or "tailnet", int(time.time())))
    return {"token": token, "url": _share_url(token)}


@app.get("/api/shares")
def list_shares(request: Request):
    p, tailnet = _me(request)
    admin = tailnet or bool(p and p["owner"])
    rows = db().execute(
        "select share.*, video.title, video.channel from share join video on video.id=share.video_id"
        " where ? or share.made_by=? order by made_at desc", (int(admin), (p and p["username"]) or "")).fetchall()
    return {"shares": [{**dict(r), "url": _share_url(r["token"])} for r in rows]}


@app.delete("/api/shares/{token}")
def stop_share(token: str, request: Request):
    p, tailnet = _me(request)
    admin = tailnet or bool(p and p["owner"])
    db().execute("delete from share where token=? and (? or made_by=?)", (token, int(admin), (p and p["username"]) or ""))
    return {"ok": True}


def _shared(token: str):
    row = db().execute("select video_id from share where token=?", (token,)).fetchone()
    if not row:
        raise HTTPException(404)
    return _transcript(row["video_id"])


@app.get("/s/{token}")
def shared_page(token: str):
    return FileResponse(STATIC / "share.html", headers={"x-robots-tag": "noindex", "referrer-policy": "no-referrer"})


@app.get("/api/shared/{token}")
def shared_data(token: str):
    v, segs = _shared(token)
    keep = ("id", "title", "channel", "upload_date", "duration", "lang", "origin")
    return {"video": {k: v.get(k) for k in keep}, "segments": segs}


@app.get("/api/shared/{token}/export")
def shared_export(token: str, format: str = "txt"):
    fmt = _fmt(format)
    v, segs = _shared(token)
    return _download(export.render(v, segs, fmt), export.filename(v, fmt), export.FORMATS[fmt])


# ---------- chat: questions about the transcripts, answered by Claude ----------

CHAT_STATUS = {"missing": 404, "video": 404, "source": 404, "off": 403, "day": 429}


def _chatter(request: Request) -> tuple[str, bool]:
    """Whose chats these are (the tailnet has its own), and whether that's the owner."""
    p, tailnet = _me(request)
    if not chat.allowed(p, tailnet):
        raise HTTPException(403, "chat")
    return (p["email"] if p else "tailnet"), bool(tailnet or p["owner"])


def _chat_do(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except chat.Refused as e:
        raise HTTPException(CHAT_STATUS.get(str(e), 400), str(e))


class NewChat(BaseModel):
    video_id: str | None = None
    source_id: int | None = None


class Question(BaseModel):
    text: str


@app.get("/api/chats")
def api_chats(request: Request):
    return {"chats": chat.chats(_chatter(request)[0])}


@app.post("/api/chats")
def api_chat_new(body: NewChat, request: Request):
    return _chat_do(chat.new_chat, _chatter(request)[0], body.video_id, body.source_id)


@app.get("/api/chats/{chat_id}")
def api_chat(chat_id: int, request: Request):
    return _chat_do(chat.get_chat, _chatter(request)[0], chat_id)


@app.delete("/api/chats/{chat_id}")
def api_chat_delete(chat_id: int, request: Request):
    chat.delete_chat(_chatter(request)[0], chat_id)
    return {"ok": True}


@app.post("/api/chats/{chat_id}/ask")
def api_chat_ask(chat_id: int, body: Question, request: Request):
    who, owner = _chatter(request)
    c, use, q = _chat_do(chat.start, who, chat_id, body.text, owner)
    return StreamingResponse(chat.answer(who, c, use, q, gone=request.is_disconnected),
                             media_type="text/event-stream", headers={"cache-control": "no-cache", "x-accel-buffering": "no"})


@app.post("/api/chats/stop")
def api_chat_stop(request: Request):
    chat.stop(_chatter(request)[0])
    return {"ok": True}


class ChatSettings(BaseModel):
    on: bool | None = None
    model: str | None = None
    model_name: str | None = None
    everyone: bool | None = None


class Connection(BaseModel):
    preset: str | None = None
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None


@app.get("/api/chat/settings")
def api_chat_settings(request: Request):
    _owner_only(request)
    return chat.settings()


@app.post("/api/chat/settings")
def api_chat_settings_save(body: ChatSettings, request: Request):
    _owner_only(request)
    return _chat_do(chat.set_settings, **body.model_dump(exclude_none=True))


@app.post("/api/chat/connections")
def api_chat_connection_add(body: Connection, request: Request):
    _owner_only(request)
    return _chat_do(chat.add_connection, **body.model_dump(exclude_none=True))


@app.patch("/api/chat/connections/{cid}")
def api_chat_connection_edit(cid: int, body: Connection, request: Request):
    _owner_only(request)
    return _chat_do(chat.edit_connection, cid, **body.model_dump(exclude_none=True, exclude={"preset"}))


@app.delete("/api/chat/connections/{cid}")
async def api_chat_connection_delete(cid: int, request: Request):
    _owner_only(request)
    if any(c["id"] == cid and c["preset"] == "chatgpt" for c in chat.settings()["connections"]):
        await chatgpt.disconnect()                  # signs out at OpenAI too
    return chat.delete_connection(cid)


# ChatGPT's sign-in (see chatgpt.py): start, then finish from the address the browser landed on,
# pasted, or right here when the browser is on this computer.

class Callback(BaseModel):
    url: str = ""


@app.post("/api/chat/chatgpt/start")
def api_chatgpt_start(request: Request):
    _owner_only(request)
    return {"url": chatgpt.start()}


@app.post("/api/chat/chatgpt/finish")
async def api_chatgpt_finish(body: Callback, request: Request):
    _owner_only(request)
    try:
        await chatgpt.finish(chatgpt.parse_callback(body.url))
    except chatgpt.SignInError as e:
        raise HTTPException(400, f"signin-{e}") from None
    return chat.chatgpt_signed_in()


@app.get("/auth/callback")
async def api_chatgpt_callback(request: Request):
    _owner_only(request)
    try:
        await chatgpt.finish(dict(request.query_params))
        chat.chatgpt_signed_in()
        return RedirectResponse("/#/settings")
    except chatgpt.SignInError as e:
        return RedirectResponse(f"/#/settings?chatgpt={e}")


@app.get("/api/chat/connections/{cid}/models")
async def api_chat_connection_models(cid: int, request: Request, fresh: int = 0):
    _owner_only(request)
    try:
        return {"models": await chat.models(cid, fresh=bool(fresh))}
    except chat.Refused as e:
        raise HTTPException(CHAT_STATUS.get(str(e), 502), str(e)) from None


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
