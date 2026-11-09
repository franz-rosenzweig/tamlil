"""Using a ChatGPT plan for the chat, through OpenAI's "Sign in with ChatGPT" for open-source apps.

The sign-in is OpenID Connect with PKCE. OpenAI only sends people back to a loopback address
(http://127.0.0.1:<port>/auth/callback), which is the computer the browser is on:

- on the computer Tamlil runs on, that is Tamlil's own front door, and the sign-in finishes by itself;
- anywhere else, the browser lands on a page that doesn't load, and the owner pastes its address into
  Settings, which finishes the same sign-in from there.

Everything is kept in data/chatgpt.json (readable only by its owner): this copy's host id, the client id
OpenAI issued it, a sign-in that's under way, and the tokens, refreshed before they run out. The refresh
token is replaced every time OpenAI hands out a new one.
Docs: https://developers.openai.com/siwc/token-sharing-open-source
"""

import asyncio
import base64
import hashlib
import json
import os
import secrets
import time
import uuid
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from . import config

ISSUER = "https://auth.openai.com"
AUTHORIZE = ISSUER + "/api/accounts/authorize"
TOKEN = ISSUER + "/api/accounts/oauth/token"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
DYNAMIC = "dynamic_agent_client"
PORT = int(os.environ.get("TAMLIL_PORT", "8445"))      # the front door's port on this computer

_lock = asyncio.Lock()
_transport = None                                     # tests swap in an httpx.MockTransport


class SignInError(Exception):
    """The sign-in didn't finish; the message is a short code the page turns into words."""


class Failed(Exception):
    """The plan can't be used right now: "signin" (sign in again) or "network"."""


def _http() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30, transport=_transport)


def redirect_uri() -> str:
    return f"http://127.0.0.1:{PORT}/auth/callback"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _file():
    return config.DATA / "chatgpt.json"


def _state() -> dict:
    try:
        return json.loads(_file().read_text())
    except (OSError, ValueError):
        return {}


def _save(state: dict) -> None:
    f = _file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as out:
        json.dump(state, out)
    os.replace(tmp, f)


def load() -> dict | None:
    """The tokens, or None when ChatGPT isn't signed in."""
    return _state().get("creds") or None


def status() -> dict | None:
    creds = load()
    return {"email": creds.get("email", ""), "name": creds.get("name", "")} if creds else None


def start() -> str:
    """The address to open for "Continue with ChatGPT"."""
    st = _state()
    st.setdefault("host_id", str(uuid.uuid4()))       # OpenAI's ext_agent_host_id for this copy of Tamlil
    client_id = st.get("client_id") or DYNAMIC
    verifier = _b64(secrets.token_bytes(48))
    st["pending"] = {"state": secrets.token_urlsafe(24), "nonce": secrets.token_urlsafe(24), "verifier": verifier,
                     "client_id": client_id, "at": time.time()}
    _save(st)
    params = {
        "response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri(),
        "scope": SCOPES, "state": st["pending"]["state"], "nonce": st["pending"]["nonce"],
        "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()), "code_challenge_method": "S256",
        "resource": RESOURCE, "ext_agent_host_id": st["host_id"],
    }
    if client_id == DYNAMIC:
        params["agent_name_hint"] = "Tamlil"
    if (st.get("creds") or {}).get("email"):
        params["login_hint"] = st["creds"]["email"]
    return AUTHORIZE + "?" + urlencode(params)


def parse_callback(url_or_query: str) -> dict:
    text = (url_or_query or "").strip()
    query = urlparse(text).query if "://" in text else text.lstrip("?")
    return {k: v[0] for k, v in parse_qs(query).items()}


