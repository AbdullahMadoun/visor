import threading
import urllib.request
from http.server import HTTPServer

from visor.strategy import tree, tree_server


def test_live_map_shows_branches_and_escapes_page_text(monkeypatch):
    data = {"rsvp": {"find_RSVP": {"not_found": {"More_visible": {
        "action": "click_ocr", "target": "<script>alert(1)</script>",
        "reason": "RSVP moved under More", "proven_on": "http://x/2"}}}}}
    monkeypatch.setattr(tree, "load", lambda: data)
    server = HTTPServer(("127.0.0.1", 0), tree_server.TreeHandler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    page = urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/", timeout=5).read().decode()
    server.server_close()
    assert "RSVP moved under More" in page and "http://x/2" in page
    assert "<script>alert(1)" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
