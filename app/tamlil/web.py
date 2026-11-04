import re
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import accounts, config
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

STATUS = {"not-on-list": 403, "owner": 403, "throttled": 429, "mail": 502, "wrong": 401, "expired": 401,
          "taken": 409, "exists": 409, "username": 400, "need-username": 400, "email": 400}


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


@app.post("/api/auth/logout")
def auth_logout():
    r = JSONResponse({"ok": True})
    r.delete_cookie(accounts.COOKIE, path="/")
    return r


@app.get("/login")
def login_page():
    return FileResponse(STATIC / "login.html")


@app.get("/api/me")
def api_me(request: Request):
    p, tailnet = _me(request)
    r = JSONResponse({"username": p and p["username"], "owner": bool(p and p["owner"]),
                      "tailnet": tailnet, "admin": tailnet or bool(p and p["owner"])})
    if p and p["renew"]:                       # slide the 180 days forward, once a day
        _set_cookie(r, request, accounts.renew(request.cookies.get(accounts.COOKIE)))
    return r


class Person(BaseModel):
    email: str


@app.get("/api/people")
def api_people(request: Request):
    _owner_only(request)
    return {"people": accounts.people(), "mail": accounts.mail.available()}


@app.post("/api/people")
def api_people_add(body: Person, request: Request):
    _owner_only(request)
    try:
        return accounts.allow(body.email)
    except accounts.Refused as e:
        raise _refused(e)


@app.delete("/api/people/{email}")
def api_people_remove(email: str, request: Request):
    _owner_only(request)
    try:
        accounts.remove(email)
    except accounts.Refused as e:
        raise _refused(e)
    return {"ok": True}


@app.get("/api/config")
def get_config():
    return {"player": config.PLAYER_URL}


@app.get("/api/search")
def api_search(q: str = "", lang: str = "all", source: int | None = None):
    return search(db(), q, None if lang == "all" else lang, source)


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
    url = s.url.strip()
    if not re.match(r"^https?://(www\.|m\.)?(youtube\.com|youtu\.be)/", url):
        raise HTTPException(400, "YouTube link")
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


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