async def finish(params: dict) -> dict:
    """Finish the sign-in from the callback's query (pasted or received). Returns the account."""
    st = _state()
    pending = st.get("pending")
    if not pending:
        raise SignInError("start")
    if params.get("state") != pending["state"]:
        raise SignInError("state")
    if params.get("error"):
        raise SignInError("denied" if params["error"] == "access_denied" else "refused")
    if time.time() - pending["at"] > 1800:
        raise SignInError("expired")
    code = params.get("code")
    if not code:
        raise SignInError("code")
    issued = params.get("client_id") or pending["client_id"]
    if pending["client_id"] != DYNAMIC and issued != pending["client_id"]:
        raise SignInError("client")
    try:
        async with _http() as c:
            r = await c.post(TOKEN, data={"grant_type": "authorization_code", "client_id": issued, "code": code,
                                          "code_verifier": pending["verifier"], "redirect_uri": redirect_uri(),
                                          "resource": RESOURCE})
    except httpx.TransportError:
        raise SignInError("network") from None
    if r.status_code >= 400:
        raise SignInError("expired" if "invalid_grant" in r.text else "refused")
    tok = r.json()
    if issued == DYNAMIC:
        # The issued id didn't come back on the callback: take it from the token response, or the ID token's audience.
        import jwt
        aud = jwt.decode(tok["id_token"], options={"verify_signature": False}).get("aud")
        issued = tok.get("client_id") or (aud[0] if isinstance(aud, list) else aud) or ""
        if not issued or issued == DYNAMIC:
            raise SignInError("client")
    claims = await _verify(tok["id_token"], issued, pending["nonce"])
    scopes = (tok.get("scope") or "").split()
    if PLAN_SCOPE not in scopes:
        raise SignInError("scope")
    st = _state()
    st.update(client_id=issued, pending=None, creds={
        "client_id": issued, "sub": claims["sub"], "email": claims.get("email", ""), "name": claims.get("name", ""),
        "id_token": tok["id_token"], "access_token": tok["access_token"], "refresh_token": tok.get("refresh_token", ""),
        "expires_at": time.time() + int(tok.get("expires_in", 3600)), "scopes": scopes, "saved_at": time.time()})
    _save(st)
    return status()


async def _verify(id_token: str, client_id: str, nonce: str) -> dict:
    import jwt

    try:
        async with _http() as c:
            oidc = (await c.get(ISSUER + "/.well-known/openid-configuration")).json()
            jwks = (await c.get(oidc["jwks_uri"])).json()
    except (httpx.HTTPError, KeyError, ValueError):
        raise SignInError("network") from None
    header = jwt.get_unverified_header(id_token)
    jwk = {k.get("kid"): k for k in jwks.get("keys", [])}.get(header.get("kid"))
    if not jwk:
        raise SignInError("id_token")
    try:
        claims = jwt.decode(id_token, jwt.PyJWK(jwk).key, algorithms=[header.get("alg", "RS256")], audience=client_id,
                            issuer=oidc.get("issuer", ISSUER))
    except jwt.PyJWTError as e:
        raise SignInError("id_token") from e
    if claims.get("nonce") != nonce:
        raise SignInError("nonce")
    return claims


async def access_token(force: bool = False) -> str:
    async with _lock:
        st = _state()
        creds = st.get("creds")
        if not creds:
            raise Failed("signin")
        if force or creds["expires_at"] - time.time() < 120:
            try:
                async with _http() as c:
                    r = await c.post(TOKEN, data={"grant_type": "refresh_token", "client_id": creds["client_id"],
                                                  "refresh_token": creds["refresh_token"], "resource": RESOURCE})
            except httpx.TransportError:
                raise Failed("network") from None
            if r.status_code >= 400:
                raise Failed("signin")
            tok = r.json()
            creds["access_token"] = tok["access_token"]
            creds["refresh_token"] = tok.get("refresh_token") or creds["refresh_token"]
            creds["expires_at"] = time.time() + int(tok.get("expires_in", 3600))
            if tok.get("scope"):
                creds["scopes"] = tok["scope"].split()
            creds["saved_at"] = time.time()
            _save(st)
        return creds["access_token"]


async def disconnect() -> bool:
    """Revoke the refresh token at OpenAI and forget the tokens. False if OpenAI couldn't be told."""
    st = _state()
    creds = st.get("creds")
    told = True
    if creds and creds.get("refresh_token"):
        try:
            async with _http() as c:
                oidc = (await c.get(ISSUER + "/.well-known/openid-configuration")).json()
                r = await c.post(oidc["revocation_endpoint"], data={
                    "token": creds["refresh_token"], "token_type_hint": "refresh_token", "client_id": creds["client_id"]})
                told = r.status_code == 200
        except (httpx.HTTPError, KeyError, ValueError):
            told = False
    st["creds"] = None
    st["pending"] = None
    _save(st)
    return told
