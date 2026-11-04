from tamlil.vtt import parse

UPLOADER = """WEBVTT
Kind: captions
Language: en

00:00:01.360 --> 00:00:03.040
[♪♪♪]

00:00:18.640 --> 00:00:21.880
♪ We're no strangers to love ♪

00:00:22.640 --> 00:00:26.960
♪ You know the rules
and so do I ♪
"""

AUTO = """WEBVTT
Kind: captions
Language: en

00:00:00.160 --> 00:00:02.390 align:start position:0%

if<00:00:00.480><c> your</c><00:00:00.800><c> starter</c>

00:00:02.390 --> 00:00:02.400 align:start position:0%
if your starter


00:00:02.400 --> 00:00:05.110 align:start position:0%
if your starter
isn't<00:00:02.900><c> rising</c><00:00:03.300><c> after</c>

00:00:05.110 --> 00:00:05.120 align:start position:0%
isn't rising after


00:00:05.120 --> 00:00:07.000 align:start position:0%
isn't rising after
a<00:00:05.500><c> feeding</c> &amp; more
"""


def test_uploader_cues_join_lines_and_drop_sound_tags():
    segs = parse(UPLOADER)
    assert [s["text"] for s in segs] == ["♪ We're no strangers to love ♪", "♪ You know the rules and so do I ♪"]
    assert segs[0]["start_ms"] == 18640


def test_auto_captions_keep_each_line_once():
    segs = parse(AUTO)
    assert [s["text"] for s in segs] == ["if your starter", "isn't rising after", "a feeding & more"]
    assert [s["start_ms"] for s in segs] == [160, 2400, 5120]
    assert all(a["end_ms"] <= b["start_ms"] for a, b in zip(segs, segs[1:]))
