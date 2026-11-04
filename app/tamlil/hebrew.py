"""Word rules shared by the index and the search box.

Hebrew attaches prepositions, the article and conjunctions to the front of a
word (ו ה ב כ ל מ ש), writes acronyms with geresh/gershayim, and is often
pasted with niqqud and cantillation. We normalize all of that ourselves and
hand the full-text index finished tokens, plus every prefix-peeled form.
"""

import re
import unicodedata

PREFIXES = "והבכלמש"
FINAL = str.maketrans("ךםןףץ", "כמנפצ")
UNFINAL = {"כ": "ך", "מ": "ם", "נ": "ן", "פ": "ף", "צ": "ץ"}

_MARKS = re.compile(r"[֑-ׇ]")
_QUOTES = re.compile(r"[״׳\"'’`]")
# A word is letters, digits and Hebrew points; geresh/gershayim/apostrophes may
# sit inside it (רמב״ם, isn't). Maqaf, hyphens and sof pasuq split words.
_CH = r"(?:[^\W_]|[֑-ׇֽֿׁׂׅׄ])"
_TOKEN = re.compile(rf"{_CH}+(?:[״׳\"'’]{_CH}+)*")
_HEBREW = re.compile(r"[א-ת]")

STOP = {
    "the", "a", "an", "of", "to", "in", "is", "it", "and", "or", "not", "on", "for",
    "with", "my", "your", "why", "how", "what", "does", "do", "are", "be", "this", "that",
    "את", "של", "על", "זה", "לא", "גם", "אבל", "כי", "מה", "יש", "אז", "הוא", "היא",
    "עם", "אם", "או",
}


def is_hebrew(s: str) -> bool:
    return bool(_HEBREW.search(s))


def fold(word: str) -> str:
    """Strip niqqud, cantillation and quote marks; lowercase; fold final letters."""
    s = unicodedata.normalize("NFD", word)
    s = _MARKS.sub("", s)
    s = _QUOTES.sub("", s)
    s = s.lower().translate(FINAL)
    return unicodedata.normalize("NFC", s)


def unfold(word: str) -> str:
    """Restore the final letter form for display."""
    if word and is_hebrew(word) and word[-1] in UNFINAL:
        return word[:-1] + UNFINAL[word[-1]]
    return word


def stem(word: str) -> str:
    """A deliberately light English stemmer: rising/rises/rise → ris."""
    s = re.sub(r"(ing|ers|er|es|ed|s)$", "", word)
    if len(s) < 3:
        s = word
    if len(s) >= 4 and s.endswith("e"):
        s = s[:-1]
    return s


# Out of reverence, many speakers and writers put ק for ה in the divine name.
_ELOKIM = re.compile(r"^(אלו?)ק")


def variants(folded: str) -> list[str]:
    """The folded word plus the forms the index also stores for it."""
    out = [folded]
    if is_hebrew(folded):
        t = folded
        for _ in range(3):
            if len(t) > 3 and t[0] in PREFIXES:
                t = t[1:]
                out.append(t)
            else:
                break
        out += [_ELOKIM.sub(r"\1ה", f) for f in out if _ELOKIM.match(f)]
    else:
        s = stem(folded)
        if s != folded:
            out.append(s)
    return out


def skeleton(folded: str) -> str | None:
    """The word without inner ו and י, so full and short spellings meet:
    שמיים/שמים, אלוהים/אלהים, מאוד/מאד. None when nothing changes or too little is left."""
    if not is_hebrew(folded) or len(folded) < 3:
        return None
    s = folded[0] + folded[1:].replace("ו", "").replace("י", "")
    return s if s != folded and len(s) >= 3 else None


def mater_related(a: str, b: str) -> bool:
    """True when one word is the other with only ו/י letters added (full vs short spelling)."""
    if len(a) > len(b):
        a, b = b, a
    i = 0
    for ch in b:
        if i < len(a) and ch == a[i]:
            i += 1
        elif ch not in "וי":
            return False
    return i == len(a)


class Token:
    """A word in a line (index side) or in the search box (query side).

    Index side: forms are the word plus its prefix-peeled forms.
    Query side: Hebrew is never peeled (searching שמים must not mean מים);
    English still gets its light stem on both sides.
    """

    __slots__ = ("raw", "start", "end", "folded", "forms", "skels")

    def __init__(self, raw, start, end, query=False):
        self.raw, self.start, self.end = raw, start, end
        self.folded = fold(raw)
        if query and is_hebrew(self.folded):
            self.forms = [self.folded]
        else:
            self.forms = variants(self.folded)
        self.skels = list(dict.fromkeys(k for k in map(skeleton, self.forms) if k))

    def __repr__(self):
        return f"Token({self.raw!r}, {self.forms}, {self.skels})"


def tokens(text: str, query=False) -> list[Token]:
    """Words with their character offsets. Hyphens and maqaf split words."""
    out = []
    for m in _TOKEN.finditer(text):
        t = Token(m.group(0), m.start(), m.end(), query)
        if len(t.folded) >= 2:
            out.append(t)
    return out


def index_text(text: str) -> str:
    """What the full-text index stores for a stretch of speech."""
    words = []
    for t in tokens(text):
        words.extend(t.forms)
        words.extend(t.skels)
    return " ".join(dict.fromkeys(words))


def query_tokens(q: str) -> list[Token]:
    toks = tokens(q, query=True)
    kept = [t for t in toks if t.folded not in {fold(w) for w in STOP}]
    return kept or toks


def form_label(tok: Token, common: str) -> str:
    if is_hebrew(tok.folded):
        if tok.folded != common and tok.folded.endswith(common):
            return tok.folded[: len(tok.folded) - len(common)] + "+" + unfold(common)
        return unfold(tok.folded)
    return tok.raw.lower()


WEIGHT = {"exact": 10, "form": 8, "spelling": 5}


def match(text: str, qtoks: list[Token]):
    """Where the query's words occur in one line.

    Returns (ranges, why, score): ranges are (start, end, kind) with kind
    'exact', 'form' or 'spelling'; why is a de-duplicated list of [kind, detail].
    """
    ranges, why, seen = [], [], set()
    best: dict[int, str] = {}
    exact = 0
    for t in tokens(text):
        for i, q in enumerate(qtoks):
            kind, label = None, ""
            if t.folded == q.folded:
                kind = "exact"
                exact += 1
            else:
                common = next((f for f in q.forms if f in t.forms), None)
                if common:
                    kind, label = "form", form_label(t, common)
                elif q.skels and any(k in t.skels for k in q.skels) and any(
                        mater_related(qf, tf) for qf in q.forms for tf in t.forms):
                    kind, label = "spelling", unfold(t.folded)
            if not kind:
                continue
            ranges.append((t.start, t.end, kind))
            if (kind, label) not in seen:
                seen.add((kind, label))
                why.append([kind, label])
            if WEIGHT[kind] > WEIGHT.get(best.get(i), 0):
                best[i] = kind
            break
    return ranges, why, sum(WEIGHT[k] for k in best.values()) + exact
