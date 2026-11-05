"""Tamlil's emails, dressed like the app: a dark band with the icon and a timeline with its
ticks, a white page, a timestamp beside each heading, and the key word highlighted the way a
search hit is. Email clients are picky, so it's tables and inline styles only, no scripts, no
SVG, and every color written out. Each one gives back (subject, text, html), and the text is
the same email for mail apps that want plain text.
"""
from html import escape

C = {"bg": "#ECEEF1", "page": "#FFFFFF", "ink": "#121419", "body": "#343945", "muted": "#5C6473",
     "rule": "#D2D6DD", "sunk": "#E2E5EA", "cap": "#FFD43B", "cap_ink": "#17150A", "band": "#121419",
     "band_2": "#8C94A3", "rail": "#2A2F39", "form": "#07756D", "form_bg": "#D3EEEA"}
DISPLAY = "Rubik, 'Segoe UI', Helvetica, Arial, sans-serif"
BODY = "Assistant, -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "'JetBrains Mono', SFMono-Regular, Menlo, Consolas, monospace"


def esc(s) -> str:
    return escape(str(s if s is not None else ""), quote=True)


def first(name) -> str:
    return (str(name or "").strip().split() or [""])[0]


def hl(word: str) -> str:
    """A word highlighted like an exact match in the search."""
    return (f'<span style="background:{C["cap"]};color:{C["cap_ink"]};padding:0 5px;border-radius:4px">'
            f'{esc(word)}</span>')


def kicker(ts: str, label: str) -> str:
    return f"""<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 14px"><tr>
<td style="font-family:{MONO};font-size:12px;font-weight:600;color:{C['ink']};background:{C['sunk']};border:1px solid {C['rule']};border-radius:5px;padding:3px 7px">{esc(ts)}</td>
<td style="padding-left:10px;font-family:{BODY};font-size:12px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:{C['muted']}">{esc(label)}</td>
</tr></table>"""


def title(html: str) -> str:
    return (f'<h1 style="font-family:{DISPLAY};font-size:30px;line-height:1.25;font-weight:700;color:{C["ink"]};'
            f'margin:0 0 16px">{html}</h1>')


def para(html: str, extra: str = "") -> str:
    return (f'<p style="font-family:{BODY};font-size:16px;line-height:1.6;color:{C["body"]};margin:0 0 16px;{extra}">'
            f'{html}</p>')


def small(html: str) -> str:
    return para(html, f"font-size:14px;color:{C['muted']};margin-top:14px")


def button(label: str, href: str) -> str:
    return f"""<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:6px 0 4px"><tr>
<td align="center" bgcolor="{C['ink']}" style="border-radius:10px;background:{C['ink']}">
<a href="{esc(href)}" style="display:inline-block;padding:14px 26px;font-family:{BODY};font-size:16px;font-weight:700;color:#FFFFFF;text-decoration:none;border-radius:10px">{esc(label)}</a>
</td></tr></table>"""


RULE = f'<div style="height:1px;background:{C["rule"]};margin:26px 0 22px;line-height:1px;font-size:0">&nbsp;</div>'


def moments(rows) -> str:
    """Lines like the app's results: a timestamp, then the line with its hit highlighted."""
    out = "".join(f"""<tr>
<td valign="top" style="padding:0 12px 12px 0"><span style="display:inline-block;font-family:{MONO};font-size:12px;font-weight:600;color:{C['ink']};background:{C['sunk']};border:1px solid {C['rule']};border-radius:5px;padding:3px 7px">{esc(ts)}</span></td>
<td style="padding:2px 0 12px;font-family:{BODY};font-size:15px;line-height:1.55;color:{C['body']}">{line}</td></tr>""" for ts, line in rows)
    return f'<table role="presentation" cellpadding="0" cellspacing="0" border="0">{out}</table>'


def strip() -> str:
    """The timeline under a search result, with a tick for each match."""
    cells, ticks = [], [9, 23, 27, 51, 74, 88]
    pos = 0
    for t in ticks:
        cells.append(f'<td width="{t - pos}%" style="height:6px;background:{C["rail"]};font-size:0;line-height:0">&nbsp;</td>')
        cells.append(f'<td width="4" style="width:4px;height:6px;background:{C["cap"]};font-size:0;line-height:0">&nbsp;</td>')
        pos = t
    cells.append(f'<td style="height:6px;background:{C["rail"]};font-size:0;line-height:0">&nbsp;</td>')
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="border-radius:3px;margin-top:22px"><tr>{"".join(cells)}</tr></table>')


