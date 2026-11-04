<sub>[Tamlil docs](README.md) › Under the hood</sub>

# Developing and running it

## The stack

`docker-compose.yml` has seven services:

| Service | What it does |
|---|---|
| gateway | Caddy on 127.0.0.1:8445, the one way in for the app and its player. Outside the tailnet it asks the app about the sign-in first. |
| web | the app's page and API (FastAPI), on the stack's own network only |
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

The gateway lets in anything from Tailscale's range (100.64.0.0/10) without a sign-in, and tells the app so with a header that it strips from everyone else. Everything else needs a sign-in cookie, checked on every request. To open Tamlil from anywhere, point a tunnel or a proxy at 127.0.0.1:8445 (mine is a Cloudflare tunnel), and set `TAMLIL_URL` to that address.

## Mail

The codes and invites go out through any SMTP server with STARTTLS, set in `mail.json` in `DATA_DIR` (mode 600):

```json
{ "host": "protonmail-bridge", "port": 25, "user": "...", "pass": "...", "from": "Tamlil <support@example.com>" }
```

Mine is Proton Mail Bridge in its own Compose project, so the override puts the web container on Bridge's network and `host` is Bridge's container name. A self-signed certificate is accepted only from localhost and that name. Without `mail.json`, nobody can sign in from outside the tailnet.

For the codes to land in inboxes and not in spam, the `from` domain needs SPF, DKIM and DMARC records, which your mail provider gives you when you add the domain.

## People from the command line

```sh
docker exec tamlil-web python -m tamlil.accounts list
docker exec tamlil-web python -m tamlil.accounts allow EMAIL [--quiet]   # --quiet: no invite email
docker exec tamlil-web python -m tamlil.accounts remove EMAIL
```

The first address on the list is the owner's.

## What it keeps

Everything is in `DATA_DIR`:

- `tamlil.db`: the sources, videos, transcripts and the index (SQLite).
- `accounts.json` (the people and the cookie secret) and `mail.json`, both mode 600.
- `tmp/` for audio while it's transcribed, `cache/` for yt-dlp, and `pylib/` for the daily yt-dlp.

After changing the Hebrew rules in `hebrew.py`, rebuild the index from the saved transcripts:

```sh
docker exec tamlil-web python -m tamlil.reindex
```

## Tests

```sh
docker compose build web && docker run --rm -e TAMLIL_DATA=/tmp tamlil:latest python -m pytest -q tests
```

They cover the Hebrew matching, the caption parser, the index, the search filters and sorting, the links from YouTube, Invidious and Materialious, the accounts and codes, and listing in batches.

## The demo

The pictures in these docs come from `tools/demo.py`. It builds a database with made-up channels and lectures, three made-up people, and a worker halfway through a lecture, and serves the real app on it, with drawn thumbnails and a still player in place of YouTube. Pictures of my own Tamlil would show what I watch and who I share it with, so they never go in here.

```sh
docker run --rm -v "$PWD:/src:ro" -p 127.0.0.1:8499:8000 tamlil:latest python /src/tools/demo.py
```

These pages are in `docs/`, and docs.tiresia.xyz builds them within 10 minutes of a push to `main`.
