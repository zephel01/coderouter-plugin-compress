# coderouter-plugin-compress

Headroom-inspired **context compression** for CodeRouter. A pure-stdlib
`InputFilter` plugin that compresses `tool_result` blocks (JSON / log) before
they reach the LLM — "same answers, fewer tokens".

- **Opt-in.** Only activates when `compress` is listed in `plugins.enabled`.
- **Zero core dependencies.** MVP crushers are pure Python. Precise token
  metering (`accuracy`) and AST code compression (`code`) are optional extras.
- **Safe by default.** Any crusher error leaves the block untouched; `mode: off`
  is an exact pass-through.
- **Reversible (CCR).** Originals are kept locally, keyed by content hash.

## Install

```bash
pip install -e .              # core (pure stdlib)
pip install -e ".[accuracy]"  # + local-tokenizer metering (CJK-correct)
```

## Enable in CodeRouter (`providers.yaml`)

```yaml
plugins:
  enabled: [compress, compress-stats]
  config:
    compress:
      mode: safe                # off | safe | aggressive
      min_block_tokens: 200
      targets: [tool_result]
      crushers: [json, log, text]
      ccr: true
      metering:
        tokenizer_path: ~/.coderouter/tokenizers/sonnet.json  # optional
```

## What it compresses

| Crusher | Target | Technique |
|---|---|---|
| `json` | JSON tool output | array-of-objects → columnar table (key dedup) + whitespace minify |
| `log`  | logs / stack traces | exact-run + template-run folding; **marker lines kept verbatim** |
| `text` | other long blocks | conservative middle-elision, markers preserved |

## Test & benchmark

```bash
PYTHONPATH=tests python -m pytest -q
python scripts/bench.py
```

## CCR re-expansion (Phase 2)

Each compressed block is tagged with a content-hash id `ccr_<hex>` and a hint:
`reply "expand ccr_<hex>" to restore`. When a later turn echoes that id, the
block is passed through **uncompressed** that turn — deterministic, no false
positives, works with local models (no tool call needed). Toggle with
`ccr_restore: explicit | off` (default `explicit`).

## CacheAligner (Phase 3)

A second, independent InputFilter (`cache-align`, **opt-in**) that marks
Anthropic prompt-cache breakpoints and optionally stabilizes the prefix —
implemented as a plugin filter, so CodeRouter core is never modified. On the
Anthropic-native paid route the `cache_control` markers are forwarded and the
big stable system+tools prefix is cached; on OpenAI/local routes they are
dropped harmlessly in translation.

```yaml
plugins:
  enabled: [compress, compress-stats, cache-align]
  config:
    cache-align:
      inject_cache_control: true    # ephemeral breakpoints on system + tools tails
      cache_system: true
      cache_tools: true
      stabilize_tools_order: false  # higher risk; off by default
      max_breakpoints: 4            # Anthropic hard limit
```

Status: Phases 0–3 complete. All implemented as plugins; CodeRouter core
unmodified. See `../2026-06-21_headroom統合計画_v2.md` for the roadmap.

MIT License.
