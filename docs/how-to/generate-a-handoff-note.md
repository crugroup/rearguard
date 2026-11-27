# How to generate a handoff note

Give `handoff.py` a transcript path or a session id; a prefix of the id is enough.

```bash
hooks/handoff.py ~/.claude/projects/<project>/<session-id>.jsonl
hooks/handoff.py 3f2a9c
```

It prints the path of the note, written to `~/.claude/handoffs/<date>-<id prefix>.md`. Start a
new session with `Read <that path> and go on.`

An id that matches several transcripts resolves to the first in sorted order; give more
characters to be precise. The note's contents are listed in the
[handoff note reference](../reference/handoff-note.md).
