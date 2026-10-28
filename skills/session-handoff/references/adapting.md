# Adapting the skill to a machine

Defaults assume a standard install. Everything below is for when the defaults don't fit. Check with `handoff.py doctor` after each change.

## 1. Non-standard locations

Each setting is resolved as: environment variable → config file → default.

| Environment variable | Config key | Default | Meaning |
|---|---|---|---|
| `CODEX_HOME` | `codex_home` | `~/.codex` | Codex data directory (contains `sessions/`, `session_index.jsonl`) |
| `CLAUDE_CONFIG_DIR` | `claude_home` | `~/.claude` | Claude Code config directory (contains `projects/`) |
| `CLAUDE_DESKTOP_DIR` | `claude_desktop_dir` | auto (see below) | Claude Desktop app-data directory |
| `SESSION_HANDOFF_LANG` | `lang` | locale | `en` or `zh`; `--lang` overrides it |

Claude Desktop's folder is auto-detected by trying the per-OS locations and reading those that exist:

- macOS: `~/Library/Application Support/Claude`
- Windows: `%APPDATA%\Claude`
- Linux: `$XDG_CONFIG_HOME/Claude` or `~/.config/Claude`

The macOS layout was verified; the Windows and Linux ones are best-effort. If `doctor` shows the folder is elsewhere, set `claude_desktop_dir`.

To persist a setting, write `~/.config/session-handoff/config.json` (`$XDG_CONFIG_HOME/session-handoff/config.json` if that variable is set):

```json
{"codex_home": "/data/codex", "claude_home": "~/claude-alt", "lang": "zh"}
```

Only Claude's title cache is ever written (`~/.cache/session-handoff/`); `SESSION_HANDOFF_NO_CACHE=1` turns it off.

## 2. Format drift

The agents' record formats are internal and unversioned, so they can change with any release. Symptoms: `doctor` says "sessions exist but none could be parsed", or `show` says no conversation text was extracted, or the material contains junk (injected prompts, tool output, duplicated messages).

1. Take the newest record file `doctor`/`list` reports. Read a few lines — never load a large file whole (Codex files can reach 100 MB; use `head`, `tail`, `grep`, or a small Python loop).
2. Compare with the field description in `references/source-codex.md` or `references/source-claude.md`: where the message text lives, which record types are noise.
3. Edit `messages()` (and, if the title/ID/cwd lookup broke, `sessions()`) in `scripts/sources/<source>.py`. Keep the contract: `messages(path)` yields `(role, text, timestamp)` with role in `user` / `assistant` / `summary`.
4. Run `doctor`, then `show` on a real session and read the output for leftover noise.
5. Update the matching reference file with what changed and the date, so the next person starts from the new facts.

Edits live in the installed copy. If the fix is general, send it upstream.

## 3. Adding a source

Any agent that stores sessions as local files can be added without touching existing code. Drop `scripts/sources/<name>.py` next to `claude.py` and `codex.py`; it is discovered automatically and appears in `--source`, `list`, `show` and `doctor`.

Required module attributes:

```python
NAME = "myagent"          # CLI value for --source, and the references/source-<NAME>.md to read on errors
LABEL = "MyAgent"         # shown to the user

def roots() -> list[Path]: ...                       # where it looks (doctor prints these)
def owns(path: Path) -> bool: ...                    # is this record file one of ours?
def sessions(include_all: bool = False) -> list[dict]: ...   # make_session(...) dicts
def session_for_path(path: Path) -> dict: ...        # one make_session(...) for a given file
def messages(path: Path): ...                        # yield (role, text, timestamp)
```

Use `common.make_session(source=LABEL, id=..., title=..., aliases=[...], cwd=..., path=..., updated=<epoch>)`; helpers `iter_jsonl`, `strip_tags`, `last_timestamp`, `stamp` are in `common.py`, and `config.setting(ENV, key)` gives the env/config override pattern. Use `claude.py` (JSONL, many files) or `codex.py` (JSONL plus a name index) as the template. Write the format notes to `references/source-<NAME>.md`, and add a test beside the existing ones in `tests/` if the repository copy is available.

Don't guess a format: inspect real records first. If the agent stores sessions in SQLite or an encrypted/opaque store, say so to the user rather than fabricating a parser.

## 4. Other notes

- Python 3.9+ standard library only. `python3 -m unittest discover -s tests` runs the tests when working in the repository.
- Windows: the scripts reconfigure stdout to UTF-8, and paths are handled with `pathlib`, but this has not been exercised on a real Windows machine — treat the first run as a test.
