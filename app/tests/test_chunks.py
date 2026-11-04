from tamlil.db import chunks


def seg(start, end):
    return {"start_ms": start * 1000, "end_ms": end * 1000, "text": ""}


def covered(segs):
    out = set()
    for a, b in chunks(segs):
        out.update(range(a, b + 1))
    return out


def test_every_line_lands_in_a_chunk_even_with_long_lines():
    segs = [seg(498, 511), seg(511, 587), seg(587, 602)]
    assert covered(segs) == {0, 1, 2}


def test_short_lines_share_overlapping_windows():
    segs = [seg(t, t + 3) for t in range(0, 120, 3)]
    cs = chunks(segs)
    assert covered(segs) == set(range(len(segs)))
    starts = [segs[a]["start_ms"] for a, _ in cs]
    assert all(b - a >= 15_000 for a, b in zip(starts, starts[1:]))
    assert all(segs[b]["end_ms"] - segs[a]["start_ms"] <= 30_000 for a, b in cs)
