#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""UserPromptSubmit hook: hold the first prompt sent to a large, cache-expired session.

Prompts are cached for one hour after the last request. Past that, the next request
writes the whole context to the cache again at twice the input price. This hook
blocks that prompt once and says what it would cost. Any prompt sent within
GRACE_SECONDS after the block goes through, so a resend continues the session.

Each block, and each prompt that goes through after one, is appended to
~/.claude/cache-guard/events.jsonl, so that the tokens the hook saves can be counted later.
The log never grows past MAX_LOG_BYTES; README.md next to it says how to read it.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # handoff.py sits next to this
try:
    from handoff import write_handoff
except Exception:  # installed without handoff.py: nothing to offer, stay out of the way
    sys.exit(0)

TTL_SECONDS = 60 * 60  # one-hour prompt cache
MIN_CONTEXT = 150_000  # below this, resuming costs about a fresh session's baseline
FALLBACK_BASELINE = 75_000  # typical starting context when the transcript gives none
GRACE_SECONDS = 10 * 60
TAIL_BYTES = 8 * 1024 * 1024
STATE_DIR = Path("~/.claude/cache-guard").expanduser()
LOG_FILE = STATE_DIR / "events.jsonl"
LOG_README = STATE_DIR / "README.md"
MAX_LOG_BYTES = 25 * 1024 * 1024  # the log is trimmed to its newest half when it would pass this

LOG_README_TEXT = """\
# cache-guard event log

Written by `cache-expiry-guard.py` (rear-guard). `events.jsonl` has one JSON
object per line, oldest first. It is trimmed to its newest half whenever it would pass 25 MiB,
so the oldest events disappear first. This file is rewritten by the hook; do not edit it.

## Events

Every event has `v` (schema version, 1), `ts` (UTC, ISO 8601), `event` and `session_id`.

- `block`: the hook held the first prompt of a large session whose prompt cache had expired.
  `tokens`: context size of the session's last request. `idle_s`: seconds since that request.
  `start_cost`: estimated input-token equivalents to start a new session instead.
  `start_baseline`: tokens such a session starts with. `start_cached`: part of it another
  session keeps cached (0 if none). `start_estimated`: true when no first request was found
  and a fixed guess was used.
- `override`: a prompt arrived within the grace period after a block, so it went through and
  the session continued. `since_block_s`: seconds between the block and that prompt.

## Cost model

Input-token equivalents: a cache write costs 2x a normal input token, a cache read 0.1x.

- Continuing an expired session writes its whole context again: about `2 * tokens`, then
  `tokens / 10` for every later call.
- Starting fresh costs `start_cost`, then `start_baseline / 10` per call.

## Estimating what the hook saved

For each `block`, look for an `override` of the same `session_id` after it and before the
session's next `block` (if any).

- Overridden: saved about 0. The prompt was sent anyway and the cost was paid.
- Not overridden: the user did not continue in that session, which probably means a new one,
  saved about `2 * tokens - start_cost`.

To check the model, find the first request of an overridden session after the block in
`~/.claude/projects/*/<session_id>.jsonl`: its `cache_creation_input_tokens` should be close to
`tokens`.

## Limits

These are estimates, not billed amounts. Some blocked prompts would never have been sent, so
the saving is an upper bound. The hook cannot tell a new session from an abandoned one. A
second block of the same session means the first one got no override.
"""


def request_usage(raw: bytes) -> tuple[str | None, int, int] | None:
    """Return (timestamp, context tokens, cache-read tokens) of a main-chain request line."""
    if b'"type":"assistant"' not in raw:
        return None
    try:
        record = json.loads(raw)
    except ValueError:
        return None
    if record.get("isSidechain"):
        return None
    usage = (record.get("message") or {}).get("usage") or {}
    parts = usage.get("iterations") or [usage]
    read = sum(p.get("cache_read_input_tokens") or 0 for p in parts)
    tokens = read + sum(
        (p.get("input_tokens") or 0) + (p.get("cache_creation_input_tokens") or 0)
        for p in parts
    )
    return (record.get("timestamp"), tokens, read) if tokens else None


def last_request(transcript: Path) -> tuple[float, int] | None:
    """Return (epoch seconds, context tokens) of the transcript's last API request."""
    with transcript.open("rb") as f:
        size = f.seek(0, 2)
        f.seek(max(0, size - TAIL_BYTES))
        lines = f.read().splitlines()
    for stamp, tokens, _ in filter(None, map(request_usage, reversed(lines))):
        if stamp:
            return datetime.fromisoformat(stamp).timestamp(), tokens
    return None


def first_request(transcript: Path) -> tuple[int, int] | None:
    """Return (context tokens, cache-read tokens) of the transcript's first API request.

    Its context is what a new session of the same preset starts with; its cache read
    is the prefix (system prompt, tools) that sessions share.
    """
    with transcript.open("rb") as f:
        found = next(filter(None, map(request_usage, f)), None)
    return found[1:] if found else None


def shared_cache_warm(transcript: Path) -> bool:
    """Whether another session sent a request within the TTL, keeping the shared prefix cached."""
    cutoff = time.time() - TTL_SECONDS
    for other in transcript.parent.parent.glob("*/*.jsonl"):
        try:
            if other != transcript and other.stat().st_mtime > cutoff:
                return True
        except OSError:
            continue
    return False


