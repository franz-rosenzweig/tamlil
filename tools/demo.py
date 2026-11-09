"""A demo of Tamlil with made-up channels, for the screenshots in the docs.

It builds a throwaway database (a Hebrew lecture series, an English channel and a Hebrew playlist,
all invented, with their transcripts) and serves the real app on it, with drawn thumbnails and a
still "player" in place of Invidious and YouTube. Nothing here touches the internet.

  docker run --rm -v "$PWD:/src:ro" -p 127.0.0.1:8499:8000 tamlil:latest python /src/tools/demo.py
  then open http://127.0.0.1:8499

The verses quoted are Genesis 1 and Psalms in Hebrew, and the King James Version in English.
Everything else is written for the demo.
"""

import argparse
import base64
import html
import json
import shutil
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

SOURCES = [
    {"url": "https://www.youtube.com/@demo-beit-midrash", "kind": "channel", "title": "בית מדרש בראשית",
     "lang": "he", "date_from": "2025-09-01", "colors": ("#1F3B5C", "#3E7CB1")},
    {"url": "https://www.youtube.com/@demo-close-reading", "kind": "channel", "title": "Genesis Close Reading",
     "lang": "en", "date_from": "2026-01-01", "colors": ("#4A2C1E", "#C0703A")},
    {"url": "https://www.youtube.com/playlist?list=PLdemo-erev", "kind": "playlist", "title": "שיחות ערב · עונה 2",
     "lang": "auto", "max_videos": 20, "colors": ("#233B2E", "#4F9A6E")},
]

WHISPER = "ivrit-ai/whisper-large-v3-turbo-ct2"

