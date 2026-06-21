# CCR — Compressed-Context Reversibility

Compression that can't be undone is dangerous: the moment the model needs a
detail you elided, the session is stuck. CCR makes compression **reversible**.

## Two halves

1. **Safety (phase 1).** Every compressed block's original is stashed locally,
   keyed by a content hash, in `CCRStore` (LRU + optional TTL + byte cap).
   Nothing is ever truly destroyed.
2. **Re-expansion (phase 2).** A previously compressed block can be restored to
   its original on demand, deterministically.

## The deterministic trick

CodeRouter is a **proxy**. The client (Claude Code) keeps its own copy of the
conversation, so **every turn it resends the original, uncompressed
`tool_result`**. We compress it on the way upstream and tag it:

```
…compressed table…
[coderouter-compress json: 1200->240 tok; full output id ccr_ab12cd34ef56aa01
 (reply "expand ccr_ab12cd34ef56aa01" to restore)]
```

The id is **`sha256(original)`** — a pure function of the content. So even
though we recompute it every turn from the resent original, the id is **stable
across turns**.

Flow:

1. **Turn N.** Block compressed; tagged with `ccr_ab12…`. The model sees the
   tag.
2. The model decides it needs the full output and writes `expand ccr_ab12…` in
   its reply. That reply flows back to the client.
3. **Turn N+1.** The client resends the original block *and* the assistant turn
   containing `expand ccr_ab12…`. We scan the inbound request for referenced
   ids; any `tool_result` whose `sha256` matches a referenced id is **passed
   through uncompressed** this turn.

```
referenced = ids found in every message's text   (ccr_[0-9a-f]{16})
for block in tool_results:
    if sha256(block.original) in referenced:
        pass through original        # restore
    else:
        compress + tag               # default
```

Properties:

- **Deterministic.** No heuristic "does the model seem to need it?" guesswork —
  zero false positives, zero misses.
- **No tool call required.** Works with local models that can't call tools; the
  model just echoes a token.
- **No persistent store needed for the explicit path.** Because the client
  resends the original, re-expansion is "skip compression," not "fetch from a
  database." (`CCRStore` still backs a future `coderouter_retrieve` MCP tool.)

## Configuration

```yaml
compress:
  ccr: true               # keep originals locally (default)
  ccr_restore: explicit   # explicit (default) re-expands on echoed id; off disables
```

## Where the id is scanned

`find_referenced_ids` looks in plain-string messages, `text` blocks, the text
inside `tool_result` blocks, and `tool_use` input values — so the model can
reference an id anywhere and still trigger restoration.

---

See also: [Architecture](./architecture.md) · [CacheAligner](./CACHE_ALIGNER.md) · [README](../README.md)
