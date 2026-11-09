import asyncio
import json
import threading
import time
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
    chat._lists.clear()


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
    assert chat.settings()["on"] is False and not chat.allowed(OWNER, False)
    with pytest.raises(chat.Refused):
        chat.add_connection(preset="openrouter")                               # it needs a key
    with pytest.raises(chat.Refused):
        chat.add_connection(preset="anthropic", api_key="not a key")
    with pytest.raises(chat.Refused):
        chat.add_connection(preset="custom", base_url="ftp://x")
    with pytest.raises(chat.Refused):
        chat.add_connection(preset="nope")
    s = chat.add_connection(preset="anthropic", api_key=" sk-ant-api03-" + "x" * 30 + "WXYZ ")
    assert s["added"] == 1 and s["model"] == "1/claude-sonnet-5-5" and s["model_label"] == "Sonnet 5.5 · Claude"
    assert s["connections"][0]["key"] == "…WXYZ" and "sk-ant" not in json.dumps(s)
    assert not s["ready"] and not chat.allowed(OWNER, False)                  # still off
    assert (chat.config.DATA / "chat.json").stat().st_mode & 0o777 == 0o600
    s = chat.set_settings(on=True)
    assert s["ready"] and chat.allowed(OWNER, False) and chat.allowed(None, True) and not chat.allowed(GUEST, False)
    chat.set_settings(everyone=True)
    assert chat.allowed(GUEST, False) and not chat.allowed(None, False)

    s = chat.add_connection(preset="ollama", name="  My   box ")
    assert s["added"] == 2 and s["model"] == "1/claude-sonnet-5-5"           # a second one doesn't change the model
    assert s["connections"][1] == {"id": 2, "preset": "ollama", "name": "My box", "key": None,
                                   "base_url": "http://host.docker.internal:11434/v1"}
    with pytest.raises(chat.Refused):
        chat.set_settings(model="9/llama")                                     # no such connection
    with pytest.raises(chat.Refused):
        chat.set_settings(model="2/has space")
    s = chat.set_settings(model="2/llama3.3:70b", model_name="Llama 3.3")
    assert s["ready"] and s["model_label"] == "Llama 3.3 · My box"
    s = chat.edit_connection(2, base_url="http://10.0.0.5:11434/v1/", name="")
    assert s["connections"][1]["base_url"] == "http://10.0.0.5:11434/v1" and s["connections"][1]["name"] == "Ollama"
    s = chat.edit_connection(1, api_key="")                                      # an empty key keeps the one there
    assert s["connections"][0]["key"] == "…WXYZ"
    s = chat.delete_connection(2)
    assert s["model"] == "" and not s["ready"] and not chat.allowed(OWNER, False) and len(s["connections"]) == 1


def test_old_settings_carry_over(db):
    token = "sk-ant-oat01-" + "t" * 40
    (chat.config.DATA / "chat.json").write_text(json.dumps(
        {"engine": "off", "api_key": "", "token": token, "model": "claude-opus-5-5", "everyone": True}))
    s = chat.settings()
    assert s["connections"] == [{"id": 1, "preset": "claude_code", "name": "Claude Code", "key": "…tttt", "base_url": ""}]
    assert s["model"] == "1/claude-opus-5-5" and s["everyone"] and not s["on"]
    conn, model = chat._usable({**chat._read(), "on": True})
    assert conn["api_key"] == token and model == "claude-opus-5-5"
    (chat.config.DATA / "chat.json").write_text(json.dumps(
        {"engine": "api", "api_key": "sk-ant-api03-" + "k" * 30, "token": token, "model": "claude-sonnet-5-5"}))
    s = chat.settings()
    assert [c["preset"] for c in s["connections"]] == ["claude_code", "anthropic"] and s["model"] == "2/claude-sonnet-5-5"
    assert s["on"] and s["ready"]


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
    chat.add_connection(preset="anthropic", api_key="sk-ant-api03-" + "x" * 30)
    chat.set_settings(on=True)
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
    chat.add_connection(preset="anthropic", api_key="sk-ant-api03-" + "x" * 30)
    chat.set_settings(on=True, everyone=True)

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
    chat._lists.clear()
    db.executemany("insert into chat_msg(chat_id, role, text, at) values (?, 'user', 'q', strftime('%s','now'))",
                   [(c["id"],)] * chat.PER_DAY)
    with pytest.raises(chat.Refused, match="day"):
        chat.start(GUEST["email"], c["id"], "q", False)
    chat.start(OWNER["email"], chat.new_chat(OWNER["email"])["id"], "q", True)        # not the owner
    chat.forget(GUEST["email"])
    assert chat.chats(GUEST["email"]) == []