# (source, id, title, date, origin, lines)
VIDEOS = [
    (0, "dmRakia0003", "בריאת הרקיע · שיעור 3", "20261028", "whisper", """
ערב טוב לכולם, אנחנו ממשיכים היום ביום השני של הבריאה.
בשבוע שעבר דיברנו על האור, והיום נגיע לרקיע.
נקרא קודם את הפסוק: ויאמר אלהים יהי רקיע בתוך המים.
ויהי מבדיל בין מים למים.
השאלה הראשונה היא פשוטה: מה זה בכלל רקיע?
המילה באה מהשורש ר־ק־ע, כמו לרקוע ברגל, או לרקע פח.
משהו שמרדדים אותו ומותחים אותו, כמו יריעה דקה.
ובספר שמות כתוב וירקעו את פחי הזהב, אותו שורש בדיוק.
אז הרקיע הוא משהו מתוח, משהו שמפריד.
ובפסוק הבא כתוב ויעש אלהים את הרקיע.
ויבדל בין המים אשר מתחת לרקיע ובין המים אשר מעל לרקיע.
שימו לב, יש מים מתחת לרקיע ויש מים מעל לרקיע.
ועל זה נשאל בשבוע הבא, מה הם המים העליונים.
ואז מגיע הפסוק: ויקרא אלהים לרקיע שמים.
כלומר הרקיע מקבל שם, הוא נהיה השמים.
רש"י אומר שהשמים נבראו ביום הראשון, אבל עדיין היו לחים.
ורק ביום השני הם קרשו, מגערת הקב"ה.
יש כאן רעיון יפה: השמים נבראו, אבל רק ביום השני הם עמדו במקומם.
ויש עוד דבר מעניין, ביום השני לא כתוב כי טוב.
רש"י אומר שזה בגלל שמלאכת המים לא נגמרה עד היום השלישי.
ויש מדרש שאומר שזה בגלל שביום השני נבראה מחלוקת, הפרדה.
הרקיע מבדיל, והבדלה לבד היא עוד לא טוב.
רק כשהמים מתכנסים למקום אחד ביום השלישי, נאמר פעמיים כי טוב.
בפעם הבאה נלמד את הפסוק מתהלים, השמים מספרים כבוד אל.
ומעשה ידיו מגיד הרקיע, אותו רקיע בדיוק.
תודה רבה, ולילה טוב.
"""),
    (0, "dmMayim0002", "המים העליונים והמים התחתונים", "20261021", "whisper", """
שלום לכולם, היום נדבר על המים העליונים.
ראינו שהרקיע מבדיל בין המים אשר מתחת לרקיע ובין המים אשר מעל לרקיע.
אז איפה המים העליונים? מעל השמים?
בתהלים כתוב: הללוהו שמי השמים, והמים אשר מעל השמים.
יש מפרשים שאומרים שאלה העננים, המים שבאוויר.
ויש שאומרים שזה דבר שאין לנו מושג בו בכלל.
הרמב"ן מאריך בזה, ואומר שהרקיע נמתח באמצע המים.
ויש מדרש מפורסם על המים התחתונים, שבכו שהם רחוקים מהקב"ה.
הם רצו להיות קרובים, גם הם רצו להיות בשמים.
ולכן הובטח להם שיעלו על המזבח, בניסוך המים בסוכות.
יש בזה משהו נוגע ללב: גם מה שלמטה רוצה להיות קרוב.
ובשמחת בית השואבה שמחים בדיוק עם המים האלה.
נסכם: הרקיע מבדיל, אבל הקשר בין המים לא נקטע.
בשיעור הבא נלמד על היום השלישי ועל היבשה.
"""),
    (0, "dmShamay001", "שמיים וארץ: עיון בפסוק הראשון", "20261014", "whisper", """
בראשית ברא אלוקים את השמיים ואת הארץ.
זה הפסוק הראשון בתורה, והוא נראה פשוט, אבל הוא לא.
קודם כל, המילה בראשית: בראשית של מה?
רש"י אומר שהפסוק הזה לא בא ללמד על סדר הבריאה.
הוא אומר: אין המקרא הזה אומר אלא דרשני.
ושנית, למה כתוב את השמיים ואת הארץ, ולא רק שמיים וארץ?
יש מי שאומר שהמילה את באה לרבות, לכלול עוד דברים.
את השמיים לרבות השמש והירח והכוכבים.
ואת הארץ לרבות האילנות והדשאים.
כלומר הכל כבר נמצא בפסוק הראשון, בכוח.
ובימים הבאים זה רק יוצא לפועל, אחד אחד.
וזה מסביר למה הרקיע ביום השני נקרא שוב שמיים.
השמיים של הפסוק הראשון הם השורש, והרקיע הוא מה שאנחנו רואים.
"""),
    (0, "dmOrYom0000", "אור ביום הראשון", "20261007", "whisper", """
ויאמר אלהים יהי אור ויהי אור.
אבל השמש נבראה רק ביום הרביעי, אז מה היה האור הזה?
חז"ל אומרים שזה אור מיוחד, שאדם היה רואה בו מסוף העולם ועד סופו.
והקב"ה גנז אותו לצדיקים לעתיד לבוא.
וירא אלהים את האור כי טוב, ויבדל אלהים בין האור ובין החשך.
שוב הבדלה, כמו שנראה ביום השני עם הרקיע.
ויקרא אלהים לאור יום ולחשך קרא לילה.
ויהי ערב ויהי בקר יום אחד, ולא יום ראשון.
רש"י מסביר שזה כי עדיין היה הקב"ה יחיד בעולמו.
"""),
    (1, "dmFirmamnt2", "Day Two: What Is the Firmament?", "20261030", "uploader", """
Welcome back. Today we're on day two, and the word everyone trips over: firmament.
The Hebrew is rakia, and it comes from a verb that means to beat out, to hammer flat.
Think of a smith hammering gold into a thin sheet.
In Exodus they hammer the gold into thin plates, and it's the same root.
So the firmament is something stretched out, something that divides.
And God said, Let there be a firmament in the midst of the waters,
and let it divide the waters from the waters.
Notice that there are waters under the firmament and waters above it.
Then the firmament gets a name. And God called the firmament Heaven.
So the heaven of verse one and the firmament of day two are connected.
One reading says the heavens were made on day one but only set firm on day two.
That's why the old translators reached for firmament, from the Latin firmus, solid.
Next week: the waters above the heavens.
"""),
    (1, "dmWatersAbv", "The Waters Above the Heavens", "20261016", "uploader", """
Psalm 148 has a line I love.
Praise him, ye heavens of heavens, and ye waters that be above the heavens.
So what are the waters above the heavens?
Some read them as rain clouds, water held up in the sky.
Others say it's a picture of an ordered world, with the deep held back on every side.
The firmament keeps the waters apart, and that keeps a space open for life.
There's a midrash where the lower waters weep, because they're far from God.
And they're promised a place on the altar, in the water libation at Sukkot.
I find that moving: even the lowest things want to be close.
"""),
    (1, "dmLightSun1", "Light Before the Sun", "20260925", "uploader", """
And God said, Let there be light: and there was light.
The sun doesn't show up until day four, so what is this light?
The rabbis say it was a special light, hidden away for the righteous.
And God saw the light, that it was good: and God divided the light from the darkness.
The first thing light does in the Bible is make a division, just like the firmament on day two.
And the evening and the morning were the first day.
"""),
    (2, "dmKachol0007", "למה השמיים כחולים?", "20261025", "uploader", """
שאלה שכל ילד שואל: למה השמיים כחולים?
האור של השמש נראה לבן, אבל יש בו את כל הצבעים.
כשהאור עובר באוויר, הוא פוגש מולקולות קטנות מאוד.
והן מפזרות את האור הכחול הרבה יותר מאשר את האדום.
אז לאן שלא נסתכל בשמיים, מגיע אלינו אור כחול מפוזר.
ובשקיעה, כשהאור עובר דרך הרבה יותר אוויר, הכחול כבר התפזר בדרך.
ומה שנשאר לנו זה האדום והכתום.
אז בפעם הבאה שאתם מסתכלים על השקיעה, תחשבו על כל האוויר הזה.
"""),
    (2, "dmEmunah0006", "שיחה על אמונה ומדע", "20261018", "uploader", """
הערב אני רוצה לדבר על שאלה ששואלים אותי הרבה.
איך אפשר לקרוא את סיפור הבריאה ולהכיר גם את המדע?
יש מי שרואה סתירה, ויש מי שרואה שתי שפות שונות.
התורה לא באה ללמד אותנו פיזיקה, היא באה ללמד אותנו משהו על העולם ועל עצמנו.
כשכתוב שאלוקים הבדיל בין המים למים, אני שומע משהו על סדר.
העולם הוא לא תוהו ובוהו, יש בו גבולות, יש בו מקום.
והמדע מתאר את הסדר הזה בשפה אחרת, בשפה של מספרים.
אני לא חושב שצריך לבחור.
"""),
]

