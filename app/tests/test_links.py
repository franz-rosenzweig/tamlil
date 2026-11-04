import pytest

from tamlil.links import to_youtube

V = "dQw4w9WgXcQ"
UC = "UCBJycsmduvYEL83R_U4JriQ"
PL = "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"


@pytest.mark.parametrize("link, want", [
    # YouTube itself
    (f"https://www.youtube.com/watch?v={V}&t=42s", f"https://www.youtube.com/watch?v={V}"),
    (f"https://youtu.be/{V}?si=abc", f"https://www.youtube.com/watch?v={V}"),
    (f"https://m.youtube.com/shorts/{V}", f"https://www.youtube.com/watch?v={V}"),
    (f"https://music.youtube.com/watch?v={V}&list={PL}", f"https://www.youtube.com/watch?v={V}"),
    (f"https://www.youtube.com/playlist?list={PL}", f"https://www.youtube.com/playlist?list={PL}"),
    (f"https://www.youtube.com/channel/{UC}/videos", f"https://www.youtube.com/channel/{UC}"),
    ("https://www.youtube.com/@mkbhd", "https://www.youtube.com/@mkbhd"),
    ("youtube.com/@mkbhd/videos", "https://www.youtube.com/@mkbhd"),
    ("https://www.youtube.com/c/somename", "https://www.youtube.com/c/somename"),
    # Invidious: YouTube's own paths, on any instance
    (f"https://invidious.example.com/watch?v={V}&listen=false", f"https://www.youtube.com/watch?v={V}"),
    (f"https://yewtu.be/channel/{UC}/playlists", f"https://www.youtube.com/channel/{UC}"),
    (f"https://inv.example.org/playlist?list={PL}", f"https://www.youtube.com/playlist?list={PL}"),
    (f"https://inv.example.org/embed/{V}?t=10", f"https://www.youtube.com/watch?v={V}"),
    (f"https://inv.example.org/{V}", f"https://www.youtube.com/watch?v={V}"),
    ("https://invidious.example.com/@mkbhd", "https://www.youtube.com/@mkbhd"),
    # Materialious: the ID in the path
    (f"https://materialious.example.com/watch/{V}?playlist={PL}&time=30", f"https://www.youtube.com/watch?v={V}"),
    (f"https://materialious.example.com/playlist/{PL}", f"https://www.youtube.com/playlist?list={PL}"),
    (f"https://materialious.example.com/channel/{UC}", f"https://www.youtube.com/channel/{UC}"),
])
def test_links(link, want):
    assert to_youtube(link) == want


@pytest.mark.parametrize("link", [
    "", "not a link", "https://invidious.example.com/feed/popular", "https://materialious.example.com/search/cats",
    "https://www.youtube.com/watch?v=short", "https://www.youtube.com/channel/nope", "https://example.com/",
    "https://www.youtube.com/playlist", "localhost/watch?v=dQw4w9WgXcQx", "javascript:alert(1)",
])
def test_not_links(link):
    assert to_youtube(link) is None
