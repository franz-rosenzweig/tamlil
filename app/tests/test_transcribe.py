import numpy as np

from tamlil import transcribe

SR = transcribe.SR


def test_short_audio_goes_in_whole():
    audio = np.ones(25 * 60 * SR, dtype=np.float32)
    assert transcribe._pieces(audio) == [(0, len(audio))]


def test_long_audio_is_cut_in_the_quiet():
    rng = np.random.default_rng(1)
    audio = rng.uniform(-0.5, 0.5, 104 * 60 * SR).astype(np.float32)       # 1h44, loud all through
    quiet = [(20 * 60 + 12) * SR, (40 * 60 + 5) * SR]                      # two pauses near the marks
    for q in quiet:
        audio[q : q + SR // 2] = 0
    pieces = transcribe._pieces(audio)

    assert pieces[0][0] == 0 and pieces[-1][1] == len(audio)
    assert all(a[1] == b[0] for a, b in zip(pieces, pieces[1:]))           # nothing lost, nothing twice
    assert all(b - a <= transcribe.WHOLE * SR for a, b in pieces)
    assert quiet[0] <= pieces[0][1] <= quiet[0] + SR // 2
    assert quiet[1] <= pieces[1][1] <= quiet[1] + SR // 2
