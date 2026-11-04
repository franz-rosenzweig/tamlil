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


def detect_language(path) -> str | None:
    from faster_whisper.audio import decode_audio

    audio = decode_audio(str(path), sampling_rate=16000)
    middle = max(0, len(audio) // 2 - 15 * 16000)
    clip = audio[middle : middle + 30 * 16000]
    _, info = _model(config.WHISPER_MODEL).transcribe(clip, language=None, vad_filter=True)
    return "he" if info.language in ("he", "iw") else info.language


def transcribe(path, lang: str | None, prompt: str = "", progress=None):
    """Return (segments, lang, model_name). progress(fraction) is called as it goes."""
    if not lang:
        lang = detect_language(path)
    name = model_for(lang)
    segments, info = _model(name).transcribe(
        str(path),
        language=lang,
        task="transcribe",
        beam_size=config.WHISPER_BEAM,
        vad_filter=True,
        condition_on_previous_text=False,
        initial_prompt=prompt[:220] or None,
    )
    out, last = [], None
    total = info.duration or 0
    for s in segments:
        text = s.text.strip()
        if progress and total:
            progress(min(1.0, s.end / total))
        if not text or text == last or _PHANTOM.match(text):
            continue
        if s.no_speech_prob > 0.6 and s.avg_logprob < -1.0:
            continue
        out.append({"start_ms": int(s.start * 1000), "end_ms": int(s.end * 1000), "text": text})
        last = text
    return out, lang, name
