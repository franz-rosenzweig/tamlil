<sub>[Tamlil docs](README.md) › Under the hood</sub>

# How it works

## Captions or Whisper

For each video, Tamlil takes the first of these it can get:

1. **The uploader's own captions,** in the language that's spoken.
2. **YouTube's automatic captions,** for English only. Its Hebrew ones aren't good enough to search.
3. **Whisper,** on the server's CPU: ivrit.ai's model for Hebrew (Whisper large-v3-turbo, trained further on Hebrew), and Whisper large-v3-turbo for everything else.

Translated caption tracks never count, since they're not what was said. If the source's language is Detect and the captions don't settle it, Whisper listens to 30 seconds from the middle of the video and decides. YouTube's own label for the language only decides which captions to look for, never what Whisper hears, because on a video YouTube has dubbed into other languages the label can name one of the dubs. For those, Tamlil goes by the language of the original audio track.

Whisper runs at the lowest priority on 8 threads, with a beam of 5 and voice detection, and it leaves out the lines it makes up in silence and music (Whisper likes to "hear" things there). It takes about 25 minutes for an hour of Hebrew. Anything longer than half an hour goes through in pieces of about 20 minutes, each cut at a quiet moment so no word is split, because a long video in one go needs more memory than the worker has. Captions take a few seconds a video. For Whisper, only the audio is downloaded, at a low bitrate, and it's deleted as soon as the video is done.

## The index

Every transcript is cut into 30-second stretches that overlap by half, and each stretch goes into SQLite's full-text index with every Hebrew word in all its forms: as it's written, without its prefixes, and without its extra ו and י. A search finds the stretches first, then checks every line in them to mark exactly which words matched and why. See [Searching](searching.md).

## Talking to YouTube

- Everything that talks to YouTube, the worker and the player both, goes through the stack's own VPN (gluetun), never the server's own address.
- The worker waits 4 seconds between requests, and lists a channel 10 videos at a time.
- When YouTube turns the VPN away (its bot check, or too many requests), the worker asks gluetun for another server, at most once in 10 minutes, and otherwise waits half an hour. Changing servers needs `GLUETUN_KEY` (see `.env.example`); without it, it only waits.
- When nothing gets through the VPN at all, that isn't counted against any video either. The worker makes sure gluetun's VPN is switched on and tries again every 2 minutes.
- If the worker stops partway through a video (a restart, or running out of memory), that counts as one try, so one video can't keep it going round in circles.
- yt-dlp, which does the talking, updates itself once a day, since YouTube changes things often.

## The player

The player is a private Invidious with its companion, both behind the same gateway as Tamlil, so they share one address and one sign-in. Its own accounts and sign-ups are switched off.

<sub>Next: [Developing and running it](DEVELOPING.md)</sub>
