"""Accounts: an email on the list, a username, and a code by email. No passwords.

The owner puts addresses on the list (Library → People, as the owner or from the tailnet, or the
CLI below). The first address on the list is the owner's. An address on the list can ask for a
six-digit code from support@; the first time, the code comes back with a username of their
choosing and that makes the account. After that the username or the address both work.

/data/accounts.json (600): the cookie secret and the people. Codes are kept in memory only.
- A code works for 10 minutes and 5 tries.
- Codes: 6 per IP address an hour, 3 to one address every 15 minutes and 8 a day, 100 an hour in all.
- 20 wrong codes from one IP address in an hour, and it waits.
Removing someone signs them out everywhere, and adding them back doesn't revive an old cookie.

  docker exec -it tamlil-web python -m tamlil.accounts list
  docker exec -it tamlil-web python -m tamlil.accounts allow EMAIL [--quiet]   (--quiet: no invite)
  docker exec -it tamlil-web python -m tamlil.accounts remove EMAIL
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
import time

from . import config, mail

COOKIE = "tamlil"
DAYS = 180
CODE_SECONDS = 600
CODE_TRIES = 5
USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{1,31}$")
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")

_lock = threading.Lock()
_codes: dict[str, dict] = {}      # email -> {hash, exp, tries}
_hits: dict[str, list[float]] = {}


class Refused(Exception):
    """A short reason the app turns into a message: not-on-list, throttled, mail, wrong,
    expired, username, taken, need-username, owner, email."""


# ---------- the file ----------

def _path():
    return config.DATA / "accounts.json"


def _read() -> dict:
    try:
        return json.loads(_path().read_text())
    except (OSError, ValueError):
        return {"secret": None, "people": []}


def _write(d: dict) -> None:
    _path().parent.mkdir(parents=True, exist_ok=True)
    tmp = _path().with_suffix(".tmp")
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump(d, f, indent=1)
    tmp.replace(_path())


def _public(p: dict) -> dict:
    return {k: p.get(k) for k in ("email", "username", "owner", "added", "joined")}


def clean_email(s) -> str:
    return str(s or "").strip().lower()


def _find(d: dict, who: str):
    who = clean_email(who)
    key = "email" if "@" in who else "username"
    return next((p for p in d["people"] if who and p.get(key) == who), None)


def people() -> list[dict]:
    return [_public(p) for p in _read()["people"]]


def mask(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:1]}•••@{domain}"


# ---------- the list ----------

def allow(email: str, invite: bool = True) -> dict:
    """Put an address on the list (the first one is the owner). Returns {"invited": bool}."""
    email = clean_email(email)
    if not EMAIL.match(email):
        raise Refused("email")
    with _lock:
        d = _read()
        if not d.get("secret"):
            d["secret"] = secrets.token_hex(32)
        if _find(d, email):
            raise Refused("exists")
        d["people"].append({"email": email, "username": None, "owner": not d["people"],
                            "added": int(time.time()), "joined": None, "key": secrets.token_hex(8)})
        _write(d)
    invited = False
    if invite:
        invited = mail.send(email, "You're invited to Tamlil", INVITE.format(url=config.PUBLIC_URL, signature=config.SIGNATURE))
    return {"invited": invited}


def remove(email: str) -> None:
    email = clean_email(email)
    with _lock:
        d = _read()
        p = _find(d, email)
        if not p:
            raise Refused("not-on-list")
        if p.get("owner") and sum(1 for x in d["people"] if x.get("owner")) == 1:
            raise Refused("owner")
        d["people"] = [x for x in d["people"] if x is not p]
        _write(d)
    _codes.pop(email, None)


# ---------- codes ----------

def _limited(key: str, most: int, seconds: float) -> bool:
    now = time.time()
    _hits[key] = [t for t in _hits.get(key, []) if now - t < seconds]
    return len(_hits[key]) >= most


def _hit(*keys: str) -> None:
    now = time.time()
    for k in keys:
        _hits.setdefault(k, []).append(now)


def _sha(email: str, code: str) -> str:
    return hashlib.sha256(f"{email}:{code}".encode()).hexdigest()


def send_code(who: str, ip: str) -> dict:
    """Email a code to whoever `who` is (an address or a username). Returns where it went,
    masked, and whether they still need to pick a username."""
    with _lock:
        if (_limited(f"ip:{ip}", 6, 3600) or _limited("all", 100, 3600)):
            raise Refused("throttled")
        _hit(f"ip:{ip}", "all")            # unknown names count too, so nobody can fish for addresses
        p = _find(_read(), who)
        if not p:
            raise Refused("not-on-list")
        email = p["email"]
        if _limited(f"to:{email}", 3, 900) or _limited(f"day:{email}", 8, 86400):
            raise Refused("throttled")
        _hit(f"to:{email}", f"day:{email}")
        if len(_codes) > 1000:
            for k in [k for k, c in _codes.items() if c["exp"] < time.time()]:
                _codes.pop(k, None)
        code = f"{secrets.randbelow(10 ** 6):06d}"
        _codes[email] = {"hash": _sha(email, code), "exp": time.time() + CODE_SECONDS, "tries": 0}
    text = CODE.format(code=f"{code[:3]} {code[3:]}", url=config.PUBLIC_URL)
    if not mail.send(email, f"{code} is your Tamlil code", text):
        _codes.pop(email, None)
        raise Refused("mail")
    return {"to": mask(email), "new": not p.get("username")}


def sign_in(who: str, code: str, username: str | None, ip: str) -> str:
    """Check the code; the first time, take the username too. Returns the cookie."""
    with _lock:
        if _limited(f"bad:{ip}", 20, 3600):
            raise Refused("throttled")
        d = _read()
        p = _find(d, who)
        c = _codes.get(p["email"]) if p else None
        if not c or c["exp"] < time.time():
            raise Refused("expired")
        if not hmac.compare_digest(c["hash"], _sha(p["email"], re.sub(r"\D", "", str(code or "")))):
            _hit(f"bad:{ip}")
            c["tries"] += 1
            if c["tries"] >= CODE_TRIES:
                _codes.pop(p["email"], None)
            raise Refused("wrong")
        if not p.get("username"):
            name = clean_email(username)
            if not name:
                raise Refused("need-username")      # the code stays good for the second try
            if not USERNAME.match(name):
                raise Refused("username")
            if any(x.get("username") == name for x in d["people"]):
                raise Refused("taken")
            p["username"], p["joined"] = name, int(time.time())
            _write(d)
        _codes.pop(p["email"], None)
        return _cookie(d, p)


# ---------- the cookie: key.expiry.username.signature (a username can have dots) ----------

def _cookie(d: dict, p: dict) -> str:
    body = f"{p['key']}.{int(time.time()) + DAYS * 86400}.{p['username']}"
    return body + "." + hmac.new(bytes.fromhex(d["secret"]), body.encode(), "sha256").hexdigest()


def who(value: str | None) -> dict | None:
    """The person a cookie belongs to (with "renew": True once it's a day old), or None."""
    if not value or value.count(".") < 3:
        return None
    d = _read()
    if not d.get("secret"):
        return None
    body, sig = value.rsplit(".", 1)
    good = hmac.new(bytes.fromhex(d["secret"]), body.encode(), "sha256").hexdigest()
    if not hmac.compare_digest(sig, good):
        return None
    key, exp, name = body.split(".", 2)
    p = next((x for x in d["people"] if x.get("username") == name and x.get("key") == key), None)
    if not p or not exp.isdigit() or int(exp) < time.time():
        return None
    return {**_public(p), "renew": int(exp) < time.time() + (DAYS - 1) * 86400}


def renew(value: str) -> str | None:
    p = who(value)
    if not p:
        return None
    d = _read()
    return _cookie(d, next(x for x in d["people"] if x.get("username") == p["username"]))


CODE = """Hi,

Your code for signing in to Tamlil is:

    {code}

It works for 10 minutes. If you didn't ask for it, you can ignore this email: nobody gets in without the code.

Tamlil
{url}
"""

INVITE = """Hi,

I added you to Tamlil, which is a little app I made that searches what's said in a few YouTube channels, in Hebrew and English, and plays the video right from that moment.

To sign in, go to {url} and type this email address. You'll get a code by email, and the first time you'll also pick a username. That's it, no password to remember.

If anything doesn't work, just reply to this email and let me know.

{signature}
"""


def main(argv: list[str]) -> int:
    cmd, rest = (argv[0] if argv else "list"), argv[1:]
    try:
        if cmd == "list":
            for p in people():
                print(f"{p['email']:<36} {p['username'] or '-':<20} {'owner' if p['owner'] else ''}")
        elif cmd == "allow" and rest:
            r = allow(rest[0], invite="--quiet" not in rest)
            print("Added." + (" Invite sent." if r["invited"] else ""))
        elif cmd == "remove" and rest:
            remove(rest[0])
            print("Removed, and signed out everywhere.")
        else:
            print(__doc__.split("\n\n")[-1])
            return 2
    except Refused as e:
        print({"email": "That email looks off.", "exists": "Already on the list.",
               "not-on-list": "Not on the list.", "owner": "That's the only owner."}.get(str(e), str(e)))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
