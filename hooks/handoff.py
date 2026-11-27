#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a handoff note from a Claude Code transcript, without any model call.

The note holds what a new session needs to pick up the task: the title, the first
and the latest prompts, the turn recaps, the task list, the files written and the
last reply, plus the transcript path to search for detail. It costs no tokens to
build and a few thousand to read.

Usage: handoff.py <transcript.jsonl | session id or prefix>
Prints the path of the note written under ~/.claude/handoffs/.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECTS = Path("~/.claude/projects").expanduser()
HANDOFFS = Path("~/.claude/handoffs").expanduser()
LATEST_PROMPTS = 5
LATEST_RECAPS = 8
LATEST_FILES = 30


def clip(text: str, limit: int) -> str:
    """Shorten text to limit characters, marking the cut."""
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " […]"


def prompt_text(record: dict) -> str | None:
    """Return the text the user typed in a user record, or None for anything else."""
    if record.get("isMeta"):
        return None
    content = (record.get("message") or {}).get("content")
    if isinstance(content, list):
        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
        if len(texts) != len(content):  # tool results, not a prompt
            return None
        content = "\n".join(texts)
    if not isinstance(content, str) or content.lstrip().startswith("<"):
        return None  # system-injected text: notifications, commands, reminders
    return content


def apply_plan(plan: list[dict], change: dict) -> list[dict]:
    """Replay one update_plan call on the task list."""
    if change.get("items"):
        return [dict(item) for item in change["items"]]
    if change.get("advance"):
        for i, item in enumerate(plan):
            if item.get("status") == "in_progress":
                item["status"] = "completed"
                if i + 1 < len(plan) and plan[i + 1].get("status") == "pending":
                    plan[i + 1]["status"] = "in_progress"
                break
    for number in change.get("done") or []:
        if 0 < number <= len(plan):
            plan[number - 1]["status"] = "completed"
    start = change.get("start")
    if isinstance(start, int) and 0 < start <= len(plan):
        plan[start - 1]["status"] = "in_progress"
    return plan


def read(transcript: Path) -> dict:
    """Collect the parts of the transcript a handoff note needs."""
    found = {"title": None, "cwd": None, "prompts": [], "recaps": [], "plan": [],
             "files": [], "reply": "", "first": None, "last": None}
    with transcript.open(encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            kind = record.get("type")
            stamp = record.get("timestamp")
            if stamp:
                found["first"] = found["first"] or stamp
                found["last"] = stamp
            if kind == "custom-title":
                found["title"] = record.get("customTitle")
            elif kind == "user":
                found["cwd"] = record.get("cwd") or found["cwd"]
                text = prompt_text(record)
                if text:
                    found["prompts"].append((stamp, text))
            elif kind == "assistant" and not record.get("isSidechain"):
                collect_assistant(found, record)
    return found


def collect_assistant(found: dict, record: dict) -> None:
    """Take the recap, task list, written files and reply text from one record."""
    for block in (record.get("message") or {}).get("content") or []:
        if block.get("type") == "text" and block.get("text", "").strip():
            found["reply"] = block["text"]
        if block.get("type") != "tool_use":
            continue
        name, data = block.get("name", ""), block.get("input") or {}
        if name.endswith("__wrap_up") and data.get("recap"):
            found["recaps"].append(data["recap"])
        elif name.endswith("__update_plan"):
            found["plan"] = apply_plan(found["plan"], data)
        elif name in ("Write", "Edit", "NotebookEdit") and data.get("file_path"):
            path = data["file_path"]
            if path in found["files"]:
                found["files"].remove(path)
            found["files"].append(path)


def section(title: str, body: list[str]) -> list[str]:
    """One Markdown section: a blank line, the heading, a blank line, the body."""
    return ["", f"## {title}", "", *body]


def render(transcript: Path, found: dict) -> str:
    """Write the note as Markdown."""
    marks = {"completed": "x", "in_progress": "~", "pending": " "}
    prompts = found["prompts"]
    lines = [
        f"# Handoff: {found['title'] or transcript.stem}",
        "",
        f"- Folder: `{found['cwd']}`",
        f"- Session: {found['first']} to {found['last']}",
        f"- Transcript (search it, do not read it whole): `{transcript}`",
    ]
    lines += section("Task as first asked",
                     [clip(prompts[0][1], 2000) if prompts else "(no prompt found)"])
    lines += section("Latest prompts",
                     [f"- {stamp}: {clip(text, 600)}" for stamp, text in prompts[1:][-LATEST_PROMPTS:]])
    lines += section("Turn recaps, oldest first",
                     [f"- {clip(r, 400)}" for r in found["recaps"][-LATEST_RECAPS:]])
    lines += section("Task list",
                     [f"- [{marks.get(i.get('status'), ' ')}] {i.get('content')}"
                      for i in found["plan"]] or ["(none)"])
    lines += section("Files written or edited, most recent last",
                     [f"- `{p}`" for p in found["files"][-LATEST_FILES:]] or ["(none)"])
    lines += section("Last reply", [clip(found["reply"], 2500)])
    return "\n".join(lines) + "\n"


def resolve(argument: str) -> Path:
    """Accept a transcript path or a session id (prefix)."""
    path = Path(argument).expanduser()
    if path.is_file():
        return path
    matches = sorted(PROJECTS.glob(f"*/{argument}*.jsonl"))
    if not matches:
        raise FileNotFoundError(argument)
    return matches[0]


def write_handoff(transcript: Path) -> Path:
    """Build the note for a transcript and return where it was written."""
    found = read(transcript)
    HANDOFFS.mkdir(parents=True, exist_ok=True)
    day = (found["last"] or datetime.now(timezone.utc).isoformat())[:10]
    target = HANDOFFS / f"{day}-{transcript.stem[:8]}.md"
    target.write_text(render(transcript, found), encoding="utf-8")
    return target


if __name__ == "__main__":
    arguments = sys.argv[1:]
    if len(arguments) != 1:
        sys.exit(__doc__)
    sys.stdout.write(f"{write_handoff(resolve(arguments[0]))}\n")
