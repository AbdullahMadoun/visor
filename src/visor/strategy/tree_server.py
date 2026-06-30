import json
import os
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
</body>
</html>
"""

def dict_to_html(d):
    html = ""
    for k, v in d.items():
        if isinstance(v, dict):
            if "action" in v:
                # Leaf node
                leaf_str = f'<div class="leaf"><span class="key">{k}</span> &rarr; <span class="action">action: {v["action"]}</span>'
                if "target" in v:
                    leaf_str += f' | <span class="target">target: "{v["target"]}"</span>'
                if "reason" in v:
                    leaf_str += f' | <span class="reason">reason: "{v["reason"]}"</span>'
                leaf_str += '</div>'
                html += f"<li>{leaf_str}</li>"
            else:
                html += f'<li><span class="key">{k}</span><ul>{dict_to_html(v)}</ul></li>'
    return html

class TreeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        tree_path = os.path.join(os.path.dirname(__file__), "tree.json")
        data = {}
        if os.path.exists(tree_path):
            with open(tree_path) as f:
                data = json.load(f)
                
        tree_html = dict_to_html(data)
        if not tree_html:
            tree_html = "<li>No strategy loaded yet.</li>"
            
        page = HTML_TEMPLATE.replace("{{TREE_HTML}}", tree_html)
        self.wfile.write(page.encode('utf-8'))

    def log_message(self, format, *args):
        pass # Suppress logs to keep terminal clean

if __name__ == "__main__":
    port = 8080
    server = HTTPServer(('localhost', port), TreeHandler)
    print(f"[MAP SERVER] Running live map on http://localhost:{port}")
    server.serve_forever()
