import importlib
import json
import re

import pytest

from tamlil import config


@pytest.fixture
def acc(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA", tmp_path)
    monkeypatch.setenv("TAMLIL_MAIL", "outbox")
    from tamlil import accounts
    importlib.reload(accounts)
    return accounts


def last_code(tmp_path):
    lines = (tmp_path / "outbox.jsonl").read_text().splitlines()
    return re.search(r"(\d{3}) (\d{3})", json.loads(lines[-1])["text"]).group(0)


def test_list_invite_and_owner(acc, tmp_path):
    assert acc.allow("Owner@Example.com")["invited"]
    acc.allow("friend@example.com", invite=False)
    ppl = acc.people()
    assert [p["email"] for p in ppl] == ["owner@example.com", "friend@example.com"]
    assert ppl[0]["owner"] and not ppl[1]["owner"]
    assert len((tmp_path / "outbox.jsonl").read_text().splitlines()) == 1
    with pytest.raises(acc.Refused, match="exists"):
        acc.allow("owner@example.com")
    with pytest.raises(acc.Refused, match="email"):
        acc.allow("not an email")
    with pytest.raises(acc.Refused, match="owner"):
        acc.remove("owner@example.com")


def test_first_code_makes_the_account(acc, tmp_path):
    acc.allow("a@example.com", invite=False)
    with pytest.raises(acc.Refused, match="not-on-list"):
        acc.send_code("stranger@example.com", "1.1.1.1")
    r = acc.send_code("A@example.com", "1.1.1.1")
    assert r == {"to": "a•••@example.com", "new": True}
    code = last_code(tmp_path)
    with pytest.raises(acc.Refused, match="need-username"):
        acc.sign_in("a@example.com", code, None, "1.1.1.1")
    with pytest.raises(acc.Refused, match="username"):
        acc.sign_in("a@example.com", code, "x", "1.1.1.1")
    cookie = acc.sign_in("a@example.com", code, "Ari.B", "1.1.1.1")   # the code survived both
    assert acc.who(cookie)["username"] == "ari.b"
    with pytest.raises(acc.Refused, match="expired"):                 # and is used up now
        acc.sign_in("a@example.com", code, None, "1.1.1.1")
    # next time: by username, no username needed
    assert acc.send_code("ari.b", "1.1.1.1")["new"] is False
    assert acc.who(acc.sign_in("ari.b", last_code(tmp_path), None, "1.1.1.1"))["email"] == "a@example.com"


def test_usernames_are_unique(acc, tmp_path):
    acc.allow("a@example.com", invite=False)
    acc.allow("b@example.com", invite=False)
    acc.send_code("a@example.com", "1")
    acc.sign_in("a@example.com", last_code(tmp_path), "same", "1")
    acc.send_code("b@example.com", "1")
    with pytest.raises(acc.Refused, match="taken"):
        acc.sign_in("b@example.com", last_code(tmp_path), "same", "1")


def test_wrong_codes(acc, tmp_path):
    acc.allow("a@example.com", invite=False)
    acc.send_code("a@example.com", "1")
    good = last_code(tmp_path)
    bad = "000 000" if good != "000 000" else "111 111"
    for _ in range(acc.CODE_TRIES):
        with pytest.raises(acc.Refused, match="wrong"):
            acc.sign_in("a@example.com", bad, "ana", "1")
    with pytest.raises(acc.Refused, match="expired"):                 # five wrong, and it's gone
        acc.sign_in("a@example.com", good, "ana", "1")


def test_code_limits(acc, tmp_path):
    acc.allow("a@example.com", invite=False)
    for _ in range(3):
        acc.send_code("a@example.com", "1")
    with pytest.raises(acc.Refused, match="throttled"):              # 3 to one address in 15 minutes
        acc.send_code("a@example.com", "2")
    for _ in range(3):
        with pytest.raises(acc.Refused):
            acc.send_code("nobody@example.com", "3")
    with pytest.raises(acc.Refused, match="throttled"):              # 6 from one IP an hour, known or not
        acc.send_code("a@example.com", "1")


def test_cookies(acc, tmp_path):
    acc.allow("owner@example.com", invite=False)
    acc.allow("a@example.com", invite=False)
    acc.send_code("a@example.com", "1")
    c = acc.sign_in("a@example.com", last_code(tmp_path), "ana", "1")
    assert acc.who(c) and not acc.who(c)["renew"]
    assert acc.who(c[:-1] + ("0" if c[-1] != "0" else "1")) is None
    assert acc.who("ana") is None and acc.who(None) is None
    acc.remove("a@example.com")
    assert acc.who(c) is None                                         # removed: signed out everywhere
    acc.allow("a@example.com", invite=False)
    acc.send_code("a@example.com", "1")
    acc.sign_in("a@example.com", last_code(tmp_path), "ana", "1")
    assert acc.who(c) is None                                         # back on the list: the old cookie stays dead


def outbox(tmp_path):
    return [json.loads(x) for x in (tmp_path / "outbox.jsonl").read_text().splitlines()]


def member(acc, tmp_path, email="a@example.com", username="ana"):
    acc.allow(email, invite=False)
    acc.send_code(email, "1")
    return acc.sign_in(email, last_code(tmp_path), username, "1")


def test_emails_have_html_and_text(acc, tmp_path):
    acc.allow("owner@example.com", name="<b>Dana Levi")
    m = outbox(tmp_path)[-1]
    assert "Hi <b>Dana," in m["text"] and "owner@example.com" in m["text"]
    assert m["html"].startswith("<!doctype html>") and "&lt;b&gt;Dana" in m["html"] and "<b>Dana" not in m["html"]
    acc.send_code("owner@example.com", "1")
    m = outbox(tmp_path)[-1]
    code = last_code(tmp_path).replace(" ", "")
    assert m["subject"] == f"{code} is your Tamlil code" and all(d in m["html"] for d in code)


def test_passwords(acc, tmp_path):
    acc.allow("owner@example.com", invite=False)
    c1 = member(acc, tmp_path)
    with pytest.raises(acc.Refused, match="login"):                   # no password yet
        acc.sign_in_password("ana", "whatever123", "1")
    with pytest.raises(acc.Refused, match="short"):
        acc.set_password("a@example.com", "short", None)
    c2 = acc.set_password("a@example.com", "correct horse", None)
    assert acc.who(c1) is None and acc.who(c2)["password"]          # a new password signs out everywhere else
    with pytest.raises(acc.Refused, match="current"):
        acc.set_password("a@example.com", "another one", "wrong")
    for who in ("ana", "A@Example.com"):
        assert acc.who(acc.sign_in_password(who, "correct horse", "1"))["username"] == "ana"
    with pytest.raises(acc.Refused, match="login"):
        acc.sign_in_password("ana", "wrong horse", "2")
    with pytest.raises(acc.Refused, match="current"):
        acc.remove_password("a@example.com", "nope")
    acc.remove_password("a@example.com", "correct horse")
    with pytest.raises(acc.Refused, match="login"):
        acc.sign_in_password("ana", "correct horse", "3")


def test_password_lockout(acc, tmp_path):
    acc.allow("owner@example.com", invite=False)
    member(acc, tmp_path)
    acc.set_password("a@example.com", "correct horse", None)
    for i in range(8):
        with pytest.raises(acc.Refused, match="login"):
            acc.sign_in_password("ana", "nope", f"ip{i}")
    with pytest.raises(acc.Refused, match="locked"):                  # even the right one, for 15 minutes
        acc.sign_in_password("ana", "correct horse", "elsewhere")


def test_username_change_keeps_you_signed_in(acc, tmp_path):
    acc.allow("owner@example.com", invite=False)
    c = member(acc, tmp_path)
    member(acc, tmp_path, "b@example.com", "bo")
    with pytest.raises(acc.Refused, match="taken"):
        acc.update("a@example.com", username="bo")
    acc.update("a@example.com", username="Ana.K", name="Ana K")
    assert acc.who(c)["username"] == "ana.k" and acc.who(c)["name"] == "Ana K"
    c2 = acc.sign_out_others("a@example.com")
    assert acc.who(c) is None and acc.who(c2)


def test_asking_for_an_invite(acc, tmp_path):
    acc.allow("owner@example.com", invite=False)
    member(acc, tmp_path, "b@example.com", "bo")
    with pytest.raises(acc.Refused, match="taken"):
        acc.ask(name="Avi", email="avi@example.com", username="bo", password=None, note=None, ip="9")
    assert acc.ask(name="Avi", email="avi@example.com", username="avi", password="tov meod 1", note="From shul", ip="9") == {"allowed": False}
    assert acc.requests() == []                                       # not until the code comes back
    with pytest.raises(acc.Refused, match="wrong"):
        acc.confirm("avi@example.com", "000 000" if last_code(tmp_path) != "000 000" else "111 111", "9")
    acc.confirm("avi@example.com", last_code(tmp_path), "9")
    note = outbox(tmp_path)[-1]
    assert note["to"] == "owner@example.com" and "Avi" in note["subject"] and "From shul" in note["text"]
    assert [r["username"] for r in acc.requests()] == ["avi"]
    with pytest.raises(acc.Refused, match="pending"):
        acc.send_code("avi@example.com", "9")
    with pytest.raises(acc.Refused, match="pending"):
        acc.sign_in_password("avi", "tov meod 1", "9")
    assert acc.approve("avi@example.com")["mailed"]
    assert outbox(tmp_path)[-1]["subject"] == "You're in! Welcome to Tamlil"
    assert acc.requests() == []
    assert acc.who(acc.sign_in_password("avi", "tov meod 1", "9"))["email"] == "avi@example.com"
    assert acc.ask(name="Avi", email="avi@example.com", username="x2", password=None, note=None, ip="9") == {"allowed": True}


def test_declining_and_closing(acc, tmp_path):
    acc.allow("owner@example.com", invite=False)
    acc.set_settings(notify=False)
    acc.ask(name="Z", email="z@example.com", username="zed", password=None, note=None, ip="5")
    acc.confirm("z@example.com", last_code(tmp_path), "5")
    assert outbox(tmp_path)[-1]["to"] == "z@example.com"                # the owner asked not to hear
    acc.decline("z@example.com")
    assert acc.requests() == []
    acc.set_settings(requests=False)
    with pytest.raises(acc.Refused, match="closed"):
        acc.ask(name="Z", email="z@example.com", username="zed", password=None, note=None, ip="5")