# ---------- the OpenAI chat format (OpenRouter and the rest), against a stand-in ----------

import httpx  # noqa: E402


def sse(*chunks) -> bytes:
    return "".join(f"data: {json.dumps(c, ensure_ascii=False)}\n\n" for c in chunks).encode() + b"data: [DONE]\n\n"


def stand_in(monkeypatch, handler):
    monkeypatch.setattr(chat, "_transport", httpx.MockTransport(handler))


def test_models_listed(db, monkeypatch):
    chat.add_connection(preset="openrouter", api_key="sk-or-v1-" + "o" * 40)
    chat.add_connection(preset="gemini", api_key="AIza" + "g" * 30)
    chat.add_connection(preset="claude_code", api_key="sk-ant-oat01-" + "t" * 40)
    asked = []

    def handler(req):
        asked.append((str(req.url), req.headers.get("authorization"), req.headers.get("x-title")))
        if "openrouter" in str(req.url):
            return httpx.Response(200, json={"data": [
                {"id": "b/thinks", "name": "B: Thinks", "supported_parameters": ["tools", "reasoning"],
                 "reasoning": {"supported_efforts": ["low", "high"]}},
                {"id": "a/plain", "name": "A: Plain", "supported_parameters": ["tools"]},
                {"id": "c/no-tools", "name": "C", "supported_parameters": ["temperature"]}]})
        if req.headers.get("authorization") == "Bearer AIza" + "g" * 30:
            return httpx.Response(200, json={"data": [{"id": "models/gemini-x"}]})
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    stand_in(monkeypatch, handler)
    got = asyncio.run(chat.models(1))
    assert [m["id"] for m in got] == ["a/plain", "b/thinks"] and got[0]["reasoning"] is None
    assert asked[0] == ("https://openrouter.ai/api/v1/models", "Bearer sk-or-v1-" + "o" * 40, "Tamlil")
    assert asyncio.run(chat.models(1)) is got and len(asked) == 1                 # kept for an hour
    assert asyncio.run(chat.models(2)) == [{"id": "gemini-x", "name": "gemini-x"}]
    assert [m["id"] for m in asyncio.run(chat.models(3))] == list(chat.MODELS)
    chat.edit_connection(2, api_key="AIza" + "w" * 30)
    with pytest.raises(chat.Refused, match="key"):
        asyncio.run(chat.models(2))


