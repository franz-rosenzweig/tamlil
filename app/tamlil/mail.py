"""Tamlil's few emails (codes, invites, and requests for an invite), through an SMTP server such as Proton Mail Bridge:
STARTTLS, then AUTH, one message per connection.

Where it sends from: TAMLIL_MAIL, or /data/mail.json (600, never in git):
  {"host": "protonmail-bridge", "port": 25, "user": "...", "pass": "...", "from": "Tamlil <support@example.com>"}
With Bridge in its own Compose project, put the web container on Bridge's network (see
docker-compose.override.example.yml) and use Bridge's container name as the host.
No file means no email, and nobody can sign in from outside the tailnet.
TAMLIL_MAIL=outbox writes each message to /data/outbox.jsonl instead (tests).
"""
import json
import os
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from . import config

# Bridge's certificate is its own, so it's only accepted on this machine or Bridge's private network.
LOCAL = {"127.0.0.1", "::1", "localhost", "protonmail-bridge"}


def _cfg():
    where = os.environ.get("TAMLIL_MAIL") or str(config.DATA / "mail.json")
    if where == "outbox":
        return "outbox"
    try:
        c = json.loads(open(where).read())
    except (OSError, ValueError):
        return None
    return c if c.get("from") else None


def available() -> bool:
    return _cfg() is not None


def send(to: str, subject: str, text: str, html: str | None = None) -> bool:
    """True when it went out. With html, it's both, and mail apps pick the one they show."""
    c = _cfg()
    if c is None:
        return False
    if c == "outbox":
        with open(config.DATA / "outbox.jsonl", "a") as f:
            f.write(json.dumps({"at": int(time.time()), "to": to, "subject": subject, "text": text, "html": html},
                               ensure_ascii=False) + "\n")
        return True
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = c["from"], to, subject
    m["Date"] = formatdate(localtime=True)
    m["Message-ID"] = make_msgid(domain=c["from"].split("@")[-1].strip(">"))
    m.set_content(text)
    if html:
        m.add_alternative(html, subtype="html")
    host = c.get("host", "127.0.0.1")
    ctx = ssl.create_default_context()
    if host in LOCAL:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    try:
        with smtplib.SMTP(host, int(c.get("port", 25)), timeout=20) as s:
            s.starttls(context=ctx)
            if c.get("user"):
                s.login(c["user"], c.get("pass", ""))
            s.send_message(m)
        return True
    except (OSError, smtplib.SMTPException) as e:
        print("mail to", to.split("@")[-1], "failed:", e, flush=True)
        return False
