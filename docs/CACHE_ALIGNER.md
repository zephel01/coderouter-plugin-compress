# CacheAligner

`cache-align` is a second, independent `InputFilter` (opt-in) that helps the
provider's KV cache actually hit. It does two things, both operating on the
inbound `AnthropicRequest`:

1. **Prompt-cache breakpoint injection** (default on when enabled) — adds an
   `ephemeral` `cache_control` marker at the end of the stable prefix (the
   system prompt and/or the tools array).
2. **Prefix stabilization** (default off — higher risk) — sorts tool
   definitions by name so the prefix is byte-identical across turns, which also
   helps server-side prefix caches on llama.cpp / Ollama.

## Why it matters

A provider's KV cache only hits when the prompt **prefix matches exactly**.
Claude Code resends a 15–20k-token system prompt every turn; if that prefix is
cached, the paid-route prefill cost and latency drop sharply. CacheAligner marks
where the stable prefix ends so the provider can cache it.

## Route behavior (safe everywhere)

- **Anthropic-native (paid) route.** The native adapter sends
  `req.model_dump(exclude_none=True)` straight to `api.anthropic.com`, so the
  injected `cache_control` markers are forwarded and prompt caching engages.
- **OpenAI-compat / local routes.** The Anthropic→OpenAI translation flattens
  content and drops `cache_control` (it isn't an OpenAI field). Harmless no-op.

So enabling `cache-align` is safe on every route — it only takes effect where
the provider supports it.

## Breakpoint budget

Anthropic allows at most **4** cache breakpoints. The filter clamps
`max_breakpoints` to that and spends the budget on the tools tail first, then
the system tail.

## Implementation notes

- `system` as a string is wrapped into `[{"type":"text","text":…,"cache_control":…}]`.
- `system` as a list gets the marker on its last block.
- Tools keep their original `AnthropicTool` type (added via `model_copy`) so the
  adapter's `model_dump` serializes them without a pydantic warning.
- The original request is never mutated; exceptions degrade to pass-through.

## Configuration

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

## Not yet verified

Real cache-hit measurement on a live paid Anthropic route
(`cache_creation_input_tokens` / `cache_read_input_tokens`) hasn't been done —
it needs a billed API key. The injection and forwarding are confirmed via
`model_dump` in the integration test.

---

See also: [Architecture](./architecture.md) · [CCR](./CCR.md) · [README](../README.md)
