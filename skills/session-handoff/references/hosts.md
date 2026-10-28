# Installing and running in different agents

Copy the skill directory (`session-handoff/`, the one containing `SKILL.md`) into the agent's skills folder. The repository's `install.py` does this for the agents it finds.

| Agent | Skills folder | Status |
|---|---|---|
| Claude Code (CLI, desktop Code tab) | `~/.claude/skills/session-handoff` (or `$CLAUDE_CONFIG_DIR/skills/...`) | Standard personal skills folder |
| Codex | `~/.agents/skills/session-handoff` | Codex loads skills from `~/.agents/skills` |
| Gemini CLI | `~/.gemini/skills/session-handoff` | Not verified by the author; `install.py` writes it only if `~/.gemini` exists |
| Any other agent with SKILL.md-style skills | its skills folder | `install.py --target <folder>` |

If your agent keeps skills elsewhere, check its documentation and use `--target`.

## Read access

The script reads `~/.codex`, `~/.claude` and Claude Desktop's app-data folder.

- Codex: the default sandbox allowed read-only access to `~/.claude` when tested.
- Claude Code: reading outside the project directory may ask for confirmation — allow it — or start with `claude --add-dir ~/.codex`.
- Other agents: if a sandbox or workspace limit blocks the read, add those directories to the readable set or have the user approve the command.

## Runtime

- Python 3.9 or newer, standard library only. macOS's `/usr/bin/python3` is enough; on Windows use `python` or `py -3`.
- Call the script by absolute path, e.g. `python3 ~/.agents/skills/session-handoff/scripts/handoff.py show "name"`.
- Test hooks: `SESSION_HANDOFF_HOME=<dir>` makes the script look for `.codex` / `.claude` under another root; `SESSION_HANDOFF_NO_CACHE=1` disables the title cache.

## Not applicable

Sessions that run in the cloud (claude.ai web, Claude cloud sessions, ChatGPT web) cannot read this computer's files, so the skill does nothing there.