# Still on their way: one being transcribed, one waiting.
PENDING = [
    (0, "dmYomShel05", "ויהי ערב ויהי בקר · שיעור 5", "20261102", "transcribing", 2710),
    (0, "dmYabasha04", "היום השלישי: היבשה והים", "20261104", "new", 2460),
]

PEOPLE = [("dana@example.com", "dana", "Dana Mizrahi"), ("yoni@example.com", "yoni", "Yoni Peretz"),
          ("avital@example.com", None, "Avital")]
ASKING = [("noam@example.com", "Noam Shapira", "noam.s", "From the Thursday night shiur", 3 * 3600),
          ("ruth.b@example.com", "Ruth Ben-David", "ruthbd", "Dana's sister", 26 * 3600)]

# Two chats, as Claude answered them on this demo (through Claude Code): one about the whole library,
# one about a single lecture with a follow-up.
CHATS = [
    (None, [
        ('user', "Where do the lectures talk about the firmament dividing the waters, and what do they say?"),
        ('assistant', "Two lectures cover this. Both are about day two of creation, Genesis 1:6–8.\n\n**\"בריאת הרקיע · שיעור 3\" (בית מדרש בראשית, Hebrew)**\n- It reads the verse \"יהי רקיע בתוך המים, ויהי מבדיל בין מים למים\" ([0:18](#dmRakia0003@0:18)).\n- It traces \"רקיע\" to the root ר־ק־ע, meaning to beat or stretch something thin. It compares Exodus, \"וירקעו את פחי הזהב\". So the firmament is \"something stretched, something that separates\" ([0:40](#dmRakia0003@0:40)).\n- It points out that there are waters below the firmament and waters above it ([1:21](#dmRakia0003@1:21)). The question of what the upper waters are is left for the following week.\n- Rashi says the heavens were created on day one but were still liquid, and only set firm on day two ([1:53](#dmRakia0003@1:53)).\n- On why day two lacks \"כי טוב\", it gives two reasons. Rashi says the work on the waters wasn't finished until day three. A midrash says day two created division, and separation alone isn't yet good ([2:18](#dmRakia0003@2:18)).\n\n**\"Day Two: What Is the Firmament?\" (Genesis Close Reading, English)**\n- It explains that *rakia* comes from a verb meaning to beat out or hammer flat, like a smith hammering gold into a thin sheet. It cites the same root in Exodus ([0:10](#dmFirmamnt2@0:10)).\n- It quotes \"let it divide the waters from the waters\" ([0:50](#dmFirmamnt2@0:50)). It notes there are waters under the firmament and waters above it ([1:07](#dmFirmamnt2@1:07)).\n- It links the \"heaven\" of verse one to the firmament of day two. One reading says the heavens were made on day one but only set firm on day two ([1:26](#dmFirmamnt2@1:26)).\n- The English word \"firmament\" comes from the Latin *firmus*, \"solid\" ([1:42](#dmFirmamnt2@1:42)).\n- The next lecture is on the waters above the heavens.\n\nThe two lectures make nearly the same points. The Hebrew one adds the discussion of \"כי טוב\" and the midrash on division."),
    ]),
    ('dmRakia0003', [
        ('user', "מה אומר השיעור על כי טוב ביום השני?"),
        ('assistant', "השיעור מציין שביום השני לא כתוב \"כי טוב\" ([2:18](#dmRakia0003@2:18)), ומביא שני הסברים:\n\n- **רש\"י:** זה בגלל שמלאכת המים לא נגמרה עד היום השלישי ([2:26](#dmRakia0003@2:26)).\n- **מדרש:** ביום השני נבראה מחלוקת, כלומר הפרדה. הרקיע מבדיל, והבדלה לבדה היא עוד לא טוב ([2:33](#dmRakia0003@2:33)).\n\nבהמשך, כשהמים מתכנסים למקום אחד ביום השלישי, נאמר \"כי טוב\" פעמיים ([2:48](#dmRakia0003@2:48))."),
        ('user', "And what does Rashi say there, in one sentence?"),
        ('assistant', "Rashi says that \"ki tov\" is missing on the second day because the work of the waters wasn't finished until the third day ([2:26](#dmRakia0003@2:26))."),
    ]),
]

