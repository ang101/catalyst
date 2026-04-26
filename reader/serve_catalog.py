"""
Tiny HTTP server for the paper reader catalog.
Serves readers/ directory and handles POST /process to trigger pipeline.
Usage: python3 serve_catalog.py [port]
"""

import sys
import subprocess
import json
import urllib.parse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

BASE = Path("/home/hchadha1/.zeroclaw/workspace/paper-repro")
READERS_DIR = BASE / "reader/readers"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.lstrip("/").split("?")[0]
        if not path or path == "catalog.html":
            path = "catalog.html"
        file_path = READERS_DIR / path
        if file_path.exists() and file_path.is_file() and READERS_DIR in file_path.resolve().parents or file_path.resolve() == READERS_DIR / path:
            content_type = "text/html"
            if path.endswith(".json"):
                content_type = "application/json"
            elif path.endswith(".js"):
                content_type = "application/javascript"
            elif path.endswith(".css"):
                content_type = "text/css"
            self.send_response(200)
            self.send_header("Content-type", content_type)
            self.end_headers()
            self.wfile.write(file_path.read_bytes())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")

    def do_POST(self):
        if self.path == "/process":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode()
            params = urllib.parse.parse_qs(body)
            paper_id = params.get("arxiv_id", [""])[0].strip()

            if not paper_id:
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "no arxiv_id provided"}).encode())
                return

            def run_pipeline():
                try:
                    print(f"[pipeline] Starting: {paper_id}")
                    subprocess.run(
                        ["python3", str(BASE / "reader/run_pipeline.py"), paper_id],
                        check=True
                    )
                    print(f"[pipeline] Done: {paper_id}")
                except Exception as e:
                    print(f"[pipeline] Error for {paper_id}: {e}")

            threading.Thread(target=run_pipeline, daemon=True).start()

            self.send_response(202)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "processing",
                "paper_id": paper_id,
                "message": f"Pipeline started for {paper_id}. Refresh catalog in 60-120 seconds."
            }).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        print(f"[server] {args[0]}")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"Paper Reader Catalog Server")
    print(f"  URL: http://localhost:{port}/")
    print(f"  Readers: {READERS_DIR}")
    print(f"  POST /process with arxiv_id= to trigger pipeline")
    HTTPServer(("localhost", port), Handler).serve_forever()
