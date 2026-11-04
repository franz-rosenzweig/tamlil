import json
import sqlite3
import time

from . import config
from .hebrew import index_text

SCHEMA = """
create table if not exists source(
  id integer primary key,
  url text not null unique,
  kind text,
  title text,
  lang text default 'auto',
  date_from text,
  date_to text,
  max_videos integer,
  added_at text default (datetime('now')),
  checked_at text,
  state text default 'new',
  error text
);
create table if not exists video(
  id text primary key,
  source_id integer references source(id) on delete cascade,
  title text,
  channel text,
  upload_date text,
  duration integer,
  description text,
  lang text,
  tracks text,
  state text default 'new',
  origin text,
  model text,
  error text,
  attempts integer default 0,
  retry_at real default 0,
  updated_at text default (datetime('now'))
);
create table if not exists segment(
  video_id text references video(id) on delete cascade,
  idx integer,
  start_ms integer,
  end_ms integer,
  text text,
  primary key(video_id, idx)
);
create table if not exists chunk(
  id integer primary key,
  video_id text references video(id) on delete cascade,
  seg_from integer,
  seg_to integer,
  start_ms integer,
  end_ms integer
);
create virtual table if not exists chunk_fts using fts5(norm, tokenize='unicode61 remove_diacritics 0');
create table if not exists kv(key text primary key, value text);
create index if not exists video_source on video(source_id);
create index if not exists video_state on video(state);
create index if not exists chunk_video on chunk(video_id);
"""

CHUNK_MS = 30_000
STEP_MS = 15_000


def connect() -> sqlite3.Connection:
    config.DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(config.DB_PATH, timeout=30, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("pragma journal_mode=wal")
    db.execute("pragma foreign_keys=on")
    db.execute("pragma busy_timeout=30000")
    db.executescript(SCHEMA)
    return db


def chunks(segments: list[dict]) -> list[tuple[int, int]]:
    """Overlapping windows of about 30 s, one starting every 15 s: (first, last) segment index."""
    out, last_start, covered = [], 0, -1
    for i, s in enumerate(segments):
        if i <= covered and s["start_ms"] < last_start + STEP_MS:
            continue
        j = i
        while j + 1 < len(segments) and segments[j + 1]["end_ms"] - s["start_ms"] <= CHUNK_MS:
            j += 1
        out.append((i, j))
        covered, last_start = max(covered, j), s["start_ms"]
    return out


def clear_transcript(db, video_id: str):
    db.execute("delete from chunk_fts where rowid in (select id from chunk where video_id=?)", (video_id,))
    db.execute("delete from chunk where video_id=?", (video_id,))
    db.execute("delete from segment where video_id=?", (video_id,))


def save_transcript(db, video_id: str, segments: list[dict], origin: str, model: str | None, lang: str | None):
    db.execute("begin")
    try:
        clear_transcript(db, video_id)
        db.executemany(
            "insert into segment(video_id, idx, start_ms, end_ms, text) values (?,?,?,?,?)",
            [(video_id, i, s["start_ms"], s["end_ms"], s["text"]) for i, s in enumerate(segments)],
        )
        for a, b in chunks(segments):
            cur = db.execute(
                "insert into chunk(video_id, seg_from, seg_to, start_ms, end_ms) values (?,?,?,?,?)",
                (video_id, a, b, segments[a]["start_ms"], segments[b]["end_ms"]),
            )
            text = " ".join(s["text"] for s in segments[a : b + 1])
            db.execute("insert into chunk_fts(rowid, norm) values (?,?)", (cur.lastrowid, index_text(text)))
        db.execute(
            "update video set state='ready', origin=?, model=?, lang=coalesce(?, lang), error=null,"
            " updated_at=datetime('now') where id=?",
            (origin, model, lang, video_id),
        )
        db.execute("commit")
    except Exception:
        db.execute("rollback")
        raise


def set_status(db, **status):
    status["at"] = time.time()
    db.execute(
        "insert into kv(key, value) values ('worker', ?) on conflict(key) do update set value=excluded.value",
        (json.dumps(status, ensure_ascii=False),),
    )


def get_status(db) -> dict:
    row = db.execute("select value from kv where key='worker'").fetchone()
    return json.loads(row["value"]) if row else {}
