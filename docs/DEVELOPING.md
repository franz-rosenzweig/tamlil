<sub>[Tamlil docs](README.md) › Under the hood</sub>

# Developing and running it

## The stack

`docker-compose.yml` has seven services:

| Service | What it does |
|---|---|
| gateway | Caddy on 127.0.0.1:8445, the one way in for the app and its player. Outside the tailnet it asks the app about the sign-in first. |
| web | the app's page and API (FastAPI), on the stack's own network only, and the chat (up to 2 GB, for Claude Code) |
| worker | lists the sources and gets the transcripts, at the lowest priority, with at most 8 CPUs and 6 GB |
| gluetun | the VPN, with an HTTP proxy that the worker and Invidious go through |
| invidious, companion, invidious-db | the private player |

## Settings

Copy `.env.example` to `.env`:

- **The VPN:** `VPN_SERVICE_PROVIDER`, `WIREGUARD_PRIVATE_KEY` and `SERVER_COUNTRIES`, for any provider gluetun supports. Give the stack a key of its own.
- **Invidious:** `INVIDIOUS_DB_PASSWORD`, `INVIDIOUS_HMAC_KEY`, and `COMPANION_KEY` (exactly 16 characters).
- **Folders:** `DATA_DIR` for the database, temp audio and caches, and `MODELS_DIR` for the Whisper models (about 1.6 GB each, downloaded the first time they're needed).
- **For the emails:** `TAMLIL_URL`, the address people open it at, and `TAMLIL_SIGNATURE`, the name the invite is signed with.
- `TZ`, and `TAMLIL_USER` if the folders belong to someone other than 1000:1000.

Anything that only fits your own server goes in `docker-compose.override.yml`, which Compose reads on its own and git ignores. `docker-compose.override.example.yml` has the two I use: the gateway also answering on the Tailscale address, and the web container joining a mail relay's network.

```sh
docker compose up -d --build
docker compose logs -f worker
```

## The tailnet and the outside

The gateway lets in anything from Tailscale's range (100.64.0.0/10) without a sign-in, and tells the app so with a header that it strips from everyone else. Everything else needs a sign-in cookie, checked on every request, except the sign-in pages (`/login`, `/join` and `/api/auth/*`), the static files, and the transcripts someone chose to share (`/s/*` and `/api/shared/*`). To open Tamlil from anywhere, point a tunnel or a proxy at 127.0.0.1:8445 (mine is a Cloudflare tunnel), and set `TAMLIL_URL` to that address.

## Mail

The emails (the codes, the invites, the welcome after a yes, and the note to the owner about a request) go out through any SMTP server with STARTTLS, set in `mail.json` in `DATA_DIR` (mode 600):

```json
{ "host": "protonmail-bridge", "port": 25, "user": "...", "pass": "...", "from": "Tamlil <support@example.com>" }
```

Mine is Proton Mail Bridge in its own Compose project, so the override puts the web container on Bridge's network and `host` is Bridge's container name. A self-signed certificate is accepted only from localhost and that name. Without `mail.json`, nobody can sign in from outside the tailnet.

Each email is HTML in Tamlil's colors with a plain text copy, both in `emails.py`. The icon in them loads from `/static/icon-mail.png` at `TAMLIL_URL`, so that address has to be reachable from outside for the picture to show.

For the emails to land in inboxes and not in spam, the `from` domain needs SPF, DKIM and DMARC records, which your mail provider gives you when you add the domain.

## People from the command line

```sh
docker exec tamlil-web python -m tamlil.accounts list
docker exec tamlil-web python -m tamlil.accounts allow EMAIL [--quiet]   # --quiet: no invite email
docker exec tamlil-web python -m tamlil.accounts remove EMAIL
```

The first address on the list is the owner's. `list` shows the requests waiting too.

## What it keeps

Everything is in `DATA_DIR`:

- `tamlil.db`: the sources, videos, transcripts, the index, the shared links and the chats (SQLite).
- `accounts.json`: the people (with scrypt hashes for anyone who set a password), the requests, the two settings for requests, and the cookie secret. It, `mail.json` and `chat.json` (how chat reaches Claude, with its API key or Claude Code token) are all mode 600.
- `tmp/` for audio while it's transcribed, `cache/` for yt-dlp, and `pylib/` for the daily yt-dlp.

After changing the Hebrew rules in `hebrew.py`, rebuild the index from the saved transcripts:

```sh
docker exec tamlil-web python -m tamlil.reindex
```

## Tests

```sh
docker compose build web && docker run --rm -e TAMLIL_DATA=/tmp tamlil:latest python -m pytest -q tests
```

They cover the Hebrew matching, the caption parser, the index, the search filters and sorting, the links from YouTube, Invidious and Materialious, the accounts, codes and passwords, asking for an invite, the emails, export, listing in batches, and the chat (its tools, its settings, and an answer with tool calls, against a stand-in for Claude).

## The demo

The pictures in these docs come from `tools/demo.py`. It builds a database with made-up channels and lectures, three made-up people, two requests waiting, a shared link, a paused playlist, two chats (answered by Claude on the demo itself), and a worker halfway through a lecture, and serves the real app on it, with drawn thumbnails and a still player in place of YouTube. Pictures of my own Tamlil would show what I watch and who I share it with, so they never go in here.

```sh
docker run --rm -v "$PWD:/src:ro" -p 127.0.0.1:8499:8000 tamlil:latest python /src/tools/demo.py
```

These pages are in `docs/`, and docs.tiresia.xyz builds them within 10 minutes of a push to `main`.
