# Tutorial: watch the cache guard block a prompt

You will fake an expired, large session in a throwaway directory, send the cache guard the
event Claude Code would send, and read what it does. It takes five minutes, needs only
Python 3.9+, and touches nothing in your real `~/.claude`.

Run all commands from the root of the repository, in one shell.

## 1. Make a scratch home

```bash
export DEMO=$(mktemp -d)
mkdir -p "$DEMO/.claude/projects/demo"
```

Every command below sets `HOME=$DEMO`, so the hook reads and writes there.

## 2. Write a session that has gone cold

This transcript says the session's last request held 200,000 tokens and ended two hours ago,
past the one-hour cache lifetime.

```bash
python3 - <<'PY'
import json, os, datetime as d
stamp = (d.datetime.now(d.timezone.utc) - d.timedelta(hours=2)).isoformat()
lines = [
    {"type": "user", "timestamp": stamp, "cwd": "/work", "message": {"content": "Fix the build"}},
    {"type": "assistant", "timestamp": stamp, "message": {
        "content": [{"type": "text", "text": "Fixed."}],
        "usage": {"input_tokens": 200000, "cache_read_input_tokens": 0}}},
]
path = os.environ["DEMO"] + "/.claude/projects/demo/demo.jsonl"
with open(path, "w") as f:
    f.write("\n".join(json.dumps(line, separators=(",", ":")) for line in lines) + "\n")
PY
```

## 3. Send the prompt event

Claude Code gives a `UserPromptSubmit` hook the session id and the transcript path on stdin.
Do the same:

```bash
EVENT="{\"session_id\":\"demo\",\"transcript_path\":\"$DEMO/.claude/projects/demo/demo.jsonl\"}"
echo "$EVENT" | HOME=$DEMO hooks/cache-expiry-guard.py
```

The guard prints one line of JSON: `"decision": "block"` and a `reason` saying the cache expired
2.0 h ago, that continuing costs about 400k input-token equivalents, and that a new session
costs about the same here. Claude Code would show that reason instead of sending your prompt.

## 4. Open the handoff note it wrote

The reason ends with a path under `$DEMO/.claude/handoffs/`.

```bash
cat "$DEMO"/.claude/handoffs/*.md
```

It holds the first prompt ("Fix the build"), the last reply and the transcript path. This is
what you would start a new session from.

## 5. Resend

```bash
echo "$EVENT" | HOME=$DEMO hooks/cache-expiry-guard.py; echo "exit $?"
```

Nothing is printed and the exit code is 0: a prompt within 10 minutes of a block goes through,
so a resend continues the old session.

## 6. Read the log

```bash
cat "$DEMO/.claude/cache-guard/events.jsonl"
```

Two lines: a `block`, then an `override`. This is the record you would use to
[measure what the guard saved](../how-to/measure-the-savings.md).

## Clean up

```bash
rm -rf "$DEMO"; unset DEMO
```

You have seen the guard's whole cycle. To use it for real, [install and register
it](../how-to/install-and-register.md). To see why it behaves this way, read [why the guards
exist](../explanation/why-the-guards-exist.md).
