# session-handoff

[中文说明](README.zh-CN.md)

An agent skill that lets one coding agent **continue a conversation that happened in another one** — for example when your Claude quota runs out mid-task and you want to pick the same thread up in Codex, or the other way round.

You say *"continue my Codex session called `migration plan`"*; the skill finds the conversation in the local records on your machine, builds a compact handoff (goal, recent turns in full, earlier turns as excerpts, compaction summaries kept), and the agent carries on from the last open question.

- **Read-only.** It never modifies another agent's files and never converts a session into another agent's format. The one thing it writes is a small title cache in `~/.cache/session-handoff/`.
- **Local only.** Nothing is uploaded by the skill. (The handoff text does go to whichever model provider the *current* agent uses — that's the point.)
- **No dependencies.** Python 3.9+ standard library.

## Supported sources

| Source | What is read |
|---|---|
| Claude Code, Claude Desktop (Code tab and local agent sessions) | `~/.claude/projects/**.jsonl` and the desktop app's session metadata |
| Codex (CLI and desktop) | `~/.codex/sessions/**/rollout-*.jsonl` and `session_index.jsonl` |

It runs *from* any agent that loads `SKILL.md` skills and can run Python: Claude Code, Codex, Gemini CLI and others. Not covered: claude.ai / ChatGPT web chats and cloud sessions (not stored on your computer). Other agents can be added as source modules — see below.

Tested on macOS. Linux and Windows locations are handled on a best-effort basis (see [adapting.md](skills/session-handoff/references/adapting.md)); please run `doctor` on first use and report what you find.

## Install

```sh
git clone https://github.com/GenLI3202/session-handoff.git
cd session-handoff
python3 install.py
```

`install.py` copies the skill into the skill folder of every agent it finds (`~/.claude/skills`, `~/.agents/skills` for Codex, `~/.gemini/skills`) and then runs the self-check. Options: `--dry-run`, and `--target <skills folder>` for any other agent. Or copy `skills/session-handoff/` into your agent's skills folder by hand.

## Use

Just ask, in whichever agent you are in now:

> Continue my Claude conversation "budget review" here.
> 接着聊 Codex 里叫「迁移方案」的那个会话。
> Pick up the session `3f9a1c2e` from Codex.

If several conversations match, the agent lists them and you choose. You can also run the script yourself:

```sh
python3 skills/session-handoff/scripts/handoff.py list --query budget
python3 skills/session-handoff/scripts/handoff.py show "budget review" --source claude -n 6
```

## Adapting it to your machine

The skill is designed so that the agent can tune it to the computer it is installed on:

1. `handoff.py doctor` reports which agents' records exist, where it looked, and whether the newest sessions still parse.
2. Non-standard locations are fixed with `CODEX_HOME`, `CLAUDE_CONFIG_DIR`, `CLAUDE_DESKTOP_DIR` or `~/.config/session-handoff/config.json`.
3. If an agent updates and changes its record format, `doctor` flags it, and the agent follows the "format drift" procedure to patch the adapter.
4. A new agent is one new file in `scripts/sources/` (auto-discovered).

Details: [skills/session-handoff/references/adapting.md](skills/session-handoff/references/adapting.md).

## Develop

```sh
python3 -m unittest discover -s tests -v
```

The tests build synthetic session files in a temp directory; they never read your real conversations.

## License

MIT
