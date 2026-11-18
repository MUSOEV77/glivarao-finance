"""Local stand-in for the Telegram Bot API (testing only). Records each call (method, bytes received,
filenames) to calls.jsonl and serves queued getUpdates from updates.json. Never contacts Telegram."""
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LOG = Path(sys.argv[2] if len(sys.argv) > 2 else "fake_telegram_calls.jsonl")
UPDATES = LOG.with_name("updates.json")
COUNTER = {"n": 100}


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        method = self.path.rsplit("/", 1)[-1]
        files = re.findall(rb'filename="([^"]+)"', body)
        with LOG.open("a") as fh:
            fh.write(json.dumps({"method": method, "bytes": n, "files": [f.decode() for f in files]}) + "\n")
        if method == "getUpdates":
            res = json.loads(UPDATES.read_text()) if UPDATES.exists() else []
            UPDATES.write_text("[]")
        else:
            COUNTER["n"] += 1
            res = {"message_id": COUNTER["n"]}
        out = json.dumps({"ok": True, "result": res}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
