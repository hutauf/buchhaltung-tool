"""Loopback-only preview serving exactly the anonymous dashboard, no other files."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys
TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TOOL/"src"))
from autobookkeeping.workspace import data_root
ROOT = data_root()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/dashboard.html"):
            self.send_error(404); return
        data = (ROOT / "dashboard.html").read_bytes()
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(data)
    def log_message(self, *args):
        pass

if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 4181), Handler).serve_forever()
