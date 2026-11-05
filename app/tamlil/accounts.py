"""Accounts: an email on the list, a username, and a code by email or a password.

People get on the list two ways: the owner invites them (Settings → People, as the owner or from
the tailnet, or the CLI below), or they ask at /join and the owner says yes. The first address on
the list is the owner's. Signing in takes a six-digit code from support@ or, for anyone who set
one, a password. The first code also takes a username of their choosing (a request brings its own).

/data/accounts.json (600): the cookie secret, the people, the requests, and two settings.
Codes and half-finished requests are kept in memory only.
- A code works for 10 minutes and 5 tries (a request's code, 15 minutes).
- Codes: 6 per IP address an hour, 3 to one address every 15 minutes and 8 a day, 100 an hour in all.
- 20 wrong codes from one IP address in an hour, and it waits.
- Passwords: 12 tries from one IP address in 15 minutes, and 8 wrong for one login locks it for 15.
- Requests: 4 per IP address an hour, 3 for one address an hour, 30 a day, and 50 waiting at most.
Each person has a key in their cookie. Removing them, a new password, or "sign out everywhere
else" changes it, which ends every other sign-in at once.

  docker exec -it tamlil-web python -m tamlil.accounts list
  docker exec -it tamlil-web python -m tamlil.accounts allow EMAIL [--quiet]   (--quiet: no invite)
  docker exec -it tamlil-web python -m tamlil.accounts remove EMAIL
"""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
import time

from . import config, emails, mail

COOKIE = "tamlil"
DAYS = 180
CODE_SECONDS = 600
ASK_SECONDS = 900
CODE_TRIES = 5
USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{1,31}$")
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
PASSWORD_MIN = 8
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}

_lock = threading.Lock()
_codes: dict[str, dict] = {}      # email -> {hash, exp, tries}
_asking: dict[str, dict] = {}     # email -> a request, until its code comes back
_hits: dict[str, list[float]] = {}


class Refused(Exception):
    """A short reason the app turns into a message: not-on-list, pending, throttled, locked, mail,
    wrong, expired, username, taken, need-username, owner, email, exists, closed, name,
    short, long, current, login."""


# ---------- the file ----------

def _path():
    return config.DATA / "accounts.json"


def _read() -> dict:
    try:
        d = json.loads(_path().read_text())
    except (OSError, ValueError):
        d = {}
    d.setdefault("secret", None)
    d.setdefault("people", [])
    d.setdefault("requests", [])
    d.setdefault("settings", {})
    return d


def _write(d: dict) -> None:
    _path().parent.mkdir(parents=True, exist_ok=True)
    tmp = _path().with_suffix(".tmp")
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump(d, f, indent=1)
    tmp.replace(_path())


def _public(p: dict) -> dict:
    out = {k: p.get(k) for k in ("email", "username", "name", "owner", "added", "joined")}
    out["password"] = bool(p.get("pass"))
    return out


def clean_email(s) -> str:
    return str(s or "").strip().lower()


def _clip(s, n: int) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


def _find(d: dict, who: str):
    who = clean_email(who)
    key = "email" if "@" in who else "username"
    return next((p for p in d["people"] if who and p.get(key) == who), None)


def _asked(d: dict, who: str):
    who = clean_email(who)
    key = "email" if "@" in who else "username"
    return next((r for r in d["requests"] if who and r.get(key) == who), None)


def _username_free(d: dict, name: str, but=None) -> bool:
    return not any(x.get("username") == name for x in d["people"] if x is not but) \
        and not any(r.get("username") == name for r in d["requests"] if r is not but)


def people() -> list[dict]:
    return [_public(p) for p in _read()["people"]]


def requests() -> list[dict]:
    return [{k: r.get(k) for k in ("email", "name", "username", "note", "at")} for r in _read()["requests"]]


def settings() -> dict:
    s = _read()["settings"]
    return {"requests": s.get("requests", True), "notify": s.get("notify", True)}


def set_settings(**kw) -> dict:
    with _lock:
        d = _read()
        for k in ("requests", "notify"):
            if kw.get(k) is not None:
                d["settings"][k] = bool(kw[k])
        _write(d)
    return settings()


def mask(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:1]}•••@{domain}"


