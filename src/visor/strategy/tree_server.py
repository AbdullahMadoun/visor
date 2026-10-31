"""Live map of tree.json in the browser: `visor tree --serve`."""
import json
from html import escape
from visor.strategy import tree
from http.server import HTTPServer, BaseHTTPRequestHandler

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Visor Strategy Tree (Live)</title>
    <style>
        body { font-family: 'Courier New', Courier, monospace; background: #1e1e1e; color: #d4d4d4; padding: 30px; font-size: 16px; }
        ul { list-style-type: none; margin: 0; padding: 0; }
        ul ul { padding-left: 30px; border-left: 2px solid #404040; margin-left: 10px; padding-top: 5px; padding-bottom: 5px;}
        li { margin: 8px 0; position: relative; }
        li::before { content: "├─"; position: absolute; left: -25px; color: #606060; }
        li:last-child::before { content: "└─"; }
        .key { color: #569cd6; font-weight: bold; font-size: 1.1em;}
        .action { color: #4ec9b0; font-weight: bold; }
        .target { color: #ce9178; }
        .reason { color: #dcdcaa; font-style: italic; }
        .leaf { background: #2d2d2d; padding: 5px 10px; border-radius: 5px; display: inline-block; border-left: 3px solid #4ec9b0;}
        h2 { color: #dcdcaa; font-size: 1em; margin-top: 30px; }
        h1 { color: #4ec9b0; border-bottom: 1px solid #404040; padding-bottom: 10px;}
        .status { float: right; font-size: 0.5em; color: #888; }
    </style>
    <script>
        // Auto-refresh every 2 seconds to act as a live map
        setInterval(() => window.location.reload(), 2000);
    </script>
</head>
<body>
    <h1>🧠 Visor Strategy Tree <span class="status">Live Auto-refreshing...</span></h1>
    <ul>
        {{TREE_HTML}}
    </ul>
    {{SIDE_HTML}}
</body>
</html>
"""

def dict_to_html(d):
    # Branch text comes from web pages via the agent, so escape everything.
    html = ""
    for k, v in d.items():
        if not isinstance(v, dict):
            continue
        k = escape(str(k))
        if "action" in v:
            leaf = f'<div class="leaf"><span class="key">{k}</span> &rarr; <span class="action">action: {escape(str(v["action"]))}</span>'
            for field, css in (("target", "target"), ("reason", "reason"), ("proven_on", "status")):
                if field in v:
                    leaf += f' | <span class="{css}">{field}: "{escape(str(v[field]))}"</span>'
            html += f"<li>{leaf}</div></li>"
        else:
            html += f'<li><span class="key">{k}</span><ul>{dict_to_html(v)}</ul></li>'
    return html


def side_lists_html():
    """Fixes waiting for `visor tree --review`, and the latest ones that failed."""
    html = ""
    for title, name, note in (("Waiting for review", tree.PENDING, "proven_on"),
                              ("Recently rejected", tree.REJECTED, "why")):
        items = tree.load_side(name)[-10:]
        if not items:
            continue
        rows = "".join(
            f'<li><div class="leaf"><span class="key">{escape(str(i.get("branch", "")))}</span>'
            f' &rarr; <span class="action">{escape(str((i.get("fix") or {}).get("action", "")))}</span>'
            f' | <span class="reason">{escape(str(i.get(note) or (i.get("fix") or {}).get(note, "")))}</span></div></li>'
            for i in items)
        html += f"<h2>{title}</h2><ul>{rows}</ul>"
    return html


class TreeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        try:
            data = tree.load()
        except json.JSONDecodeError:
            data = {}  # tree.json mid-write; next refresh picks it up


        tree_html = dict_to_html(data)
        if not tree_html:
            tree_html = "<li>No strategy loaded yet.</li>"
            
        page = HTML_TEMPLATE.replace("{{TREE_HTML}}", tree_html).replace("{{SIDE_HTML}}", side_lists_html())
        self.wfile.write(page.encode('utf-8'))

    def log_message(self, format, *args):
        pass # Suppress logs to keep terminal clean

def serve(port: int = 8080):
    server = HTTPServer(("127.0.0.1", port), TreeHandler)
    print(f"[MAP SERVER] Live map of {tree.TREE_PATH} on http://localhost:{port} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