def shell(*, url: str, preheader: str, body: str, footer: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light"><title>Tamlil</title></head>
<body style="margin:0;padding:0;background:{C['bg']}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{C['bg']}">{esc(preheader)}&#8199;&#65279;&#847;&#8199;&#65279;&#847;&#8199;&#65279;&#847;</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{C['bg']}" style="background:{C['bg']}"><tr><td align="center" style="padding:28px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px">
  <tr><td bgcolor="{C['band']}" style="background:{C['band']};border-radius:16px 16px 0 0;padding:26px 30px 24px">
    <a href="{esc(url)}" style="text-decoration:none">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
      <td valign="middle" style="padding-right:14px"><img src="{esc(url)}/static/icon-mail.png" width="44" height="44" alt="" style="display:block;border:1px solid #3D4350;border-radius:11px"></td>
      <td valign="middle" style="font-family:{DISPLAY};font-size:26px;font-weight:800;color:#FFFFFF;line-height:1">Tamlil <span lang="he" dir="rtl" style="font-size:19px;font-weight:600;color:{C['band_2']}">&#1514;&#1502;&#1500;&#1497;&#1500;</span></td>
    </tr></table></a>
    {strip()}
  </td></tr>
  <tr><td bgcolor="{C['page']}" style="background:{C['page']};border-radius:0 0 16px 16px;padding:32px 30px 28px;border:1px solid {C['rule']};border-top:0">
    {body}
  </td></tr>
  <tr><td align="center" style="padding:18px 24px 0;font-family:{BODY};font-size:12px;line-height:1.6;color:{C['muted']}">
    {footer}<br><a href="{esc(url)}" style="color:{C['muted']}">{esc(url.split('://')[-1])}</a>
  </td></tr>
</table></td></tr></table>
</body></html>"""


def _about(url: str) -> str:
    """What Tamlil does, as three lines from a transcript."""
    return RULE + moments([
        ("0:12", f"Search what's {hl('said')} in the videos, not just their titles."),
        ("3:40", f'Hebrew too: <span lang="he" dir="rtl">{hl("שמים")}</span> also finds '
                 f'<span lang="he" dir="rtl">השמים</span> and <span lang="he" dir="rtl">שמיים</span>.'),
        ("12:48", f"Every result opens the video right at that {hl('moment')}."),
    ])


def _sign(signature: str) -> str:
    return para(f"If anything doesn't work, just reply to this email and let me know.<br>{esc(signature)}",
                f"margin:18px 0 0")


def code(code: str, url: str, *, ask: bool = False):
    """The six digits, for signing in or for finishing a request."""
    mins = 15 if ask else 10
    box = (f'<td align="center" width="44" style="width:44px;height:56px;border:2px solid {C["ink"]};border-radius:8px;'
           f'background:#FFFFFF;font-family:{MONO};font-size:28px;font-weight:700;color:{C["ink"]}">{{}}</td>'
           f'<td width="7" style="width:7px"></td>')
    digits = "".join(box.format(esc(d)) for d in code[:3]) + '<td width="14" style="width:14px"></td>' + \
        "".join(box.format(esc(d)) for d in code[3:])
    html = shell(
        url=url,
        preheader=f"{code} is your Tamlil code. It works for {mins} minutes.",
        footer="If you didn't ask for this code, you can ignore this email. Nobody gets in without it.",
        body=f"""{kicker('0:00', 'Invite request' if ask else 'Sign in')}
{title(f"Your {hl('code')}")}
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:4px 0 22px"><tr>{digits}</tr></table>
{para(f"It works for {mins} minutes. Type it into Tamlil, or paste it." if not ask else
      f"It works for {mins} minutes. Type it into Tamlil to finish asking for an invite.")}""")
    text = (f"{code[:3]} {code[3:]}\n\n"
            + (f"Your code to finish asking for an invite to Tamlil. It works for {mins} minutes."
               if ask else f"Your code for signing in to Tamlil. It works for {mins} minutes.")
            + "\nIf you didn't ask for it, you can ignore this email: nobody gets in without the code.\n\n"
            + f"Tamlil\n{url}\n")
    return f"{code} is your Tamlil code", text, html


def invite(*, email: str, name: str | None, url: str, signature: str):
    hi = f"Hi {first(name)}," if first(name) else "Hi,"
    html = shell(
        url=url,
        preheader=f"{signature} added you to Tamlil. Sign in with this email, no password needed.",
        footer=f"You got this because {esc(signature)} added you to Tamlil.",
        body=f"""{kicker('0:00', "You're invited")}
{title(f"{esc(hi[:-1])}, you're {hl('in')}" if first(name) else f"You're {hl('in')}")}
{para("I added you to <b style='color:#121419'>Tamlil</b>, a little app I made that searches what's said in a few YouTube channels, in Hebrew and English, and plays the video right from that moment.")}
{button('Open Tamlil', url)}
{small(f"Sign in with <b style='color:#121419'>{esc(email)}</b>. You'll get a 6-digit code by email, and the first time you'll also pick a username. If you'd rather have a password, you can set one in Settings.")}
{_about(url)}
{_sign(signature)}""")
    text = f"""{hi}

I added you to Tamlil, which is a little app I made that searches what's said in a few YouTube channels, in Hebrew and English, and plays the video right from that moment.

To sign in, go to {url} and type {email}. You'll get a code by email, and the first time you'll also pick a username. If you'd rather have a password, you can set one in Settings.

If anything doesn't work, just reply to this email and let me know.

{signature}
"""
    return "You're invited to Tamlil", text, html


def approved(*, email: str, name: str | None, username: str | None, password: bool, url: str, signature: str):
    hi = f"Hi {first(name)}," if first(name) else "Hi,"
    login = f"<b style='color:#121419'>{esc(username)}</b> or {esc(email)}" if username else f"<b style='color:#121419'>{esc(email)}</b>"
    how = (f"Sign in with {login} and the password you chose, or with a code by email." if password
           else f"Sign in with {login}. You'll get a 6-digit code by email.")
    html = shell(
        url=url,
        preheader=f"{signature} said yes. Your Tamlil account is ready.",
        footer=f"You got this because you asked for an invite to Tamlil and {esc(signature)} said yes.",
        body=f"""{kicker('0:00', 'Approved')}
{title(f"{esc(hi[:-1])}, you're {hl('in')}" if first(name) else f"You're {hl('in')}")}
{para("I said yes, so your <b style='color:#121419'>Tamlil</b> account is ready. It searches what's said in a few YouTube channels, in Hebrew and English, and plays the video right from that moment.")}
{button('Open Tamlil', url)}
{small(how)}
{_about(url)}
{_sign(signature)}""")
    login_t = f"{username} or {email}" if username else email
    text = f"""{hi}

I said yes, so your Tamlil account is ready.

Go to {url} and sign in with {login_t}{" and the password you chose, or with a code by email" if password else ". You'll get a code by email"}.

If anything doesn't work, just reply to this email and let me know.

{signature}
"""
    return "You're in! Welcome to Tamlil", text, html


def request(*, name: str, email: str, username: str | None, note: str | None, url: str):
    """To the owner: someone asked for an invite."""
    rows = [("Name", name), ("Email", email), ("Username", username or ""), ("How we know each other", note or "")]
    table = "".join(f"""<tr><td valign="top" style="padding:0 16px 10px 0;font-family:{BODY};font-size:13px;font-weight:700;color:{C['muted']};white-space:nowrap">{esc(k)}</td>
<td dir="auto" style="padding:0 0 10px;font-family:{BODY};font-size:15px;color:{C['ink']}">{esc(v)}</td></tr>""" for k, v in rows if v)
    html = shell(
        url=url,
        preheader=f"{name} ({email}) asked for an invite to Tamlil.",
        footer="You get these because emails about requests are on in Settings.",
        body=f"""{kicker('0:00', 'Invite request')}
{title(f"{esc(first(name) or email)} wants {hl('in')}")}
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 18px">{table}</table>
{button('Open Settings', url + '/#/settings')}""")
    text = "\n".join([f"{name} asked for an invite to Tamlil.", ""] + [f"{k}: {v}" for k, v in rows if v]
                     + ["", f"Approve or decline in Settings: {url}/#/settings", ""])
    return f"{name} asked for an invite to Tamlil", text, html
