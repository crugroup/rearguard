#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Behaviour of the Claude Code hooks, driven the way a harness drives them: one process per
event, the event as JSON on stdin, the decision as JSON on stdout.

Two promises are tested. When a guard has a reason to act, it says so in the form Claude Code
reads. When it is called by anything that does not speak its protocol, or cannot do its job,
it prints nothing, writes nothing to stderr and exits 0, so it never gets in the way.

Every run gets its own home directory (HOME, and USERPROFILE on Windows), so no test touches the real ~/.claude.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
CACHE_GUARD = "cache-expiry-guard.py"
ARCHIVE_GUARD = "archive-read-guard.py"
BOTH = (CACHE_GUARD, ARCHIVE_GUARD)


class HookCase(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        self.projects = self.home / ".claude" / "projects" / "-some-project"
        self.projects.mkdir(parents=True)

    def home_env(self):
        """Point the home directory at this test's, on POSIX and on Windows."""
        return {"HOME": str(self.home), "USERPROFILE": str(self.home)}

    def run_hook(self, hook, stdin, scripts=HOOKS, **env):
        """Run a hook as a harness would; return (exit code, stdout, stderr)."""
        if not isinstance(stdin, (str, bytes)):
            stdin = json.dumps(stdin)
        done = subprocess.run(
            [sys.executable, str(scripts / hook)],
            input=stdin if isinstance(stdin, bytes) else stdin.encode(),
            capture_output=True,
            env={**os.environ, **self.home_env(), **env},
            timeout=30,
        )
        return done.returncode, done.stdout.decode(), done.stderr.decode()

    def assert_silent(self, hook, stdin, **kwargs):
        code, out, err = self.run_hook(hook, stdin, **kwargs)
        self.assertEqual((code, out, err), (0, "", ""), f"{hook} on {stdin!r}")

    def transcript(self, session, tokens=200_000, idle=timedelta(hours=2), size=0,
                   prompt="Please fix the build"):
        """Write a session transcript whose last request used `tokens` and ended `idle` ago."""
        stamp = (datetime.now(timezone.utc) - idle).isoformat()
        usage = {"input_tokens": tokens, "cache_read_input_tokens": 0}
        lines = [
            {"type": "user", "timestamp": stamp, "cwd": "/work",
             "message": {"content": prompt}},
            {"type": "assistant", "timestamp": stamp,
             "message": {"content": [{"type": "text", "text": "Fixed."}], "usage": usage}},
        ]
        raw = "\n".join(json.dumps(line, separators=(",", ":")) for line in lines) + "\n"
        if size:
            filler = {"type": "attachment", "text": "x" * max(0, size - len(raw))}
            raw += json.dumps(filler) + "\n"
        path = self.projects / f"{session}.jsonl"
        path.write_bytes(raw.encode("utf-8"))  # same bytes on every platform
        return path


class ForeignCallerTest(HookCase):
    """A guard called by a harness it was not written for stays out of the way."""

    def test_empty_input_is_ignored(self):
        for hook in BOTH:
            self.assert_silent(hook, "")

    def test_input_that_is_not_json_is_ignored(self):
        for hook in BOTH:
            self.assert_silent(hook, "not json at all")
            self.assert_silent(hook, b"\xff\xfe\x00 binary")

    def test_json_that_is_not_an_event_is_ignored(self):
        for hook in BOTH:
            for text in ("null", "[]", '"text"', "42", "true"):
                self.assert_silent(hook, text)

    def test_event_in_another_harness_format_is_ignored(self):
        event = {"event": "before_tool", "tool": "bash", "args": ["ls"], "session": "abc"}
        for hook in BOTH:
            self.assert_silent(hook, event)

    def test_event_with_fields_of_the_wrong_type_is_ignored(self):
        events = [
            {"tool_name": "Read", "tool_input": "oops"},
            {"tool_name": ["Read"], "tool_input": None},
            {"tool_name": "Read", "tool_input": {"file_path": 7}},
            {"tool_name": "mcp__ccd_session_mgmt__list_events", "tool_input": {"session_id": 3}},
            {"transcript_path": 5, "session_id": ["x"]},
            {"transcript_path": None},
        ]
        for hook in BOTH:
            for event in events:
                self.assert_silent(hook, event)

    def test_transcript_that_does_not_exist_is_ignored(self):
        missing = str(self.projects / "gone.jsonl")
        self.assert_silent(CACHE_GUARD, {"transcript_path": missing, "session_id": "s"})
        self.assert_silent(
            ARCHIVE_GUARD,
            {"tool_name": "Read", "tool_input": {"file_path": missing}, "session_id": "s"},
        )

    def test_transcript_in_another_format_is_ignored(self):
        path = self.projects / "other.jsonl"
        path.write_bytes(b"\x00\xff garbage\n" * 30_000)
        self.assert_silent(CACHE_GUARD, {"transcript_path": str(path), "session_id": "s"})
        self.assert_silent(
            ARCHIVE_GUARD,
            {"tool_name": "Read", "tool_input": {"file_path": str(path)}, "session_id": "s"},
        )

    def test_guard_installed_without_handoff_is_ignored(self):
        lonely = self.home / "lonely"
        lonely.mkdir()
        for hook in BOTH:
            shutil.copy(HOOKS / hook, lonely / hook)
            self.assert_silent(hook, {"transcript_path": "/x", "session_id": "s"}, scripts=lonely)

    def test_closed_input_is_ignored(self):
        for hook in BOTH:
            done = subprocess.run(
                [sys.executable, str(HOOKS / hook)], stdin=subprocess.DEVNULL,
                capture_output=True, env={**os.environ, **self.home_env()}, timeout=30,
            )
            self.assertEqual((done.returncode, done.stdout, done.stderr), (0, b"", b""))

    def test_a_failure_is_explained_only_when_asked(self):
        code, out, err = self.run_hook(CACHE_GUARD, "not json", REAR_GUARD_DEBUG="1")
        self.assertEqual((code, out), (0, ""))
        self.assertIn("cache-expiry-guard", err)


class NonAsciiTest(HookCase):
    """Text outside ASCII works whatever the platform's default encoding is (cp1252 on Windows)."""

    ASCII_ONLY = {"PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0", "LC_ALL": "C"}
    PROMPT = "Rénover le café – « ok » 日本語 " + "x" * 2500  # long: the note clips it with "…"

    def test_the_cache_guard_writes_a_note_for_a_non_ascii_session(self):
        path = self.transcript("live", prompt=self.PROMPT)
        event = {"transcript_path": str(path), "session_id": "live", "prompt": "Continuons – très bien"}
        code, out, err = self.run_hook(CACHE_GUARD, event, **self.ASCII_ONLY)
        self.assertEqual((code, err, json.loads(out)["decision"]), (0, "", "block"))
        note = next((self.home / ".claude" / "handoffs").glob("*.md"))
        self.assertIn("Rénover le café", note.read_text(encoding="utf-8"))

    def test_the_archive_guard_writes_a_note_for_a_non_ascii_session(self):
        path = self.transcript("past-session", prompt=self.PROMPT, size=300_000)
        event = {"tool_name": "Read", "session_id": "caller", "tool_input": {"file_path": str(path)}}
        code, out, err = self.run_hook(ARCHIVE_GUARD, event, **self.ASCII_ONLY)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("deny", out)


class CacheExpiryGuardTest(HookCase):
    def prompt(self, path, session="live"):
        return self.run_hook(CACHE_GUARD, {"transcript_path": str(path), "session_id": session})

    def test_blocks_the_first_prompt_of_a_large_expired_session(self):
        path = self.transcript("live", tokens=200_000, idle=timedelta(hours=2))
        code, out, err = self.prompt(path)
        answer = json.loads(out)
        self.assertEqual((code, err, answer["decision"]), (0, "", "block"))
        self.assertIn("200k tokens", answer["reason"])

    def test_points_the_blocked_prompt_to_a_handoff_note(self):
        path = self.transcript("live-session", idle=timedelta(hours=2))
        reason = json.loads(self.prompt(path)[1])["reason"]
        note = next((self.home / ".claude" / "handoffs").glob("*.md"))
        self.assertIn(str(note), reason)
        self.assertIn("Please fix the build", note.read_text(encoding="utf-8"))

    def test_resending_after_the_block_continues_the_session(self):
        path = self.transcript("live", idle=timedelta(hours=2))
        self.assertIn("block", self.prompt(path)[1])
        self.assertEqual(self.prompt(path), (0, "", ""))

    def test_lets_a_session_with_a_warm_cache_through(self):
        path = self.transcript("live", idle=timedelta(minutes=5))
        self.assertEqual(self.prompt(path), (0, "", ""))

    def test_lets_a_small_session_through_even_when_expired(self):
        path = self.transcript("live", tokens=20_000, idle=timedelta(hours=5))
        self.assertEqual(self.prompt(path), (0, "", ""))


class CacheGuardLogTest(HookCase):
    """The cache guard records what it does, in a log that stays bounded."""

    def setUp(self):
        super().setUp()
        self.state = self.home / ".claude" / "cache-guard"
        self.log = self.state / "events.jsonl"

    def prompt(self, path, session="live"):
        return self.run_hook(CACHE_GUARD, {"transcript_path": str(path), "session_id": session})

    def events(self):
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def module(self):
        """Load the guard as a module, with its log pointed at this test's HOME."""
        spec = importlib.util.spec_from_file_location("cache_guard", HOOKS / CACHE_GUARD)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.STATE_DIR = self.state
        module.LOG_FILE = self.log
        module.LOG_README = self.state / "README.md"
        return module

    def test_a_block_is_logged_with_what_it_saves(self):
        path = self.transcript("live", tokens=200_000, idle=timedelta(hours=2))
        self.prompt(path)
        (block,) = self.events()
        self.assertEqual(
            (block["v"], block["event"], block["session_id"], block["tokens"]),
            (1, "block", "live", 200_000),
        )
        self.assertAlmostEqual(block["idle_s"], 7200, delta=60)
        self.assertEqual(block["start_baseline"], 200_000)  # the one request is also the first
        self.assertEqual(block["start_cost"], 400_000)
        self.assertFalse(block["start_estimated"])
        datetime.fromisoformat(block["ts"])

    def test_a_prompt_after_the_block_is_logged_as_an_override(self):
        path = self.transcript("live", idle=timedelta(hours=2))
        self.prompt(path)
        self.prompt(path)
        block, override = self.events()
        self.assertEqual((block["event"], override["event"]), ("block", "override"))
        self.assertEqual(override["session_id"], "live")
        self.assertLess(override["since_block_s"], 60)

    def test_prompts_that_are_not_held_are_not_logged(self):
        self.prompt(self.transcript("warm", idle=timedelta(minutes=5)), "warm")
        self.prompt(self.transcript("small", tokens=20_000, idle=timedelta(hours=5)), "small")
        self.assertFalse(self.log.exists())

    def test_a_readme_explains_the_log(self):
        self.prompt(self.transcript("live", idle=timedelta(hours=2)))
        readme = (self.state / "README.md").read_text(encoding="utf-8")
        for word in ("`block`", "`override`", "start_cost", "2 * tokens", "25 MiB"):
            self.assertIn(word, readme)

    def test_a_log_that_cannot_be_written_does_not_stop_the_block(self):
        self.log.mkdir(parents=True)  # appending to a directory fails
        path = self.transcript("live", idle=timedelta(hours=2))
        code, out, err = self.prompt(path)
        self.assertEqual((code, err, json.loads(out)["decision"]), (0, "", "block"))

    def test_the_log_never_passes_its_limit(self):
        guard = self.module()
        guard.MAX_LOG_BYTES = 4_000
        for n in range(300):
            guard.log_event({"event": "block", "session_id": f"s{n}", "tokens": n})
            self.assertLessEqual(self.log.stat().st_size, guard.MAX_LOG_BYTES)
        self.assertEqual(self.events()[-1]["session_id"], "s299")  # the newest event is kept
        self.assertEqual(sorted(p.name for p in self.state.iterdir()), ["README.md", "events.jsonl"])

    def test_trimming_keeps_whole_lines_and_the_newest_ones(self):
        guard = self.module()
        guard.MAX_LOG_BYTES = 4_000
        for n in range(300):
            guard.log_event({"event": "block", "session_id": f"s{n}", "tokens": n})
        events = self.events()  # every line still parses
        numbers = [int(e["session_id"][1:]) for e in events]
        self.assertEqual(numbers, list(range(numbers[0], 300)))  # no gap: only the oldest went
        self.assertGreater(len(events), 5)

    def test_an_oversized_event_is_dropped_not_logged(self):
        guard = self.module()
        guard.MAX_LOG_BYTES = 1_000
        guard.log_event({"event": "block", "session_id": "x" * 5_000})
        self.assertFalse(self.log.exists())


class ArchiveReadGuardTest(HookCase):
    def read(self, path, caller="caller", **tool_input):
        event = {"tool_name": "Read", "session_id": caller,
                 "tool_input": {"file_path": str(path), **tool_input}}
        return self.run_hook(ARCHIVE_GUARD, event)

    def past_session(self, size=300_000):
        return self.transcript("past-session", idle=timedelta(days=3), size=size)

    def test_denies_the_first_whole_read_of_another_session(self):
        code, out, err = self.read(self.past_session())
        answer = json.loads(out)["hookSpecificOutput"]
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(answer["hookEventName"], "PreToolUse")
        self.assertEqual(answer["permissionDecision"], "deny")

    def test_names_the_handoff_note_that_replaces_the_read(self):
        out = self.read(self.past_session())[1]
        reason = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
        note = next((self.home / ".claude" / "handoffs").glob("*.md"))
        self.assertIn(str(note), reason)
        self.assertIn("Please fix the build", note.read_text(encoding="utf-8"))

    def test_repeating_the_read_goes_through(self):
        path = self.past_session()
        self.assertIn("deny", self.read(path)[1])
        self.assertEqual(self.read(path), (0, "", ""))

    def test_a_partial_read_goes_through(self):
        path = self.past_session()
        self.assertEqual(self.read(path, limit=50), (0, "", ""))
        self.assertEqual(self.read(path, offset=10), (0, "", ""))

    def test_a_session_may_read_its_own_transcript(self):
        path = self.past_session()
        self.assertEqual(self.read(path, caller="past-session"), (0, "", ""))

    def test_a_small_transcript_goes_through(self):
        self.assertEqual(self.read(self.past_session(size=5_000)), (0, "", ""))

    def test_reading_anything_else_goes_through(self):
        notes = self.home / "notes.md"
        notes.write_bytes(b"hello\n" * 100_000)
        self.assertEqual(self.read(notes), (0, "", ""))


if __name__ == "__main__":
    unittest.main(verbosity=1)
