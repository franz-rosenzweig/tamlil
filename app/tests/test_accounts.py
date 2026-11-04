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
