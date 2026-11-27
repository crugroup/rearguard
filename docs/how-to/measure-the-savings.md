# How to measure what the cache guard saved

The guard logs to `~/.claude/cache-guard/events.jsonl`. A `README.md` next to it, rewritten by
the hook, explains every field and the cost model.

Count blocks and overrides:

```bash
jq -s 'group_by(.event) | map({event: .[0].event, count: length})' ~/.claude/cache-guard/events.jsonl
```

Estimate the tokens saved. For each `block`, an `override` of the same `session_id` before the
session's next `block` means the context was re-bought and nothing was saved. A block with no
override saved about `2 * tokens - start_cost` input-token equivalents.

```bash
jq -s '
  (map(select(.event == "override").session_id) | unique) as $overridden |
  map(select(.event == "block" and ((.session_id | IN($overridden[])) | not)))
  | map(2 * .tokens - .start_cost) | add // 0
' ~/.claude/cache-guard/events.jsonl
```

This is an upper bound: some blocked prompts would never have been sent. It also ignores the
"before the next block" rule, so a session blocked twice counts once overridden. The
[event log reference](../reference/event-log.md) lists the limits.
