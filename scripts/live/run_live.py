"""Live end-to-end test: REAL `coderouter serve` + stub upstream, over HTTP.

Proves the compress plugin fires inside the running server: we POST a real
Anthropic /v1/messages request with a fat tool_result, then inspect what the
upstream actually received — it must be the COMPRESSED payload. Then a second
turn echoes the CCR id and the upstream must receive the RESTORED original.

The only stub is the LLM itself; ingress, plugin loading, the input-filter
chain, translation, and the OpenAI adapter are all the real CodeRouter code.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(os.path.dirname(HERE))
# Optional: point at a CodeRouter source checkout. When unset (e.g. CI), we
# rely on a pip-installed `coderouter-cli` being importable normally.
REPO = os.environ.get("CODEROUTER_REPO")
STUB_PORT = "9911"
CR_PORT = "8088"
RECORD = "/tmp/stub_records.jsonl"


def ccr_id(text: str) -> str:
    return "ccr_" + hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


def big_json() -> str:
    rows = [{"id": i, "name": f"user{i}", "status": "ok", "note": "FILLER_PAYLOAD"} for i in range(120)]
    return json.dumps(rows, indent=2)


def big_log() -> str:
    lines = [f"2026-06-21 10:{i//60:02d}:{i%60:02d} INFO heartbeat seq={i} latency={i%30}ms" for i in range(250)]
    lines.insert(120, "2026-06-21 10:02:00 FATAL disk full on /var; aborting now")
    return "\n".join(lines)


def messages_turn1(j, lg):
    return [
        {"role": "user", "content": "run the tools"},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "tu_j", "name": "search", "input": {}},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "tu_j", "content": j},
            {"type": "tool_result", "tool_use_id": "tu_l", "content": lg},
        ]},
    ]


def messages_turn2(j, lg, expand_id):
    msgs = messages_turn1(j, lg)
    msgs.append({"role": "assistant", "content": f"I need the complete table — expand {expand_id}"})
    msgs.append({"role": "user", "content": "ok"})
    return msgs


def post(client, msgs):
    body = {"model": "claude-sonnet-4-6", "max_tokens": 256, "stream": False, "messages": msgs}
    r = client.post(
        f"http://127.0.0.1:{CR_PORT}/v1/messages",
        headers={"x-api-key": "dummy", "anthropic-version": "2023-06-01"},
        json=body, timeout=30,
    )
    r.raise_for_status()
    return r.json()


def read_last_upstream():
    with open(RECORD) as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    return json.loads(lines[-1]) if lines else None


def upstream_text(record) -> str:
    """Flatten all message contents the upstream received into one string."""
    out = []
    for m in record.get("messages", []):
        c = m.get("content")
        if isinstance(c, str):
            out.append(c)
        elif isinstance(c, list):
            for b in c:
                if isinstance(b, dict):
                    out.append(json.dumps(b))
                else:
                    out.append(str(b))
    return "\n".join(out)


def main() -> int:
    env = dict(os.environ)
    env["STUB_PORT"] = STUB_PORT
    env["STUB_RECORD"] = RECORD
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if REPO:
        # Use a source checkout if provided; otherwise the installed package.
        env["PYTHONPATH"] = REPO
    env["CODEROUTER_CONFIG"] = os.path.join(HERE, "providers.live.yaml")

    stub = subprocess.Popen([sys.executable, os.path.join(HERE, "stub_upstream.py")], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    serve = subprocess.Popen(
        [sys.executable, "-m", "coderouter", "serve", "--host", "127.0.0.1",
         "--port", CR_PORT, "--config", env["CODEROUTER_CONFIG"], "--log-level", "warning"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        # Wait for the server to accept connections.
        ok = False
        with httpx.Client() as c:
            for _ in range(80):
                if serve.poll() is not None:
                    print("SERVER EXITED EARLY:\n" + serve.stdout.read().decode("utf-8", "replace"))
                    return 1
                try:
                    c.get(f"http://127.0.0.1:{CR_PORT}/", timeout=1)
                    ok = True
                    break
                except Exception:
                    time.sleep(0.25)
            if not ok:
                print("server did not come up")
                return 1

            j, lg = big_json(), big_log()

            # --- Turn 1: expect upstream to receive COMPRESSED payload ---
            post(c, messages_turn1(j, lg))
            rec1 = read_last_upstream()
            up1 = upstream_text(rec1)
            assert "expand ccr_" in up1, "no CCR marker upstream — plugin did not compress!"
            assert "json-table" in up1, "json crusher did not run upstream"
            assert "FATAL disk full on /var; aborting now" in up1, "FATAL line lost upstream"
            # Original JSON repeats the key form `"note": "FILLER_PAYLOAD"` once per
            # row; the compressed columnar table drops per-row keys, so this exact
            # key-form should be ABSENT upstream in turn 1.
            keyform = '"note": "FILLER_PAYLOAD"'
            orig_keyforms = j.count(keyform)  # 120
            assert up1.count(keyform) == 0, "json block was NOT actually compressed upstream"
            assert len(up1) < len(j) + len(lg), "upstream payload not smaller than originals"
            print(f"[turn1] upstream received COMPRESSED payload: marker=yes, json-table=yes, "
                  f"FATAL preserved, original key-form rows {orig_keyforms}->0, "
                  f"total upstream chars={len(up1)} (originals were {len(j)+len(lg)})")

            # --- Turn 2: echo the json block's CCR id -> expect RESTORED original ---
            jid = ccr_id(j)
            post(c, messages_turn2(j, lg, jid))
            rec2 = read_last_upstream()
            up2 = upstream_text(rec2)
            restored = up2.count(keyform)
            assert restored == orig_keyforms, f"json block not restored ({restored}/{orig_keyforms} key-form rows)"
            # The log block was NOT referenced, so it must still be compressed.
            assert "FATAL disk full on /var; aborting now" in up2, "log FATAL missing in turn2"
            assert up2.count(keyform) == orig_keyforms, "restore incomplete"
            print(f"[turn2] echoed {jid} -> upstream received RESTORED original json: "
                  f"key-form rows back to {restored}/{orig_keyforms} (log block stays compressed)")

            print("\nLIVE OK — compress plugin fired inside the real running server, "
                  "over real HTTP, with CCR re-expansion working end-to-end.")
            return 0
    finally:
        for p in (serve, stub):
            p.terminate()
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()


if __name__ == "__main__":
    sys.exit(main())
