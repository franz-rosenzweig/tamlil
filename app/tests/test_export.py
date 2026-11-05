import io
import json
import zipfile

from tamlil import export

V = {"id": "abcdefghijk", "title": 'A/B: "שמים" ', "channel": "Ch", "upload_date": "20260102", "duration": 3700}
SEGS = [{"start_ms": 0, "end_ms": 1500, "text": "hello"}, {"start_ms": 3_661_250, "end_ms": 3_663_000, "text": "בראשית"}]


def test_formats():
    txt = export.render(V, SEGS, "txt")
    assert "https://www.youtube.com/watch?v=abcdefghijk" in txt and "[0:00] hello" in txt and "[1:01:01] בראשית" in txt
    assert "Ch · 2026-01-02" in txt
    assert export.render(V, SEGS, "srt").startswith("1\n00:00:00,000 --> 00:00:01,500\nhello\n")
    vtt = export.render(V, SEGS, "vtt")
    assert vtt.startswith("WEBVTT\n\n00:00:00.000 --> 00:00:01.500") and "01:01:01.250 --> 01:01:03.000" in vtt
    assert json.loads(export.render(V, SEGS, "json"))["segments"][1]["text"] == "בראשית"


def test_names_and_zip():
    assert export.filename(V, "txt") == "A B שמים [abcdefghijk].txt"
    assert export.filename({"id": "x", "title": ""}, "srt") == "x.srt"
    z = zipfile.ZipFile(io.BytesIO(export.bundle([(V, SEGS)], "vtt")))
    assert z.namelist() == [export.filename(V, "vtt")]
