"""Rebuild the word index from stored transcripts: python -m tamlil.reindex

Run after changing the word rules in hebrew.py. Nothing is downloaded again.
"""

from .db import connect, save_transcript


def main():
    db = connect()
    vids = db.execute("select id, origin, model, lang from video where state='ready'").fetchall()
    for v in vids:
        segs = [dict(r) for r in db.execute(
            "select start_ms, end_ms, text from segment where video_id=? order by idx", (v["id"],))]
        save_transcript(db, v["id"], segs, v["origin"], v["model"], v["lang"])
    print(f"reindexed {len(vids)} videos")


if __name__ == "__main__":
    main()