def _secret(d: dict) -> None:
    if not d.get("secret"):
        d["secret"] = secrets.token_hex(32)


# ---------- passwords: scrypt, with its salt and costs in one string ----------

def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hash_pass(pw: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(pw.encode(), salt=salt, n=SCRYPT["n"], r=SCRYPT["r"], p=SCRYPT["p"],
                         maxmem=64 * 1024 * 1024, dklen=64)
    return f"scrypt${SCRYPT['n']}${SCRYPT['r']}${SCRYPT['p']}${_b64(salt)}${_b64(key)}"


def check_pass(pw: str, stored: str | None) -> bool:
    m = re.match(r"^scrypt\$(\d+)\$(\d+)\$(\d+)\$([^$]+)\$([^$]+)$", str(stored or ""))
    if not m:
        hash_pass("x")                    # the same time whether or not there's a password
        return False
    want = base64.b64decode(m[5])
    got = hashlib.scrypt(str(pw).encode(), salt=base64.b64decode(m[4]), n=int(m[1]), r=int(m[2]), p=int(m[3]),
                         maxmem=64 * 1024 * 1024, dklen=len(want))
    return hmac.compare_digest(want, got)


def _good_password(pw: str) -> None:
    if len(pw) < PASSWORD_MIN:
        raise Refused("short")
    if len(pw) > 200:
        raise Refused("long")


# ---------- the list ----------

def _send_invite(p: dict) -> bool:
    return mail.send(p["email"], *emails.invite(email=p["email"], name=p.get("name"),
                                                url=config.PUBLIC_URL, signature=config.SIGNATURE))


def allow(email: str, invite: bool = True, name: str | None = None) -> dict:
    """Put an address on the list (the first one is the owner). Returns {"invited": bool}."""
    email = clean_email(email)
    if not EMAIL.match(email):
        raise Refused("email")
    with _lock:
        d = _read()
        _secret(d)
        if _find(d, email):
            raise Refused("exists")
        p = {"email": email, "username": None, "name": _clip(name, 60) or None, "owner": not d["people"],
             "added": int(time.time()), "joined": None, "key": secrets.token_hex(8)}
        d["people"].append(p)
        d["requests"] = [r for r in d["requests"] if r["email"] != email]
        _write(d)
    return {"invited": _send_invite(p) if invite else False}


def invite_again(email: str) -> dict:
    p = _find(_read(), email)
    if not p:
        raise Refused("not-on-list")
    if p.get("joined"):
        raise Refused("exists")
    with _lock:
        if _limited(f"invite:{p['email']}", 3, 86400):
            raise Refused("throttled")
        _hit(f"invite:{p['email']}")
    if not _send_invite(p):
        raise Refused("mail")
    return {"invited": True}


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


# ---------- asking for an invite (/join) ----------

def ask(*, name: str, email: str, username: str, password: str | None, note: str | None, ip: str) -> dict:
    """Step one: check it, keep it in memory, and email a code to prove the address.
    Returns {"allowed": True} for someone who's already on the list."""
    email, name, username = clean_email(email), _clip(name, 60), clean_email(username)
    if not settings()["requests"]:
        raise Refused("closed")
    if not name:
        raise Refused("name")
    if not EMAIL.match(email):
        raise Refused("email")
    if not USERNAME.match(username):
        raise Refused("username")
    if password:
        _good_password(password)
    with _lock:
        d = _read()
        if _find(d, email):
            return {"allowed": True}
        mine = _asked(d, email)
        if not _username_free(d, username, but=mine):
            raise Refused("taken")
        if (_limited(f"ask-ip:{ip}", 4, 3600) or _limited(f"ask:{email}", 3, 3600) or _limited("ask", 30, 86400)
                or len(d["requests"]) >= 50):
            raise Refused("throttled")
        _hit(f"ask-ip:{ip}", f"ask:{email}", "ask")
    code = f"{secrets.randbelow(10 ** 6):06d}"
    _asking[email] = {"name": name, "username": username, "note": _clip(note, 300) or None,
                      "pass": hash_pass(password) if password else None,
                      "hash": _sha(email, code), "exp": time.time() + ASK_SECONDS, "tries": 0}
    if not mail.send(email, *emails.code(code, config.PUBLIC_URL, ask=True)):
        _asking.pop(email, None)
        raise Refused("mail")
    return {"allowed": False}


def confirm(email: str, code: str, ip: str) -> dict:
    """Step two: the code came back, so it's a real address. It waits for the owner now."""
    email = clean_email(email)
    with _lock:
        if _limited(f"bad:{ip}", 20, 3600):
            raise Refused("throttled")
        a = _asking.get(email)
        if not a or a["exp"] < time.time():
            raise Refused("expired")
        if not hmac.compare_digest(a["hash"], _sha(email, re.sub(r"\D", "", str(code or "")))):
            _hit(f"bad:{ip}")
            a["tries"] += 1
            if a["tries"] >= CODE_TRIES:
                _asking.pop(email, None)
            raise Refused("wrong")
        _asking.pop(email, None)
        d = _read()
        if _find(d, email):
            return {"allowed": True}
        again = _asked(d, email)
        if not _username_free(d, a["username"], but=again):
            raise Refused("taken")
        r = {"email": email, "name": a["name"], "username": a["username"], "note": a["note"], "pass": a["pass"],
             "at": again["at"] if again else int(time.time())}
        d["requests"] = [x for x in d["requests"] if x is not again] + [r]
        _write(d)
        owners = [p["email"] for p in d["people"] if p.get("owner")]
    if not again and settings()["notify"]:
        msg = emails.request(name=r["name"], email=email, username=r["username"], note=r["note"], url=config.PUBLIC_URL)
        for o in owners:
            mail.send(o, *msg)
    return {"allowed": False}


def approve(email: str) -> dict:
    """The owner said yes: the account is made then and there, with the request's username and
    password, and they get an email."""
    email = clean_email(email)
    with _lock:
        d = _read()
        _secret(d)
        r = _asked(d, email)
        if not r:
            raise Refused("not-on-list")
        d["requests"] = [x for x in d["requests"] if x is not r]
        if _find(d, email):
            _write(d)
            return {"mailed": False}
        name = r["username"] if _username_free(d, r["username"]) else None
        p = {"email": email, "username": name, "name": r.get("name"), "owner": False, "added": int(time.time()),
             "joined": None, "key": secrets.token_hex(8)}
        if r.get("pass"):
            p["pass"], p["pass_set"] = r["pass"], int(time.time())
        d["people"].append(p)
        _write(d)
    return {"mailed": mail.send(email, *emails.approved(email=email, name=p["name"], username=name,
                                                         password=bool(p.get("pass")), url=config.PUBLIC_URL,
                                                         signature=config.SIGNATURE))}


def decline(email: str) -> None:
    email = clean_email(email)
    with _lock:
        d = _read()
        d["requests"] = [r for r in d["requests"] if r["email"] != email]
        _write(d)


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
        d = _read()
        p = _find(d, who)
        if not p:
            raise Refused("pending" if _asked(d, who) else "not-on-list")
        email = p["email"]
        if _limited(f"to:{email}", 3, 900) or _limited(f"day:{email}", 8, 86400):
            raise Refused("throttled")
        _hit(f"to:{email}", f"day:{email}")
        if len(_codes) > 1000:
            for k in [k for k, c in _codes.items() if c["exp"] < time.time()]:
                _codes.pop(k, None)
        code = f"{secrets.randbelow(10 ** 6):06d}"
        _codes[email] = {"hash": _sha(email, code), "exp": time.time() + CODE_SECONDS, "tries": 0}
    if not mail.send(email, *emails.code(code, config.PUBLIC_URL)):
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
            if not _username_free(d, name, but=p):
                raise Refused("taken")
            p["username"] = name
        p["joined"] = p.get("joined") or int(time.time())
        _write(d)
        _codes.pop(p["email"], None)
        return _cookie(d, p)


def sign_in_password(who: str, password: str, ip: str) -> str:
    login = clean_email(who)[:254]
    pw = str(password or "")[:200]
    if not login or not pw:
        raise Refused("login")
    with _lock:
        if _limited(f"pw-ip:{ip}", 12, 900):
            raise Refused("throttled")
        _hit(f"pw-ip:{ip}")
        if _limited(f"pw:{login}", 8, 900):
            raise Refused("locked")
        d = _read()
        p = _find(d, login)
    ok = check_pass(pw, p and p.get("pass"))
    if not p:
        r = _asked(d, login)
        if r and r.get("pass") and check_pass(pw, r["pass"]):
            raise Refused("pending")
    if not ok or not p:
        with _lock:
            _hit(f"pw:{login}")
        raise Refused("login")
    with _lock:
        d = _read()
        p = _find(d, login)
        if not p:
            raise Refused("login")
        p["joined"] = p.get("joined") or int(time.time())
        _write(d)
        _hits.pop(f"pw:{login}", None)
        return _cookie(d, p)


# ---------- your own account ----------

def update(email: str, *, name: str | None = None, username: str | None = None) -> dict:
    with _lock:
        d = _read()
        p = _find(d, email)
        if not p:
            raise Refused("not-on-list")
        if name is not None:
            p["name"] = _clip(name, 60) or None
        if username is not None:
            u = clean_email(username)
            if not USERNAME.match(u):
                raise Refused("username")
            if not _username_free(d, u, but=p):
                raise Refused("taken")
            p["username"] = u
        _write(d)
        return _public(p)


def set_password(email: str, new: str, current: str | None) -> str:
    """A new password signs out everywhere else. Returns this browser's new cookie."""
    _good_password(str(new or ""))
    p = _find(_read(), email)
    if not p:
        raise Refused("not-on-list")
    if p.get("pass") and not check_pass(str(current or ""), p["pass"]):
        raise Refused("current")
    stored = hash_pass(new)
    with _lock:
        d = _read()
        p = _find(d, email)
        p["pass"], p["pass_set"], p["key"] = stored, int(time.time()), secrets.token_hex(8)
        _write(d)
        return _cookie(d, p)


def remove_password(email: str, current: str | None) -> None:
    p = _find(_read(), email)
    if not p:
        raise Refused("not-on-list")
    if p.get("pass") and not check_pass(str(current or ""), p["pass"]):
        raise Refused("current")
    with _lock:
        d = _read()
        p = _find(d, email)
        p.pop("pass", None)
        p.pop("pass_set", None)
        _write(d)


def sign_out_others(email: str) -> str:
    with _lock:
        d = _read()
        p = _find(d, email)
        if not p:
            raise Refused("not-on-list")
        p["key"] = secrets.token_hex(8)
        _write(d)
        return _cookie(d, p)


# ---------- the cookie: key.expiry.username.signature (a username can have dots) ----------
# The key alone says who it is, so a new username doesn't sign anyone out.

def _cookie(d: dict, p: dict) -> str:
    body = f"{p['key']}.{int(time.time()) + DAYS * 86400}.{p.get('username') or ''}"
    return body + "." + hmac.new(bytes.fromhex(d["secret"]), body.encode(), "sha256").hexdigest()


def _person(value: str | None):
    """(the file, the person, the expiry) for a good cookie, or None."""
    if not value or value.count(".") < 3:
        return None
    d = _read()
    if not d.get("secret"):
        return None
    body, sig = value.rsplit(".", 1)
    good = hmac.new(bytes.fromhex(d["secret"]), body.encode(), "sha256").hexdigest()
    if not hmac.compare_digest(sig, good):
        return None
    key, exp, _ = body.split(".", 2)
    p = next((x for x in d["people"] if x.get("key") == key), None)
    if not p or not exp.isdigit() or int(exp) < time.time():
        return None
    return d, p, int(exp)


def who(value: str | None) -> dict | None:
    """The person a cookie belongs to (with "renew": True once it's a day old), or None."""
    found = _person(value)
    if not found:
        return None
    _, p, exp = found
    return {**_public(p), "renew": exp < time.time() + (DAYS - 1) * 86400}


def renew(value: str) -> str | None:
    found = _person(value)
    return _cookie(found[0], found[1]) if found else None


def main(argv: list[str]) -> int:
    cmd, rest = (argv[0] if argv else "list"), argv[1:]
    try:
        if cmd == "list":
            for p in people():
                print(f"{p['email']:<36} {p['username'] or '-':<20} {'owner' if p['owner'] else ''}")
            for r in requests():
                print(f"{r['email']:<36} {r['username'] or '-':<20} asked")
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
