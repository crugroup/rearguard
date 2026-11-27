# rearguard

[![CI](https://github.com/crugroup/rearguard/actions/workflows/ci.yml/badge.svg)](https://github.com/crugroup/rearguard/actions/workflows/ci.yml)
[![Python: default and latest](https://img.shields.io/badge/python-runner%20default%20%2B%20latest-blue)](.github/workflows/ci.yml)
[![Tested on Linux, macOS and Windows](https://img.shields.io/badge/tested%20on-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)](.github/workflows/ci.yml)
[![dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen)](hooks)
[![model calls: zero](https://img.shields.io/badge/model%20calls-zero-brightgreen)](docs/explanation/why-the-guards-exist.md)
[![License: GPL v3 or later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)
[![Claude Code hooks](https://img.shields.io/badge/Claude%20Code-hooks-d97757)](https://docs.claude.com/en/docs/claude-code/hooks)
[![docs: Diátaxis](https://img.shields.io/badge/docs-Di%C3%A1taxis-informational)](https://diataxis.fr/)

**Two Claude Code hooks that stop long sessions from silently re-buying their whole context.**
They block one expensive prompt, once, and hand you a short note to start a fresh session from.
Standard library only, no model call, and they never get in your way when they cannot help.

```bash
git clone https://github.com/crugroup/rearguard
cd rearguard
./install    # then register the two guards, see below
```

## What they guard against

- **[`cache-expiry-guard.py`](hooks/cache-expiry-guard.py)** (`UserPromptSubmit`) holds the first
  prompt sent to a session of 150k tokens or more that has been idle for over an hour. The prompt
  cache has expired, so the whole context would be written again at twice the input price. It
  shows the cost against a new session and a handoff note to start that session from; any
  prompt sent within 10 minutes goes through.
- **[`archive-read-guard.py`](hooks/archive-read-guard.py)** (`PreToolUse`) denies the first whole
  read of another session's transcript (200 kB or more) and names that session's handoff note
  instead. Repeat the call and it goes through for 30 minutes.

Both build the note with [`handoff.py`](hooks/handoff.py), which is not a hook itself: it reads
a transcript, with no model call, into a few thousand tokens instead of the whole session.

## Register the guards

Add to `~/.claude/settings.json`, merged with the hooks you already have, then restart Claude Code:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read|mcp__ccd_session_mgmt__list_events|mcp__ccd_session_mgmt__export_transcript",
        "hooks": [{ "type": "command", "command": "~/.claude/hooks/archive-read-guard.py", "timeout": 10 }]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [{ "type": "command", "command": "~/.claude/hooks/cache-expiry-guard.py", "timeout": 10 }]
      }
    ]
  }
}
```

Requires Python 3 on `PATH` as `python3`. CI runs the tests on Linux, macOS and Windows, each with
the runner's default Python and the latest release. `./install` is for macOS and Linux; see
[install and register](docs/how-to/install-and-register.md#on-windows) for Windows. Claude Code only.

## Documentation

Organised by what you need, following [Diátaxis](https://diataxis.fr/).

| | Learning | Working |
|---|---|---|
| **Practical** | [Tutorial: watch the cache guard block a prompt](docs/tutorials/watch-a-guard-fire.md) | How-to: [install and register](docs/how-to/install-and-register.md), [generate a handoff note](docs/how-to/generate-a-handoff-note.md), [tune the thresholds](docs/how-to/tune-the-thresholds.md), [measure what the guard saved](docs/how-to/measure-the-savings.md), [find out why a guard stayed silent](docs/how-to/debug-a-silent-guard.md), [cut a release](docs/how-to/cut-a-release.md) |
| **Theoretical** | [Explanation: why the guards exist](docs/explanation/why-the-guards-exist.md) | Reference: [hooks](docs/reference/hooks.md), [event log](docs/reference/event-log.md), [handoff note](docs/reference/handoff-note.md) |

## Development

```bash
python3 -m unittest discover -s tests -v
```

Each test runs the hook as Claude Code does, one process per event with the event as JSON on
stdin, in a throwaway home directory. Nothing touches your real `~/.claude`.

## Licence

GNU General Public Licence, version 3 or (at your option) any later version. See
[LICENSE](LICENSE); each source file carries `SPDX-License-Identifier: GPL-3.0-or-later`.