def timings(lines):
    """Spoken-ish timestamps: about 0.42 s a word, with pauses that vary."""
    segs, t = [], 4000
    for i, text in enumerate(lines):
        dur = max(2400, len(text.split()) * 420)
        segs.append({"start_ms": t, "end_ms": t + dur, "text": text})
        t += dur + 900 + (i * 7919 % 5) * 1400
    return segs, t // 1000 + 20


def build(data: Path):
    from tamlil import accounts, config, db as dbm

    if data.exists():
        shutil.rmtree(data)
    data.mkdir(parents=True)
    config.DATA, config.DB_PATH = data, data / "tamlil.db"
    db = dbm.connect()
    for s in SOURCES:
        db.execute(
            "insert into source(url, kind, title, lang, date_from, max_videos, checked_at, state)"
            " values (?,?,?,?,?,?,datetime('now','-2 hours'),'ok')",
            (s["url"], s["kind"], s["title"], s["lang"], s.get("date_from"), s.get("max_videos")),
        )
    for si, vid, title, day, origin, text in VIDEOS:
        segs, duration = timings([l for l in text.strip().splitlines() if l.strip()])
        lang = "en" if si == 1 else "he"
        channel = SOURCES[si]["title"].split(" · ")[0]
        db.execute(
            "insert into video(id, source_id, title, channel, upload_date, duration, lang, tracks, state)"
            " values (?,?,?,?,?,?,?,'{}','new')", (vid, si + 1, title, channel, day, duration, lang))
        dbm.save_transcript(db, vid, segs, origin, WHISPER if origin == "whisper" else None, lang)
    for si, vid, title, day, state, duration in PENDING:
        db.execute(
            "insert into video(id, source_id, title, channel, upload_date, duration, lang, tracks, state)"
            " values (?,?,?,?,?,?,'he','{}',?)", (vid, si + 1, title, SOURCES[si]["title"].split(" · ")[0], day, duration, state))

    for email, _, name in PEOPLE:
        accounts.allow(email, invite=False, name=name)
    d = accounts._read()
    for p in d["people"]:
        username = next(u for e, u, _ in PEOPLE if e == p["email"])
        if username:
            p["username"], p["joined"] = username, p["added"] + 3600
    d["people"][0]["pass"] = accounts.hash_pass("demo-password")
    now = int(time.time())
    d["requests"] = [{"email": e, "name": n, "username": u, "note": note, "pass": None, "at": now - ago}
                     for e, n, u, note, ago in ASKING]
    accounts._write(d)
    db.execute("update source set paused=1 where id=3")              # the playlist, paused
    db.execute("insert into share(token, video_id, made_by, made_at) values ('demo-share-link', ?, 'dana', ?)",
               (VIDEOS[0][1], now - 86400))
    from tamlil import chat
    chat.add_connection(preset="claude_code", api_key="sk-ant-oat01-demo-" + "0" * 30)
    chat.add_connection(preset="openrouter", api_key="sk-or-v1-demo-" + "0" * 40)
    chat.add_connection(preset="ollama", name="Ollama on the desktop", base_url="http://192.168.1.20:11434/v1")
    chat.set_settings(on=True, everyone=True)
    for i, (video_id, turns) in enumerate(CHATS):
        c = chat.new_chat(PEOPLE[0][0], video_id=video_id)
        at = now - 3600 * (len(CHATS) - i)
        for role, text in turns:
            db.execute("insert into chat_msg(chat_id, role, text, refs, at) values (?,?,?,?,?)",
                       (c["id"], role, text, json.dumps(chat._refs(text), ensure_ascii=False) if role == "assistant" else None, at))
        db.execute("update chat set title=?, updated_at=? where id=?", (turns[0][1][:90], at, c["id"]))
    return db, accounts._cookie(d, d["people"][0])


