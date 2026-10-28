# Claude local records

Observed 2026-09 on macOS (Claude Code CLI and Claude Desktop). The format is internal and unversioned and may change; `handoff.py doctor` detects when it stops parsing. Adapter: `scripts/sources/claude.py`.

## Locations

- Claude Code CLI and the Code tab of Claude Desktop: `<config dir>/projects/<encoded directory>/<session ID>.jsonl`, where `<config dir>` is `$CLAUDE_CONFIG_DIR` or `~/.claude`.
- Claude Desktop local agent sessions: `<desktop app dir>/local-agent-mode-sessions/<account>/<org>/local_<id>/.claude/projects/<directory>/<session ID>.jsonl`. App dir on macOS: `~/Library/Application Support/Claude` (Windows/Linux: see `adapting.md`).
- Sub-agent transcripts sit deeper in the session folder; reading only the `projects/*/*.jsonl` level avoids them.
- Directory encoding: ASCII letters and digits are kept, every other character (`/`, `_`, spaces, non-ASCII…) becomes `-`. It is not reversible, so the original directory comes from the `cwd` field in the records. `cwd` can change within a session; use the last one.

## Names

In priority order:

1. `type = "custom-title"` record, `customTitle` (a rename by the user)
2. Claude Desktop metadata `<desktop app dir>/claude-code-sessions/**/local_*.json`, `title`, matched by `cliSessionId` to the transcript file name
3. `type = "ai-title"` record, `aiTitle` (automatic title)
4. `type = "agent-name"` record, `agentName`
5. None of the above: the first 60 characters of the first real user message

- No `type = "summary"` records were seen in the sampled transcripts, so don't rely on them for titles.
- `~/.claude/history.jsonl` lines carry `sessionId`, `project`, `display` and a timestamp; `display` is the input history, not a title. Use it only as a hint when no name is found.
- Different sessions can share a name; let the user choose.

## Record structure

One JSON object per line; `type` says what it is:

- `user` / `assistant`: the conversation. Text is in `message.content`, either a string or an array of blocks (`text`, `tool_use`, `tool_result`, `thinking`, `image`). One assistant reply is often split over several lines, one block each.
- Other types: `ai-title`, `custom-title`, `agent-name`, `system` (e.g. hook status), `file-history-snapshot`, `file-history-delta`, `attachment`, `queue-operation`, `last-prompt`, `mode`, `cost-state`. Not needed for a handoff.
- Other fields: `uuid` / `parentUuid` chain the messages; `cwd`, `sessionId`, `timestamp`.

## Filters

- `type = "user"` holding only `tool_result` blocks: tool output, not user input.
- `isMeta = true`: injected message, skip.
- `isSidechain = true`: sub-agent message, skip.
- `isCompactSummary = true`: summary written after a context compaction; keep it as a summary.
- Take only `text` blocks; skip `thinking`, `image`, `tool_use`.
- Remove `<command-name>`, `<command-message>`, `<command-args>`, `<local-command-stdout>`, `<local-command-stderr>`, `<local-command-caveat>` and `<system-reminder>` blocks. A message left empty by this is skipped.

## Codex copies of Claude sessions

Codex Desktop can import a Claude session as a Codex thread (`~/.codex/external_agent_session_imports.json`). The import is a one-time snapshot and does not follow later changes — read the Claude original instead.

## Not on this machine

claude.ai web chats and Claude cloud sessions live on the server. Claude Desktop's folder holds an IndexedDB cache for claude.ai, but it has no complete record that can be resolved by name. Share links (`claude.ai/share/...`) can be opened in a signed-in browser; they are snapshots from the time of sharing.
