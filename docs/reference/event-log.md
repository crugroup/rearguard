# Event log reference

`~/.claude/cache-guard/events.jsonl`, written by `cache-expiry-guard.py`: one JSON object per
line, oldest first. A `README.md` next to it, rewritten by the hook whenever it differs, carries
the same field descriptions and the cost model for whoever reads the log later.

Every event has `v` (schema version, `1`), `ts` (UTC, ISO 8601), `event` and `session_id`.

## `block`

The hook held the first prompt of a large session whose cache had expired.

| Field | Meaning |
|---|---|
| `tokens` | Context size of the session's last request |
| `idle_s` | Seconds since that request |
| `start_cost` | Estimated input-token equivalents to start a new session |
| `start_baseline` | Tokens such a session starts with |
| `start_cached` | Part of that another session keeps cached, 0 if none |
| `start_estimated` | `true` when no first request was found and `FALLBACK_BASELINE` was used |

## `override`

A prompt arrived within the grace period after a block, so it went through.

| Field | Meaning |
|---|---|
| `since_block_s` | Seconds between the block and that prompt |

## Size and failures

When an event would take the file past `MAX_LOG_BYTES`, the oldest half is dropped at a line
boundary and the file is replaced atomically. An event larger than half the cap is dropped. A
log that cannot be written never stops a block.

## Limits of the figures

They are estimates, not billed amounts. The hook cannot tell a new session from an abandoned
one, and some blocked prompts would never have been sent, so a computed saving is an upper bound.
To compute it, see [measure what the guard saved](../how-to/measure-the-savings.md).
