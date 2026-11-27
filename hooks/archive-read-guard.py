#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""PreToolUse hook: hand an agent the handoff note before it reads a past session.

A past session's transcript is large; its handoff note (see handoff.py) says what
the session did in a few thousand tokens and names the transcript to search. The
first whole read of another session's transcript, or of its events through the
app's session tools, is denied once with the note's path. Reads of the same
session go through for GRACE_SECONDS afterwards. Searching (Grep,
search_session_transcripts) and partial reads (Read with offset or limit) are left
alone, since that is what the note recommends.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # handoff.py sits next to this
try:
    from handoff import PROJECTS, write_handoff
except Exception:  # installed without handoff.py: nothing to offer, stay out of the way
    sys.exit(0)

APP_SESSIONS = Path("~/Library/Application Support/Claude/claude-code-sessions")
STATE_DIR = Path("~/.claude/archive-guard").expanduser()
GRACE_SECONDS = 30 * 60
MIN_BYTES = 200_000  # below this, the transcript costs little more than its note
SESSION_TOOLS = (
    "mcp__ccd_session_mgmt__list_events",
    "mcp__ccd_session_mgmt__export_transcript",
)


def transcript_for_app_session(session_id: str) -> Path | None:
    """Map the app's local_<id> session to its Claude Code transcript."""
    for meta in APP_SESSIONS.expanduser().glob(f"*/*/{session_id}.json"):
        data = json.loads(meta.read_text())
        cli = data.get("lastAssistantCliSessionId") or data.get("cliSessionId")
        if cli:
            return next(PROJECTS.glob(f"*/{cli}.jsonl"), None)
    return None


def target(event: dict) -> Path | None:
    """Return the past session's transcript the tool call would read whole."""
    name = event.get("tool_name") or ""
    data = event.get("tool_input") or {}
    if name == "Read":
        if data.get("offset") or data.get("limit"):
            return None
        path = Path(data.get("file_path") or "").expanduser()
        is_transcript = path.suffix == ".jsonl" and path.parent.parent == PROJECTS
        return path if is_transcript else None
    if name in SESSION_TOOLS:
        session = data.get("session_id") or ""
        return transcript_for_app_session(session) if session != "self" else None
    return None


def decide(event: dict) -> dict | None:
    """Return the hook output that denies the call, or None to let it through."""
    transcript = target(event)
    if transcript is None or not transcript.is_file():
        return None
    size = transcript.stat().st_size
    if transcript.stem == event.get("session_id") or size < MIN_BYTES:
        return None  # the caller's own session, or one cheaper to read than its note

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    caller = event.get("session_id") or "unknown"
    marker = STATE_DIR / f"{caller}-{transcript.stem}.allowed"
    if marker.exists() and time.time() - marker.stat().st_mtime < GRACE_SECONDS:
        return None
    note = write_handoff(transcript)
    marker.write_text(str(time.time()))

    reason = (
        f"This reads a past session ({size // 1000} kB transcript). "
        f"Read its handoff note first: {note}. It summarises the session and names "
        f"the transcript to search with Grep. If you still need the whole session, "
        f"repeat this call: it goes through for {GRACE_SECONDS // 60} minutes."
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
    }


def main() -> None:
    """Answer one hook event from stdin; stay silent on anything this guard does not expect."""
    try:
        output = decide(json.load(sys.stdin))
    except Exception as error:  # noqa: BLE001
        # Called by a harness that does not speak this protocol, or a broken guard: never
        # get in the way of the call. Say why only when asked to.
        if os.environ.get("REAR_GUARD_DEBUG"):
            sys.stderr.write(f"archive-read-guard: {error!r}\n")
        return
    if output:
        sys.stdout.write(json.dumps(output) + "\n")


if __name__ == "__main__":
    main()
