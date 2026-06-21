"""Minimal OpenAI-compatible stub upstream for the live test.

Stands in for a real local LLM (llama.cpp / Ollama) so we can run the REAL
`coderouter serve` process end-to-end without GPUs or model downloads. It:
  - GET  /v1/models            -> advertises one model (probes/health)
  - POST /v1/chat/completions  -> records the request body to RECORD_PATH and
                                  returns a minimal valid chat completion.

The recorded body is what CodeRouter actually sent upstream AFTER the
compress plugin ran — that's the artifact the live test inspects.
"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RECORD_PATH = os.environ.get("STUB_RECORD", "/tmp/stub_records.jsonl")
PORT = int(os.environ.get("STUB_PORT", "9911"))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list", "data": [{"id": "stub-model", "object": "model"}]})
        else:
            self._json(200, {"ok": True})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw)
        except Exception:
            body = {"_unparsed": raw.decode("utf-8", "replace")}

        with open(RECORD_PATH, "a") as f:
            f.write(json.dumps(body) + "\n")

        resp = {
            "id": "chatcmpl-stub",
            "object": "chat.completion",
            "created": 0,
            "model": body.get("model", "stub-model"),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ack from stub upstream"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
        }
        self._json(200, resp)

    def _json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    open(RECORD_PATH, "w").close()  # truncate
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"stub upstream on :{PORT}, recording -> {RECORD_PATH}", file=sys.stderr)
    srv.serve_forever()
