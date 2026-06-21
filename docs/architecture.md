# Architecture

`coderouter-plugin-compress` attaches to CodeRouter purely through its plugin
SDK — it never imports CodeRouter at runtime and never modifies CodeRouter
core. Everything is an opt-in plugin discovered via entry points.

## Where it sits

```
 Claude Code / Cline / any Anthropic client
        │  POST /v1/messages  (full history every turn, originals included)
        ▼
 ┌──────────────── CodeRouter ────────────────┐
 │  ingress → tool-loop guard                  │
 │            → InputFilter chain  ◄───────────┼── compress  (this plugin)
 │            → context-budget guard           │   cache-align (this plugin)
 │            → chain dispatch                 │
 │            → translation (Anthropic↔OpenAI) │
 │            → adapter (native / openai_compat)│
 └──────────────────────┬──────────────────────┘
                         ▼
        LLM backend (Ollama / llama.cpp / OpenRouter / Anthropic)
```

The engine runs `InputFilter.transform(request)` **after** the tool-loop guard
and **before** the context-budget guard. That ordering matters: compression
shrinks `tool_result` blocks first, and only what still overflows is trimmed by
the budget guard. "Shrink before you drop."

## Components

| Module | Role |
|---|---|
| `filter.py` (`CompressInputFilter`) | Walks the request, compresses qualifying `tool_result` blocks, handles CCR re-expansion. |
| `router.py` (`route_and_crush`) | ContentRouter: detects content type, dispatches to a crusher. |
| `crushers/json_crush.py` | Array-of-objects → columnar table (key dedup) + whitespace minify. |
| `crushers/log_crush.py` | Exact-run + template-run folding; marker lines preserved verbatim. |
| `crushers/text_crush.py` | Conservative middle-elision for other large blocks. |
| `ccr.py` (`CCRStore`, `find_referenced_ids`) | Content-addressed original store + CCR-id scanning for re-expansion. |
| `cache_aligner.py` (`CacheAlignInputFilter`) | Anthropic prompt-cache breakpoint injection + optional prefix stabilization. |
| `metering.py` | char/4 token estimate, optional accurate count via local `tokenizer.json`. |
| `stats.py` / `observer.py` | Process-wide compression stats + a `request_completed` reporter. |

## Design principles

1. **Zero core dependencies.** MVP crushers are pure stdlib. Precise metering
   (`accuracy`) and AST code compression (`code`) are optional extras. This
   mirrors CodeRouter's own 5-dependency discipline.
2. **Opt-in.** Nothing runs unless the entry-point name is in `plugins.enabled`
   — CodeRouter's supply-chain defense.
3. **Degrade, never disrupt.** Any crusher exception leaves the block untouched;
   `mode: off` is an exact pass-through. The engine is never blocked.
4. **Immutable requests.** Filters return a new request via `model_copy`; the
   input is never mutated.
5. **Reversible.** Compression keeps originals locally (CCR) so nothing is
   destroyed.

## Why a plugin, not a core patch

CodeRouter's loader is explicitly built for `coderouter-plugin-*` packages: an
installed-but-unlisted plugin is skipped, and only an explicit `plugins.enabled`
entry activates it. The `InputFilter` hook receives the full `AnthropicRequest`,
which is everything these features need — compression, CCR, and even
`cache_control` injection all operate on that object. So the entire feature set
lands without touching a single line of CodeRouter core.

See also: [CCR.md](./CCR.md), [CACHE_ALIGNER.md](./CACHE_ALIGNER.md).
