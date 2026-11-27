# How to install and register the hooks

1. Link the hooks into `~/.claude/hooks/`:

   ```bash
   ./install
   ```

   A real file of the same name already there is left alone and reported as skipped; remove it
   and run `./install` again. Links point into the clone, so `git pull` updates the hooks. The
   three files must stay together in `hooks/`: the guards import `handoff.py` through the link.

2. Merge this into `~/.claude/settings.json`, next to the hooks you already have:

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

3. Restart Claude Code.

Leave out the `mcp__ccd_session_mgmt__*` names from the matcher if you do not use the Claude
desktop app; `Read` alone still covers transcripts read from disk.

## Uninstall

Remove the two entries from `settings.json`, then:

```bash
./install --uninstall
```

This removes only links that point into this clone. Logs and notes in `~/.claude/cache-guard/`,
`~/.claude/archive-guard/` and `~/.claude/handoffs/` stay; delete them if you want.

## On Windows

CI runs the tests on Windows, but `./install` is a bash script and Windows ignores the
`#!/usr/bin/env python3` line, so link and register by hand:

1. Copy the three files of `hooks/` together into `%USERPROFILE%\.claude\hooks\`.
2. Register each guard as in step 2, with the interpreter in the command, for example
   `"command": "python %USERPROFILE%\\.claude\\hooks\\cache-expiry-guard.py"`.

The archive guard's session-tool lookup reads the Claude desktop app's session folder at its
macOS location only; on Windows the guard still covers `Read` of transcripts. The hooks
have not been installed on Windows by the maintainers; only the tests run there, so adapt the
paths to your shell if needed.