def test_answer_through_openrouter(db, monkeypatch):
    chat.add_connection(preset="openrouter", api_key="sk-or-v1-" + "o" * 40)
    chat.set_settings(on=True, model="1/b/thinks", model_name="B: Thinks")
    chat._lists[1] = (time.time(), [{"id": "b/thinks", "name": "B: Thinks", "reasoning": {"supported_efforts": ["low", "high"]}}])
    bodies = []
    rounds = [
        sse({"choices": [{"delta": {"content": "Let me look.", "reasoning_details": [{"type": "reasoning.text", "text": "Think", "index": 0}]}}]},
            {"choices": [{"delta": {"reasoning_details": [{"type": "reasoning.text", "text": "ing", "signature": "sig", "index": 0}],
                                    "tool_calls": [{"index": 0, "id": "c1", "type": "function", "function": {"name": "search", "arguments": '{"que'}}]}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": 'ry": "רקיע"}'}}]}, "finish_reason": "tool_calls"}]},
            {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.002}}),
        sse({"choices": [{"delta": {"content": "It's in "}}]},
            {"choices": [{"delta": {"content": "[0:10](#a1@0:10)."}, "finish_reason": "stop"}], "usage": {"cost": 0.003}}),
    ]

    def handler(req):
        bodies.append(json.loads(req.content))
        assert str(req.url) == "https://openrouter.ai/api/v1/chat/completions"
        return httpx.Response(200, content=rounds.pop(0), headers={"content-type": "text/event-stream"})

    stand_in(monkeypatch, handler)
    c = chat.new_chat(OWNER["email"])
    out = run(chat.answer(OWNER["email"], *chat.start(OWNER["email"], c["id"], "Where is the רקיע named?", True)))
    assert [k for k, _ in out] == ["start", "text", "tool", "text", "text", "done"]
    assert out[2][1] == {"what": "search", "arg": "רקיע"} and out[-1][1]["text"] == "It's in [0:10](#a1@0:10)."

    first, second = bodies
    assert first["model"] == "b/thinks" and first["stream"] and first["reasoning"] == {"effort": "high"}
    assert first["stream_options"] == {"include_usage": True} and "tool_choice" not in first
    assert [t["function"]["name"] for t in first["tools"]] == ["search", "transcript", "videos"]
    assert "additionalProperties" not in first["tools"][0]["function"]["parameters"]
    assert first["messages"][0]["role"] == "system" and "library's channels" in first["messages"][0]["content"]
    assert first["messages"][1] == {"role": "user", "content": "Where is the רקיע named?"}
    said, result = second["messages"][2], second["messages"][3]
    assert said["tool_calls"] == [{"id": "c1", "type": "function", "function": {"name": "search", "arguments": '{"query": "רקיע"}'}}]
    assert said["content"] == "Let me look." and said["reasoning_details"] == [
        {"type": "reasoning.text", "text": "Thinking", "signature": "sig", "index": 0}]
    assert result["role"] == "tool" and result["tool_call_id"] == "c1" and "a1 · בריאת הרקיע" in result["content"]

    row = db.execute("select engine, model, cost from chat_msg where role='assistant'").fetchone()
    assert (row["engine"], row["model"]) == ("openrouter", "b/thinks") and row["cost"] == pytest.approx(0.005)


def test_openai_format_turned_down(db, monkeypatch):
    chat.add_connection(preset="custom", base_url="http://llm.local/v1")
    chat.set_settings(on=True, model="1/small")
    bodies, replies = [], [
        httpx.Response(400, json={"error": {"message": "unknown field stream_options"}}),
        httpx.Response(200, content=sse({"choices": [{"delta": {"content": "Hi."}, "finish_reason": "stop"}]})),
        httpx.Response(404, json={"error": {"message": "No endpoints found that support tool use"}}),
    ]

    def handler(req):
        bodies.append(json.loads(req.content))
        assert "authorization" not in req.headers
        return replies.pop(0)

    stand_in(monkeypatch, handler)
    c = chat.new_chat(OWNER["email"])
    out = run(chat.answer(OWNER["email"], *chat.start(OWNER["email"], c["id"], "Hello", True)))
    assert out[-1][1]["text"] == "Hi." and "stream_options" in bodies[0] and "stream_options" not in bodies[1]
    out = run(chat.answer(OWNER["email"], *chat.start(OWNER["email"], c["id"], "Again", True)))
    assert ("error", {"code": "tools"}) in out


# ---------- a ChatGPT plan, against a stand-in for OpenAI ----------

from urllib.parse import parse_qs, urlparse  # noqa: E402

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

from tamlil import chatgpt  # noqa: E402

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
JWK = {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key())), "kid": "k1"}


class FakeOpenAI:
    def __init__(self):
        self.nonce, self.bodies, self.rounds, self.expired = None, [], [], False

    def __call__(self, req):
        url = str(req.url)
        if url.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json={"issuer": "https://auth.openai.com", "jwks_uri": "https://auth.openai.com/jwks",
                                             "revocation_endpoint": "https://auth.openai.com/revoke"})
        if url.endswith("/jwks"):
            return httpx.Response(200, json={"keys": [JWK]})
        if url.endswith("/oauth/token"):
            form = parse_qs(req.content.decode())
            if form["grant_type"] == ["authorization_code"]:
                assert form["redirect_uri"] == ["http://127.0.0.1:8445/auth/callback"]
                idt = jwt.encode({"iss": "https://auth.openai.com", "aud": "oaiapp_1", "sub": "u1", "email": "a@b.c",
                                  "nonce": self.nonce, "exp": time.time() + 600}, KEY, algorithm="RS256", headers={"kid": "k1"})
                return httpx.Response(200, json={"id_token": idt, "access_token": "at-1", "refresh_token": "rt-1",
                                                 "expires_in": 3600, "scope": chatgpt.SCOPES})
            return httpx.Response(200, json={"access_token": "at-2", "refresh_token": "rt-2", "expires_in": 3600})
        if url.endswith("/v1/models"):
            return httpx.Response(200, json={"models": [{"slug": "gpt-x", "display_name": "GPT X"},
                                                       {"slug": "hidden", "visibility": "hide"}]})
        if url.endswith("/v1/responses"):
            if self.expired:
                self.expired = False
                return httpx.Response(401, json={"error": {"message": "expired"}})
            self.bodies.append((req.headers["authorization"], json.loads(req.content)))
            events = self.rounds.pop(0)
            return httpx.Response(200, content="".join(f"event: {e['type']}\ndata: {json.dumps(e, ensure_ascii=False)}\n\n"
                                                       for e in events).encode(), headers={"content-type": "text/event-stream"})
        if url.endswith("/revoke"):
            return httpx.Response(200)
        return httpx.Response(404)


