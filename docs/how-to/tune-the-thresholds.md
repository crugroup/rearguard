# How to tune the thresholds

The limits are constants at the top of each hook. Edit them in your clone; the links make the
change live after the next Claude Code restart.

| To change | Edit | In |
|---|---|---|
| The cache lifetime your setup uses (for example 5 minutes) | `TTL_SECONDS` | `cache-expiry-guard.py` |
| The smallest session worth guarding | `MIN_CONTEXT` | `cache-expiry-guard.py` |
| How long a resend counts as an override | `GRACE_SECONDS` | `cache-expiry-guard.py` |
| How large the event log may grow | `MAX_LOG_BYTES` | `cache-expiry-guard.py` |
| The smallest transcript worth redirecting | `MIN_BYTES` | `archive-read-guard.py` |
| How long a repeated read stays allowed | `GRACE_SECONDS` | `archive-read-guard.py` |

Set `TTL_SECONDS` to the lifetime your requests really use. If it is longer than the real one,
the guard fires late; if shorter, it fires on sessions whose cache is still warm. Meaning and
defaults are in the [hooks reference](../reference/hooks.md).
