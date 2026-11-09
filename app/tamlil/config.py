import os
from pathlib import Path

DATA = Path(os.environ.get("TAMLIL_DATA", "/data"))
DB_PATH = DATA / "tamlil.db"
TMP = DATA / "tmp"

# Every request to YouTube goes through the stack's own gluetun.
PROXY = os.environ.get("YTDLP_PROXY") or None
REQUEST_GAP = float(os.environ.get("REQUEST_GAP", "4"))
REFRESH_HOURS = float(os.environ.get("REFRESH_HOURS", "6"))
# gluetun's control server and its API key: with both, the worker moves to another VPN server
# when YouTube starts turning the current one away. Without them it waits it out.
GLUETUN_URL = (os.environ.get("GLUETUN_URL") or "").rstrip("/")
GLUETUN_KEY = os.environ.get("GLUETUN_KEY") or ""

WHISPER_THREADS = int(os.environ.get("WHISPER_THREADS", "8"))
WHISPER_BEAM = int(os.environ.get("WHISPER_BEAM", "5"))
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "large-v3-turbo")
WHISPER_MODEL_HE = os.environ.get("WHISPER_MODEL_HE", "ivrit-ai/whisper-large-v3-turbo-ct2")

# Where the player lives. Empty: the stack's Invidious on the same address (the gateway).
PLAYER_URL = (os.environ.get("PLAYER_URL") or "").rstrip("/")

# The address people sign in at, and the name the invite is signed with, for the emails.
PUBLIC_URL = (os.environ.get("TAMLIL_URL") or "http://localhost:8445").rstrip("/")
SIGNATURE = os.environ.get("TAMLIL_SIGNATURE") or "Tamlil"