# ---------- drawn thumbnails and a still player, in place of Invidious ----------

FONT = ROOT / "app/tamlil/static/fonts"


def _font_css():
    out = []
    for name, rng in (("Rubik-hebrew", "U+0590-05FF"), ("Rubik-latin", "U+0000-00FF,U+2000-206F")):
        b64 = base64.b64encode((FONT / f"{name}.woff2").read_bytes()).decode()
        out.append(f"@font-face{{font-family:R;font-weight:400 900;src:url(data:font/woff2;base64,{b64}) format('woff2');unicode-range:{rng}}}")
    return "".join(out)


def _wrap(title, width):
    lines, cur = [], ""
    for w in title.split():
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return lines + [cur]


def thumb_svg(info, css, bare=False):
    title, colors, hebrew = info["title"], info["colors"], info["hebrew"]
    lines = [] if bare else [l for part in title.split(" · ") for l in _wrap(part, 16 if hebrew else 18)][:3]
    x, anchor = (296, "end") if hebrew else (24, "start")
    y0 = 80 - (len(lines) - 1) * 15
    text = "".join(f'<text x="{x}" y="{y0 + i * 30}" text-anchor="{anchor}">{html.escape(l)}</text>' for i, l in enumerate(lines))
    rings = "".join(f'<circle cx="{40 if hebrew else 280}" cy="196" r="{r}" fill="none" stroke="#fff" stroke-opacity=".07" stroke-width="10"/>'
                    for r in (60, 95, 130, 165))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 180" width="640" height="360">
