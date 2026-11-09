import re

from tamlil import web


def test_pages_point_at_this_release_of_their_files():
    for name in ("index.html", "login.html", "share.html"):
        r = web._page(name)
        body = r.body.decode()
        assert re.search(r'/static/app\.css\?v=[0-9a-f]{10}"', body), name
        assert '/static/app.css"' not in body and r.headers["cache-control"] == "no-cache"
    assert re.search(r'/static/app\.js\?v=[0-9a-f]{10}"', web._page("index.html").body.decode())
