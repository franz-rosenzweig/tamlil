<sub>[Tamlil docs](README.md) › Using it</sub>

# Chat

Search is for when I remember the words. Chat is for when I remember the idea: I ask Claude a question about the videos, and it looks through the transcripts for me. It searches them the same way the search box does, reads the parts it needs, and answers with the moments it got them from. Every yellow time in an answer opens the video right there.

![A chat: a question about the firmament, and an answer about two lectures with a yellow time after each point and the two videos under it](images/chat.png)
*One question about the whole library, answered from two lectures.*

## Asking

- **Chat** at the top opens a new chat. Pick **All channels** or one channel, type the question, and **Ask** (or Enter; Shift+Enter starts a new line).
- **Ask** on a video opens a chat about that one video. Claude gets its whole transcript, so the answers come quickly.
- While Claude works, the line under the question says what it's doing: **Searching** a word, **Reading** a video, or **Listing videos**. The answer then appears as it's written. **Stop** ends it there, and what it wrote so far is kept.
- Ask more in the same chat, and Claude keeps the earlier questions and answers in mind.
- Each time in an answer opens the video at that moment, and the videos it cited are under the answer.
- It answers in the language you ask in, whatever language the videos are in. It searches Hebrew channels in Hebrew either way.
- The chats are kept, newest first, on the left. **✕** deletes one. Your chats are yours alone: nobody else sees them in Tamlil, the owner included.

The transcripts come from captions or from Whisper, so they have mistakes, most of all in names. Claude is told to say when a line looks garbled, and the time next to it is there so you can listen for yourself.

## Turning it on

Chat is the owner's to turn on, in **Settings** under **Chat**:

- **Answers by:**
  - **Off.**
  - **API key:** a key from the Claude Console. Every answer is paid for by that key's account, and **This month** in Settings counts the answers and adds up roughly what they cost.
  - **Claude Code:** Claude on the owner's own Claude plan, through Claude Code, with no API key. Run `claude setup-token` on any computer that has Claude Code. It opens the browser to sign in, then prints a long-lived token, and that goes in **Claude Code token**. Answers count toward the plan's usage, the same as using Claude Code yourself.
- **Model:** Sonnet 5.5 to start with. Opus 5.5 is slower and more careful, and Haiku 5.5 is the quickest and the cheapest.
- **Who:** **Just me** (the owner, and anyone on the tailnet) or **Everyone** on the list. Everyone but the owner gets 60 questions a day.

## What Claude can and can't do

- It has three tools, and all three only read: **search** (the search box's own search, with the same filters), **transcript** (a video's lines with their times) and **videos** (what's in the Library). It can't change the Library, see the people, or reach anything else.
- With Claude Code, every one of Claude Code's own tools is off: no files, no commands and no web. Its settings aren't loaded, and a question goes to it as plain text, so a file name or a slash command in a question is only words.
- What goes to Anthropic is the question, the chat's earlier questions and answers, the list of channels, and the transcript lines Claude reads.
- The key and the token are kept in `chat.json` in the data folder, which only its owner can read. Settings shows just their last four characters.

<sub>Next: [Signing in, people and Settings](people.md)</sub>