<style>{css} text{{font-family:R,sans-serif;font-weight:700;font-size:25px;fill:#fff}}</style>
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{colors[0]}"/><stop offset="1" stop-color="{colors[1]}"/></linearGradient></defs>
<rect width="320" height="180" fill="url(#g)"/>{rings}{text}
</svg>"""


PLAYER = """<!doctype html><meta charset="utf-8"><style>
html,body{{margin:0;height:100%;background:#000;overflow:hidden;font:13px system-ui,sans-serif;color:#fff}}
img{{width:100%;height:100%;object-fit:cover;display:block;filter:brightness(.82)}}
.play{{position:absolute;inset:0;margin:auto;width:76px;height:54px;border-radius:14px;background:rgba(0,0,0,.6)}}
.play::after{{content:"";position:absolute;left:31px;top:15px;border-style:solid;border-width:12px 0 12px 20px;border-color:transparent transparent transparent #fff}}
.bar{{position:absolute;left:0;right:0;bottom:0;padding:22px 14px 10px;background:linear-gradient(transparent,rgba(0,0,0,.75));display:flex;align-items:center;gap:12px}}
.track{{flex:1;height:4px;border-radius:2px;background:rgba(255,255,255,.3)}} .track b{{display:block;height:100%;width:{pct}%;background:#fff;border-radius:2px}}
</style><img src="/vi/{vid}/frame.jpg" alt=""><div class="play"></div>
<div class="bar"><span>▶</span><div class="track"><b></b></div><span>{at} / {total}</span></div>"""


def _clock(s):
    return f"{s // 60}:{s % 60:02d}"


def serve(data: Path, port: int):
    import uvicorn
    from fastapi import Request, Response
    from fastapi.responses import HTMLResponse

    db, cookie = build(data)
    from tamlil import accounts, web
    from tamlil.db import connect, set_status

    css = _font_css()
    info = {}
    for v in db.execute("select id, title, channel, source_id, duration from video").fetchall():
        info[v[0]] = {"title": v[1], "channel": v[2], "duration": v[4] or 0, "hebrew": any("֐" <= c <= "׿" for c in v[1]),
                      "colors": SOURCES[v[3] - 1]["colors"]}

    def thumb(vid: str, name: str):
        if vid not in info:
            return Response(status_code=404)
        return Response(thumb_svg(info[vid], css, bare=name.startswith("frame")), media_type="image/svg+xml")

    def player(vid: str, request: Request):
        v = info.get(vid, {"duration": 0})
        t = min(int(request.query_params.get("t", 0)), v["duration"])
        return HTMLResponse(PLAYER.format(vid=vid, pct=round(100 * t / max(v["duration"], 1), 1), at=_clock(t), total=_clock(v["duration"])))

    web.app.add_api_route("/vi/{vid}/{name}", thumb)
    web.app.add_api_route("/embed/{vid}", player)

    def busy():                 # the worker, halfway through the next lecture
        own = connect()
        while True:
            set_status(own, doing="transcribing", source=1, title=PENDING[0][2], video=PENDING[0][1], progress=0.62)
            time.sleep(30)
    threading.Thread(target=busy, daemon=True).start()

    async def signed_in(scope, receive, send):        # everyone is dana, the owner
        if scope["type"] == "http" and scope["path"] != "/login":
            headers = [(k, v) for k, v in scope["headers"] if k != b"cookie"]
            scope = dict(scope, headers=headers + [(b"cookie", f"{accounts.COOKIE}={cookie}".encode())])
        await web.app(scope, receive, send)

    print(f"Tamlil demo on http://127.0.0.1:{port} (data in {data})", flush=True)
    uvicorn.run(signed_in, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", default="/tmp/tamlil-demo", type=Path)
    ap.add_argument("--port", default=8000, type=int)
    a = ap.parse_args()
    import os
    os.environ["TAMLIL_DATA"] = str(a.data)
    os.environ["TAMLIL_MAIL"] = "outbox"
    serve(a.data, a.port)
