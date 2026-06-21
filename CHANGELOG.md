# Changelog

All notable changes to `coderouter-plugin-compress` are documented here.
Format loosely follows Keep a Changelog; versions follow SemVer.

## [0.2.0] — 2026-06-21

Initial public cut. Headroom-inspired context compression for CodeRouter,
shipped as standalone plugins. CodeRouter core is **not** modified — everything
plugs in via the `coderouter.input_filter` / `coderouter.observer` entry points.

### Added
- **Compression InputFilter (`compress`)** — compresses `tool_result` blocks
  before they reach the LLM. Pure-stdlib crushers:
  - `json` — array-of-objects → columnar table (key dedup) + whitespace minify.
  - `log` — exact-run and template-run folding; marker lines
    (FATAL/ERROR/Traceback/...) preserved verbatim.
  - `text` — conservative middle-elision for other large blocks.
- **CCR (Compressed-Context Reversibility)** — originals stashed locally by
  content hash (TTL / byte-cap / LRU). Deterministic re-expansion: a block is
  passed through uncompressed when a later turn echoes its `ccr_<id>` tag
  (`ccr_restore: explicit`, default).
- **CacheAligner InputFilter (`cache-align`, opt-in)** — marks Anthropic
  prompt-cache breakpoints on the system/tools prefix (≤4) and optional
  tool-order stabilization. Forwarded on the Anthropic-native route, dropped
  harmlessly elsewhere.
- **Stats Observer (`compress-stats`)** — per-request compression summary;
  optional accurate token metering via a local `tokenizer.json` (`accuracy`
  extra; no network / no torch / no pickle).
- Tests (47), a before/after `bench.py`, a real-CodeRouter `integration_test.py`,
  and a live harness (`scripts/live/`) plus a Mac+Ollama runner.

### Notes
- Core runtime dependencies: **none** (MVP crushers are pure stdlib).
- Optional extras: `accuracy` (tokenizers), `code` (tree-sitter, phase 4).
- Not yet done: phase 4 ML/AST compression; real paid-route cache-hit
  measurement (`cache_read_input_tokens`) on live Anthropic.
