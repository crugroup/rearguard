# Handoff note reference

Markdown written by [`handoff.py`](../../hooks/handoff.py) to
`~/.claude/handoffs/<date>-<id prefix>.md`, where the date is that of the session's last record.
Built from the transcript alone. Rebuilding overwrites the file.

| Section | Content | Limit |
|---|---|---|
| Heading | Session title, or the transcript's file name | |
| Header list | Folder, first and last timestamps, transcript path | |
| Task as first asked | The first prompt | 2000 characters |
| Latest prompts | The prompts after the first, with timestamps | last 5, 600 characters each |
| Turn recaps, oldest first | Recaps passed to a `wrap_up` tool | last 8, 400 characters each |
| Task list | The task list rebuilt from `update_plan` calls, as `[x]`, `[~]`, `[ ]` | |
| Files written or edited | Paths from `Write`, `Edit` and `NotebookEdit`, most recent last | last 30 |
| Last reply | The last text the assistant wrote on the main chain | 2500 characters |

Prompts injected by the system (text starting with `<`) and tool results are not counted as
prompts. Sidechain (subagent) messages are ignored.

Turn recaps and the task list come from the `wrap_up` and `update_plan` tools of the Claude
desktop app. In other sessions both sections read `(none)` or are empty.
