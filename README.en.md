# coderouter-plugin-compress

[![CI](https://github.com/zephel01/coderouter-plugin-compress/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/zephel01/coderouter-plugin-compress/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![runtime deps](https://img.shields.io/badge/runtime%20deps-0-brightgreen)
![license](https://img.shields.io/badge/license-MIT-yellow)

[日本語](./README.md) · **English** · [CodeRouter](https://github.com/zephel01/CodeRouter) · sibling plugin: [coderouter-plugin-memory](https://github.com/zephel01/coderouter-plugin-memory) · upstream inspiration: [headroom](https://github.com/chopratejas/headroom)

Headroom-inspired **context compression** for CodeRouter. A pure-stdlib
`InputFilter` plugin that compresses `tool_result` blocks (JSON / log) before
they reach the LLM — "same answers, fewer tokens".

- **Opt-in.** Only activates when `compress` is listed in `plugins.enabled`.
- **Zero core dependencies.** MVP crushers are pure Python. Precise token
  metering (`accuracy`) and AST code compression (`code`) are optional extras.
- **Safe by default.** Any crusher error leaves the block untouched; `mode: off`
  is an exact pass-through.
- **Reversible (CCR).** Originals are kept locally, keyed by content hash.

**Docs:** [Architecture](docs/architecture.md) · [CCR (reversible compression)](docs/CCR.md) · [CacheAligner](docs/CACHE_ALIGNER.md)

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
python -m pytest -q                 # unit tests (47)
python scripts/bench.py             # before/after token savings
python scripts/integration_test.py  # against real CodeRouter (needs: pip install coderouter-cli)
python scripts/live/run_live.py     # real `coderouter serve` + stub upstream
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
unmodified. Phase 4 (optional ML/AST compression) is not started.

## Relationship to CodeRouter

This is a standalone, independently-versioned plugin for
[CodeRouter](https://github.com/zephel01/CodeRouter). It does not import
CodeRouter at runtime — it only attaches via the `coderouter.input_filter` /
`coderouter.observer` entry points, and activates only when listed in
`plugins.enabled`. Integration and live tests install `coderouter-cli` to
exercise the real engine.

## Related

| Project | Role |
|---|---|
| [CodeRouter](https://github.com/zephel01/CodeRouter) | The wire-layer router that hosts this plugin (required). |
| [coderouter-plugin-memory](https://github.com/zephel01/coderouter-plugin-memory) | Sibling plugin — cross-session memory injected at the wire layer. Composes cleanly with `compress`. |
| [headroom](https://github.com/chopratejas/headroom) | Upstream inspiration for the compression / CCR / cache-alignment ideas. |

MIT License.
