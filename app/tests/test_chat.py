import asyncio
import json
import threading
from types import SimpleNamespace as NS

import anthropic
import pytest

from tamlil import chat
from .test_search import db  # noqa: F401  (the same little library)

OWNER = {"email": "me@example.com", "owner": True}
GUEST = {"email": "dana@example.com", "owner": False}


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(chat, "_local", threading.local())      # a new connection for each test's database
    chat._running.clear()


def events(raw: str) -> list[tuple[str, dict]]:
    out = []
    for block in raw.strip().split("\n\n"):
        ev, data = block.split("\n")
        out.append((ev.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


def run(gen) -> list[tuple[str, dict]]:
    async def go():
        return "".join([x async for x in gen])
    return events(asyncio.run(go()))


def test_tools(db, monkeypatch):
    text, err = chat.run_tool("search", {"query": "רקיע"})
    assert not err and "a1 · בריאת הרקיע" in text and "[0:00] ויאמר אלהים יהי רקיע" in text
    assert "3 videos" in text
    text, err = chat.run_tool("search", {"query": "firmament", "source_id": "2"})
    assert not err and "b1" in text and "a1" not in text
    text, err = chat.run_tool("search", {"query": "שמים", "video_id": "a1"})
    assert not err and "[0:10] ויקרא אלהים לרקיע שמים" in text
    assert chat.run_tool("search", {"query": "nothing-like-this"})[0].startswith("Nothing in the library")

    monkeypatch.setattr(chat, "PART", 40)
    text, err = chat.run_tool("transcript", {"video_id": "a1"})
    assert "Title: בריאת הרקיע" in text and "[0:00] ויאמר" in text and "from_seconds=10" in text
    text, _ = chat.run_tool("transcript", {"video_id": "a1", "from_seconds": 10, "to_seconds": 15})
    assert "[0:10]" in text and "[0:20]" not in text and "continues" not in text

    text, err = chat.run_tool("videos", {"source_id": 1, "limit": 2})
    assert "3 videos match; 2 shown" in text and text.index("a1") < text.index("a2")
    assert "a3" in chat.run_tool("videos", {"oldest_first": True, "limit": 1})[0]

    assert chat.run_tool("search", {})[1]                                  # query is required
    assert chat.run_tool("search", {"query": 5})[1]
    assert chat.run_tool("transcript", {"video_id": "nope"}) == ("no video with id nope", True)
    assert chat.run_tool("videos", {"limit": "lots"})[1]
    assert chat.run_tool("rm", {})[1] and chat.run_tool("videos", ["x"])[1]


def test_settings(db):
    assert chat.settings()["engine"] == "off" and not chat.allowed(OWNER, False)
    chat.set_settings(engine="api")
    assert not chat.settings()["ready"] and not chat.allowed(OWNER, False)      # no key yet
    with pytest.raises(chat.Refused):
        chat.set_settings(api_key="not a key")
    with pytest.raises(chat.Refused):
        chat.set_settings(model="gpt")
    s = chat.set_settings(api_key=" sk-ant-api03-" + "x" * 30 + "WXYZ ")
    assert s["ready"] and s["api_key"] == "…WXYZ" and "sk-ant" not in json.dumps(s)
    assert (chat.config.DATA / "chat.json").stat().st_mode & 0o777 == 0o600
    assert chat.allowed(OWNER, False) and chat.allowed(None, True) and not chat.allowed(GUEST, False)
    chat.set_settings(everyone=True)
    assert chat.allowed(GUEST, False) and not chat.allowed(None, False)
    chat.set_settings(engine="claude")
    assert not chat.settings()["ready"]                                        # the token is separate
    chat.set_settings(api_key="")
    assert chat.settings()["api_key"] is None


def test_chats(db):
    c = chat.new_chat("me", video_id="a1")
    ctx = db.execute("select context from chat where id=?", (c["id"],)).fetchone()[0]
    assert "This chat is about one video" in ctx and "[0:10] ויקרא אלהים לרקיע שמים" in ctx
    assert "- 1 · https://a · Hebrew · 3 ·" in ctx
    assert c["video"]["title"] == "בריאת הרקיע · שיעור 3" and chat.chats("me") == []   # untitled until asked
    with pytest.raises(chat.Refused):
        chat.get_chat("someone-else", c["id"])
    with pytest.raises(chat.Refused):
        chat.new_chat("me", video_id="nope")
    s = chat.new_chat("me", source_id=2)
    assert "source_id 2" in db.execute("select context from chat where id=?", (s["id"],)).fetchone()[0]
    chat.delete_chat("me", s["id"])
    with pytest.raises(chat.Refused):
        chat.get_chat("me", s["id"])


class FakeStream:
    def __init__(self, texts, final):
        self.texts, self.final = texts, final

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def _gen(self):
        for t in self.texts:
            yield NS(type="text", text=t)

    def __aiter__(self):
        return self._gen()

    async def get_final_message(self):
        return self.final


def usage():
    return NS(input_tokens=1000, output_tokens=100, cache_creation_input_tokens=0, cache_read_input_tokens=0)


def test_answer_with_api_key(db, monkeypatch):
    chat.set_settings(engine="api", api_key="sk-ant-api03-" + "x" * 30)
    script = [
        (["Let me look."], NS(stop_reason="tool_use", usage=usage(), content=[
            NS(type="text", text="Let me look."), NS(type="tool_use", id="tu1", name="search", input={"query": "רקיע"})])),
        (["It's in ", "[0:10](#a1@0:10)."], NS(stop_reason="end_turn", usage=usage(), content=[
            NS(type="text", text="It's in [0:10](#a1@0:10).")])),
    ]
    calls = []

    class Client:
        def __init__(self, **kw):
            assert kw["api_key"].startswith("sk-ant-api03-")
            self.beta = NS(messages=NS(stream=self.stream))

        def stream(self, **kw):
            calls.append({**kw, "messages": list(kw["messages"])})
            return FakeStream(*script.pop(0))

    monkeypatch.setattr(anthropic, "AsyncAnthropic", Client)
    c = chat.new_chat(OWNER["email"])
    out = run(chat.answer(OWNER["email"], *chat.start(OWNER["email"], c["id"], "Where is the רקיע named?", True)))
    kinds = [k for k, _ in out]
    assert kinds == ["start", "text", "tool", "text", "text", "done"]
    assert out[2][1] == {"what": "search", "arg": "רקיע"}
    done = out[-1][1]
    assert done["text"] == "It's in [0:10](#a1@0:10)." and list(done["refs"]) == ["a1"]

    first, second = calls
    assert first["model"] == "claude-sonnet-5-5" and first["fallbacks"] == "default"
    assert first["cache_control"] == {"type": "ephemeral"} and all(t["eager_input_streaming"] for t in first["tools"])
    assert "tool_choice" not in first
    assert first["messages"][0]["content"][1]["text"] == "Where is the רקיע named?"
    results = second["messages"][-1]["content"]
    assert results[0]["tool_use_id"] == "tu1" and "a1 · בריאת הרקיע" in results[0]["content"]

    saved = chat.get_chat(OWNER["email"], c["id"])
    assert [m["role"] for m in saved["messages"]] == ["user", "assistant"]
    assert saved["title"] == "Where is the רקיע named?" and chat.chats(OWNER["email"])[0]["id"] == c["id"]
    assert chat.settings()["month"]["answers"] == 1 and chat.settings()["month"]["cost"] == pytest.approx(0.006)

    # The next question sends the first exchange back as plain text, after the same context.
    script.append(([" Yes."], NS(stop_reason="end_turn", usage=usage(), content=[NS(type="text", text="Yes.")])))
    run(chat.answer(OWNER["email"], *chat.start(OWNER["email"], c["id"], "Sure?", True)))
    msgs = calls[-1]["messages"]
    assert msgs[0]["content"][0]["text"] == first["messages"][0]["content"][0]["text"]
    assert msgs[1] == {"role": "assistant", "content": "It's in [0:10](#a1@0:10)."} and msgs[2]["content"] == "Sure?"


def test_errors_and_limits(db, monkeypatch):
    chat.set_settings(engine="api", api_key="sk-ant-api03-" + "x" * 30, everyone=True)

    async def failing(*a):
        yield ("text", "half an ans")
        yield ("error", "key")

    monkeypatch.setattr(chat, "_via_api", failing)
    c = chat.new_chat(GUEST["email"])
    out = run(chat.answer(GUEST["email"], *chat.start(GUEST["email"], c["id"], "q", False)))
    assert ("error", {"code": "key"}) in out and out[-1][1]["text"] == "half an ans"      # what came is kept

    with pytest.raises(chat.Refused, match="empty"):
        chat.start(GUEST["email"], c["id"], "  ", False)
    chat._running[GUEST["email"]] = flag = {"stop": False}
    chat.start(GUEST["email"], c["id"], "q", False)                 # a new question stops the one before
    assert flag["stop"]
    chat._running.clear()
    db.executemany("insert into chat_msg(chat_id, role, text, at) values (?, 'user', 'q', strftime('%s','now'))",
                   [(c["id"],)] * chat.PER_DAY)
    with pytest.raises(chat.Refused, match="day"):
        chat.start(GUEST["email"], c["id"], "q", False)
    chat.start(OWNER["email"], chat.new_chat(OWNER["email"])["id"], "q", True)        # not the owner
    chat.forget(GUEST["email"])
    assert chat.chats(GUEST["email"]) == []
