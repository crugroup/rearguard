# How to find out why a guard stayed silent

By design a guard prints nothing, writes nothing to stderr and exits 0 whenever it has no
reason to act or cannot do its job. To see the reason, run it with `REAR_GUARD_DEBUG=1`; the
cause goes to stderr.

Replay the event by hand. For the cache guard, use the session id and transcript path of the
session in question:

```bash
echo '{"session_id":"<id>","transcript_path":"<path>.jsonl"}' \
  | REAR_GUARD_DEBUG=1 hooks/cache-expiry-guard.py
```

If that prints nothing even with the variable set, the guard decided to let the prompt through.
Check, in order:

1. The last request of the transcript is less than an hour old (`TTL_SECONDS`).
2. The session holds fewer than 150k tokens (`MIN_CONTEXT`).
3. A block happened in the last 10 minutes, so this prompt counts as the override.
4. The transcript is not in Claude Code's JSON Lines format with compact separators. The guard
   pre-filters lines on the literal text `"type":"assistant"`.
5. `handoff.py` is not next to the hook. The guard then exits before doing anything. Run
   `./install` again, and check that the links in `~/.claude/hooks/` are not dangling.

For the archive guard, the usual causes are a partial read (`offset` or `limit`), the caller's
own session, a transcript under 200 kB, or a repeat within 30 minutes of the first denial.

If the hook never runs at all, the registration is wrong: compare it with
[install and register](install-and-register.md) and restart Claude Code.
