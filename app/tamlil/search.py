"""Word search over the transcripts.

The full-text index holds every word with its Hebrew prefix forms, so one
FTS5 query finds candidate 30-second chunks; then each line inside them is
matched again in Python to mark exactly which words hit and why.
"""

from .hebrew import is_hebrew, match, query_tokens, unfold

TOP_MOMENTS = 3


def _fts_query(qtoks, joiner):
    groups = []
    for t in qtoks:
        forms = list(dict.fromkeys(t.forms + t.skels))
        groups.append("(" + " OR ".join(f'"{f}"' for f in forms) + ")")
    return f" {joiner} ".join(groups)


SORTS = ("best", "newest", "oldest", "moments")


def _ymd(day: str | None) -> str | None:
    """'2026-10-28' or '20261028' as YouTube's '20261028'; anything else as no limit."""
    d = (day or "").replace("-", "")
    return d if len(d) == 8 and d.isdigit() else None


def search(db, q: str, lang: str | None = None, source: int | None = None, limit: int = 40, *,
           title: str = "", date_from: str | None = None, date_to: str | None = None, sort: str = "best") -> dict:
    """Videos whose transcripts say q, narrowed by language, source, words in the title and the
    upload date, and sorted by the best match, the newest, the oldest or the most moments."""
    qtoks = query_tokens(q or "")
    head = {
        "text": q,
        "lang": "he" if is_hebrew(q or "") else "en",
        "words": [{"raw": t.raw, "forms": [unfold(f) for f in t.forms]} for t in qtoks],
    }
    if not qtoks:
        return {"query": head, "results": [], "moments": 0}

    where, args = "", []
    if lang in ("he", "en"):
        where += " and video.lang = ?"
        args.append(lang)
    if source:
        where += " and video.source_id = ?"
        args.append(source)
    for w in (title or "").lower().split()[:6]:                 # every word, anywhere in the title
        where += " and lower(video.title) like ? escape '\\'"
        args.append("%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    if _ymd(date_from):
        where += " and video.upload_date >= ?"
        args.append(_ymd(date_from))
    if _ymd(date_to):
        where += " and video.upload_date <= ?"
        args.append(_ymd(date_to))
    sort = sort if sort in SORTS else "best"
    order = {"newest": "video.upload_date desc, rank", "oldest": "video.upload_date asc, rank"}.get(sort, "rank")

    sql = f"""select chunk.video_id, chunk.seg_from, chunk.seg_to, bm25(chunk_fts) as rank
              from chunk_fts join chunk on chunk.id = chunk_fts.rowid
              join video on video.id = chunk.video_id
              where chunk_fts match ? {where}
              order by {order} limit 600"""
    rows = db.execute(sql, [_fts_query(qtoks, "AND"), *args]).fetchall()
    if not rows and len(qtoks) > 1:
        rows = db.execute(sql, [_fts_query(qtoks, "OR"), *args]).fetchall()

    best_rank: dict[str, float] = {}
    spans: dict[str, set[int]] = {}
    for r in rows:
        best_rank[r["video_id"]] = min(best_rank.get(r["video_id"], 0), r["rank"])
        spans.setdefault(r["video_id"], set()).update(range(r["seg_from"], r["seg_to"] + 1))

    results = []
    for vid, idxs in spans.items():
        segs = db.execute(
            f"select idx, start_ms, end_ms, text from segment where video_id=? and idx in ({','.join('?' * len(idxs))})",
            (vid, *sorted(idxs)),
        ).fetchall()
        moments = []
        for s in segs:
            ranges, why, score = match(s["text"], qtoks)
            if ranges:
                moments.append({"idx": s["idx"], "start_ms": s["start_ms"], "end_ms": s["end_ms"],
                                "text": s["text"], "ranges": ranges, "why": why, "score": score})
        if not moments:
            continue
        v = db.execute(
            "select id, title, channel, upload_date, duration, lang, origin, model, source_id from video where id=?",
            (vid,),
        ).fetchone()
        top = sorted(moments, key=lambda m: (-m["score"], m["start_ms"]))[:TOP_MOMENTS]
        results.append({
            "video": dict(v),
            "top": sorted(top, key=lambda m: m["start_ms"]),
            "marks": [m["start_ms"] for m in moments],
            "moments": len(moments),
            "_key": (-max(m["score"] for m in moments), best_rank[vid]),
        })
    if sort == "newest":
        results.sort(key=lambda r: (r["video"]["upload_date"] or "", -r["moments"]), reverse=True)
    elif sort == "oldest":
        results.sort(key=lambda r: (r["video"]["upload_date"] or "99999999", -r["moments"]))
    elif sort == "moments":
        results.sort(key=lambda r: (-r["moments"], r["_key"]))
    else:
        results.sort(key=lambda r: r["_key"])
    for r in results:
        del r["_key"]
    results = results[:limit]
    return {"query": head, "results": results, "moments": sum(r["moments"] for r in results)}


def video_hits(db, video_id: str, q: str) -> list[dict]:
    """Every matching line in one video, for the transcript screen."""
    qtoks = query_tokens(q or "")
    if not qtoks:
        return []
    out = []
    for s in db.execute("select idx, text from segment where video_id=? order by idx", (video_id,)):
        ranges, why, score = match(s["text"], qtoks)
        if ranges:
            out.append({"idx": s["idx"], "ranges": ranges, "why": why})
    return out