def start_estimate(transcript: Path) -> tuple[int, int, int, bool]:
    """Estimate (cost, baseline, cached, estimated) of a new session, in input-token equivalents."""
    found = first_request(transcript)
    if not found:
        return 2 * FALLBACK_BASELINE, FALLBACK_BASELINE, 0, True
    baseline, prefix = found
    cached = prefix if prefix and shared_cache_warm(transcript) else 0
    return 2 * (baseline - cached) + cached // 10, baseline, cached, False


def start_cost(transcript: Path) -> str:
    """Say, in input-token equivalents, what a new session costs to start."""
    cost, baseline, cached, estimated = start_estimate(transcript)
    if estimated:
        return f"about {cost // 1000}k (estimated, no first request found)"
    how = (f"{cached // 1000}k of it a prefix another session keeps cached" if cached
           else "all written to a cold cache")
    return f"about {cost // 1000}k (it starts at {baseline // 1000}k, {how}), then {baseline // 10_000}k per call"


def log_event(event: dict) -> None:
    """Append one event to the log, trimming it first if it would pass MAX_LOG_BYTES.

    Never raises: a metrics failure must not cost the user the block.
    """
    try:
        record = {"v": 1, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **event}
        line = (json.dumps(record, separators=(",", ":")) + "\n").encode()
        if len(line) > MAX_LOG_BYTES // 2:
            return
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        if not LOG_README.is_file() or LOG_README.read_text() != LOG_README_TEXT:
            LOG_README.write_text(LOG_README_TEXT)
        size = LOG_FILE.stat().st_size if LOG_FILE.exists() else 0
        if size + len(line) > MAX_LOG_BYTES:
            trim_log(MAX_LOG_BYTES // 2)
        with LOG_FILE.open("ab") as f:
            f.write(line)
    except Exception:  # noqa: BLE001
        if os.environ.get("REAR_GUARD_DEBUG"):
            sys.stderr.write("cache-expiry-guard: could not write the event log\n")


def trim_log(keep: int) -> None:
    """Keep the newest `keep` bytes of the log, from a line boundary, replacing it atomically."""
    with LOG_FILE.open("rb") as f:
        size = f.seek(0, 2)
        f.seek(max(0, size - keep))
        tail = f.read()
    if size > keep:
        tail = tail.partition(b"\n")[2]  # drop the line the cut went through
    temp = LOG_FILE.with_suffix(f".tmp{os.getpid()}")
    try:
        temp.write_bytes(tail)
        os.replace(temp, LOG_FILE)
    finally:
        temp.unlink(missing_ok=True)


def decide(event: dict) -> dict | None:
    """Return the hook output that blocks the prompt, or None to let it through."""
    transcript = Path(event.get("transcript_path") or "")
    if not transcript.is_file():
        return None
    found = last_request(transcript)
    if not found:
        return None
    when, tokens = found
    idle = time.time() - when
    if idle < TTL_SECONDS or tokens < MIN_CONTEXT:
        return None

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    marker = STATE_DIR / f"{event.get('session_id') or 'unknown'}.blocked"
    caller = str(event.get("session_id") or "unknown")[:200]
    if marker.exists() and time.time() - marker.stat().st_mtime < GRACE_SECONDS:
        since = round(time.time() - marker.stat().st_mtime)
        marker.unlink()
        log_event({"event": "override", "session_id": caller, "since_block_s": since})
        return None
    marker.write_text(str(time.time()))
    cost, baseline, cached, estimated = start_estimate(transcript)
    log_event({
        "event": "block", "session_id": caller, "tokens": tokens, "idle_s": round(idle),
        "start_cost": cost, "start_baseline": baseline, "start_cached": cached,
        "start_estimated": estimated,
    })

    reason = (
        f"Prompt cache expired {idle / 3600:.1f} h ago. This session holds "
        f"{tokens // 1000}k tokens: continuing writes them all to the cache again, "
        f"about {2 * tokens // 1000}k input-token equivalents, then "
        f"{tokens // 10_000}k for every later call. A new session in the right "
        f"preset costs {start_cost(transcript)}. {handoff_hint(transcript)}"
        f"Send any prompt within {GRACE_SECONDS // 60} minutes to continue here."
    )
    return {"decision": "block", "reason": reason}


def handoff_hint(transcript: Path) -> str:
    """Write the session's handoff note and say how to use it."""
    try:
        note = write_handoff(transcript)
    except (OSError, ValueError) as error:
        return f"(No handoff note: {error}.) "
    return f"To continue fresh, start the new session with: Read {note} and go on. "


def main() -> None:
    """Answer one hook event from stdin; stay silent on anything this guard does not expect."""
    try:
        output = decide(json.load(sys.stdin))
    except Exception as error:  # noqa: BLE001
        # Called by a harness that does not speak this protocol, or a broken guard: never
        # get in the way of the prompt. Say why only when asked to.
        if os.environ.get("REAR_GUARD_DEBUG"):
            sys.stderr.write(f"cache-expiry-guard: {error!r}\n")
        return
    if output:
        sys.stdout.write(json.dumps(output) + "\n")


if __name__ == "__main__":
    main()