def test_chatgpt_sign_in_and_answer(db, monkeypatch):
    fake = FakeOpenAI()
    t = httpx.MockTransport(fake)
    monkeypatch.setattr(chatgpt, "_transport", t)
    monkeypatch.setattr(chat, "_transport", t)
    with pytest.raises(chat.Refused):
        chat.add_connection(preset="chatgpt")                        # only through the sign-in
    q = {k: v[0] for k, v in parse_qs(urlparse(chatgpt.start()).query).items()}
    assert q["client_id"] == "dynamic_agent_client" and q["agent_name_hint"] == "Tamlil" and q["ext_agent_host_id"]
    assert q["redirect_uri"] == "http://127.0.0.1:8445/auth/callback" and "chatgpt.tokens.use.direct" in q["scope"]
    fake.nonce = q["nonce"]
    with pytest.raises(chatgpt.SignInError, match="state"):
        asyncio.run(chatgpt.finish(chatgpt.parse_callback("http://127.0.0.1:8445/auth/callback?code=c&state=nope")))
    asyncio.run(chatgpt.finish(chatgpt.parse_callback(
        f"http://127.0.0.1:8445/auth/callback?code=c&state={q['state']}&client_id=oaiapp_1")))
    assert (chat.config.DATA / "chatgpt.json").stat().st_mode & 0o777 == 0o600
    s = chat.chatgpt_signed_in()
    assert s["connections"] == [{"id": 1, "preset": "chatgpt", "name": "ChatGPT", "key": "a@b.c", "base_url": ""}]
    assert chat.chatgpt_signed_in()["added"] == 1 and len(chat.settings()["connections"]) == 1      # made once
    assert asyncio.run(chat.models(1)) == [{"id": "gpt-x", "name": "GPT X"}]
    q2 = {k: v[0] for k, v in parse_qs(urlparse(chatgpt.start()).query).items()}
    assert q2["client_id"] == "oaiapp_1" and "agent_name_hint" not in q2 and q2["login_hint"] == "a@b.c"

    chat.set_settings(on=True, model="1/gpt-x")
    call = {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "search", "arguments": '{"query": "רקיע"}'}
    thought = {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "enc"}
    fake.rounds = [
        [{"type": "response.output_item.done", "item": thought}, {"type": "response.output_item.done", "item": call},
         {"type": "response.completed", "response": {"output": [thought, call]}}],
        [{"type": "response.output_text.delta", "delta": "It's in "}, {"type": "response.output_text.delta", "delta": "[0:10](#a1@0:10)."},
         {"type": "response.completed", "response": {}}],
    ]
    fake.expired = True                                                # the first try finds the token run out
    c = chat.new_chat(OWNER["email"])
    out = run(chat.answer(OWNER["email"], *chat.start(OWNER["email"], c["id"], "Where?", True)))
    assert [k for k, _ in out] == ["start", "tool", "text", "text", "done"] and out[-1][1]["text"] == "It's in [0:10](#a1@0:10)."
    (auth1, first), (auth2, second) = fake.bodies
    assert auth1 == auth2 == "Bearer at-2" and chatgpt.load()["refresh_token"] == "rt-2"
    assert first["store"] is False and first["stream"] and first["include"] == ["reasoning.encrypted_content"]
    assert first["input"] == [{"role": "user", "content": "Where?"}] and "library's channels" in first["instructions"]
    assert [t["name"] for t in first["tools"]] == ["search", "transcript", "videos"] and first["tool_choice"] == "auto"
    back = second["input"]
    assert back[1] == {"type": "reasoning", "summary": [], "encrypted_content": "enc"}           # whole, without its id
    assert back[2] == {k: v for k, v in call.items() if k != "id"}
    assert back[3]["type"] == "function_call_output" and back[3]["call_id"] == "call_1" and "a1 · בריאת הרקיע" in back[3]["output"]

    assert asyncio.run(chatgpt.disconnect()) is True and chatgpt.load() is None
    assert not chat.settings()["ready"]
