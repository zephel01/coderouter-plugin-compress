"""before/after token measurement on headroom-style workloads.

Run: python scripts/bench.py
Prints char and (heuristic) token savings for representative tool outputs.
"""
from __future__ import annotations

import json

from coderouter_plugin_compress.config import CompressConfig
from coderouter_plugin_compress.metering import heuristic_tokens
from coderouter_plugin_compress.router import route_and_crush


def _code_search_results(n: int = 100) -> str:
    rows = [
        {
            "path": f"src/module_{i}/handler.py",
            "line": 100 + i,
            "match": "def handle_request(self, req):",
            "score": round(0.9 - i * 0.001, 4),
        }
        for i in range(n)
    ]
    return json.dumps(rows, indent=2)


def _sre_log(n: int = 400) -> str:
    lines = []
    for i in range(n):
        lines.append(f"2026-06-21 10:{i//60:02d}:{i%60:02d} INFO healthcheck ok seq={i} latency={i%30}ms")
    lines.insert(200, "2026-06-21 10:03:20 FATAL connection pool exhausted; aborting")
    return "\n".join(lines)


def _report(label: str, text: str) -> None:
    res = route_and_crush(text, CompressConfig())
    bt, at = heuristic_tokens(text), heuristic_tokens(res.text)
    saved = (1 - at / bt) * 100 if bt else 0
    print(
        f"{label:24s} crusher={res.crusher:5s} "
        f"tokens {bt:>7,} -> {at:>7,}  saved {saved:5.1f}%  changed={res.changed}"
    )


if __name__ == "__main__":
    print("=== coderouter-plugin-compress — before/after (heuristic tokens) ===")
    _report("code search (100)", _code_search_results(100))
    _report("SRE log (400 lines)", _sre_log(400))
    # Confirm the FATAL line survives.
    res = route_and_crush(_sre_log(400), CompressConfig())
    assert "FATAL connection pool exhausted" in res.text, "marker lost!"
    print("marker preservation: OK (FATAL line intact)")
