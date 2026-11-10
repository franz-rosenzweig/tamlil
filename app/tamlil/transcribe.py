"""Speech to timed lines with faster-whisper, on the CPU.

Hebrew goes to ivrit.ai's Hebrew fine-tune; everything else to large-v3-turbo.
Only one model stays loaded at a time, to keep memory down.
"""

import re

from . import config

_loaded = {"name": None, "model": None}

# Lines Whisper is known to invent over silence and music.
_PHANTOM = re.compile(
    r"^(thanks? (you )?for watching|thank you\.?|subtitles? by|please subscribe|תודה רבה\.?|תודה שצפיתם)[.!]*$",
    re.IGNORECASE,
)


def _model(name: str):
    if _loaded["name"] != name:
        from faster_whisper import WhisperModel

        _loaded["model"] = None
        _loaded["model"] = WhisperModel(
            name, device="cpu", compute_type="int8", cpu_threads=config.WHISPER_THREADS
        )
        _loaded["name"] = name
    return _loaded["model"]


def model_for(lang: str | None) -> str:
    return config.WHISPER_MODEL_HE if lang == "he" else config.WHISPER_MODEL


SR = 16000
WHOLE = 30 * 60     # audio up to this long goes to Whisper in one go
PIECE = 20 * 60     # longer audio goes in pieces about this long (1h44 in one go needed more than 6 GB)


def _pieces(audio) -> list[tuple[int, int]]:
    """(start, end) sample ranges covering the audio, each cut at the quietest moment within
    30 seconds of the mark, so the cut falls between words."""
    import numpy as np

    n, out, start = len(audio), [], 0
    frame = SR // 20                                   # 50 ms
    while n - start > WHOLE * SR:
        lo = start + (PIECE - 30) * SR
        win = audio[lo : lo + 60 * SR]
        win = win[: len(win) // frame * frame].reshape(-1, frame)
        cut = lo + int(np.square(win).mean(axis=1).argmin()) * frame + frame // 2
        out.append((start, cut))
        start = cut
    out.append((start, n))
    return out


def detect_language(path, audio=None) -> str | None:
    from faster_whisper.audio import decode_audio

    if audio is None:
        audio = decode_audio(str(path), sampling_rate=SR)
    middle = max(0, len(audio) // 2 - 15 * SR)
    clip = audio[middle : middle + 30 * SR]
    _, info = _model(config.WHISPER_MODEL).transcribe(clip, language=None, vad_filter=True)
    return "he" if info.language in ("he", "iw") else info.language


def transcribe(path, lang: str | None, prompt: str = "", progress=None):
    """Return (segments, lang, model_name). progress(fraction) is called as it goes."""
    from faster_whisper.audio import decode_audio

    audio = decode_audio(str(path), sampling_rate=SR)
    if not lang:
        lang = detect_language(path, audio)
    name = model_for(lang)
    total = len(audio) / SR
    out, last = [], None
    for a, b in _pieces(audio):
        offset = a / SR
        segments, _ = _model(name).transcribe(
            audio[a:b],
            language=lang,
            task="transcribe",
            beam_size=config.WHISPER_BEAM,
            vad_filter=True,
            condition_on_previous_text=False,
            initial_prompt=prompt[:220] or None,
        )
        for s in segments:
            start, end = s.start + offset, s.end + offset
            text = s.text.strip()
            if progress and total:
                progress(min(1.0, end / total))
            if not text or text == last or _PHANTOM.match(text):
                continue
            if s.no_speech_prob > 0.6 and s.avg_logprob < -1.0:
                continue
            out.append({"start_ms": int(start * 1000), "end_ms": int(end * 1000), "text": text})
            last = text
    return out, lang, name
