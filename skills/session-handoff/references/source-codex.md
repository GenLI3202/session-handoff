# Codex local records

Observed 2026-09 with Codex Desktop (`cli_version` 0.155.0-alpha). The format is internal and unversioned and may change; `handoff.py doctor` detects when it stops parsing. Adapter: `scripts/sources/codex.py`.

## Locations

- Sessions: `<codex home>/sessions/YYYY/MM/DD/rollout-<time>-<session ID>.jsonl`, where `<codex home>` is `$CODEX_HOME` or `~/.codex`.
- Archived sessions: `<codex home>/archived_sessions/rollout-<time>-<session ID>.jsonl`.
- The last 36 characters of the file name (without `.jsonl`) are the session ID.

## Names

- `<codex home>/session_index.jsonl`: one `{"id", "thread_name", "updated_at"}` per line.
- A rename appends a new line, so one ID can have several lines. The newest `updated_at` is the current name; older names are aliases.
- Different IDs can share a name.
- `updated_at` is about when the name was set, not the last activity. Last activity is the `timestamp` of the last record in the file.
- Only user-started sessions are indexed. Background sessions with `session_meta.payload.thread_source` of `subagent` or `guardian_review` have no name and are hidden by default.
- Sessions Codex imported from Claude are mostly not in the index; their names are in `<codex home>/external_agent_session_imports.json` under `records[].title`, keyed by `imported_thread_id`, with `source_path` pointing at the Claude original.

## Record structure

One JSON object per line: `{"timestamp", "type", "payload"}`.

- First line, `type = "session_meta"`: `payload.cwd` is the working directory; `payload.thread_source` and `payload.source` say where it came from.
- Conversation text: `type = "response_item"` with `payload.type = "message"`. `payload.role` is `user`, `assistant` or `developer`; the text is in `payload.content[]` items of type `input_text` or `output_text`.
- The same messages are logged again as `event_msg / item_completed`. Use only `response_item` to avoid duplicates.
- Tool calls: `function_call` / `function_call_output` (older) or `custom_tool_call` / `custom_tool_call_output` (current). Not needed.
- `reasoning` is reasoning content; skip it.
- `type = "compacted"`: context compaction. In the sampled files `payload.message` was empty and the summary items in `replacement_history` were encrypted. The original pre-compaction messages stay in the file, so reading the whole file is enough.

## What to strip from user messages

- Injected blocks: `<recommended_plugins>`, `<INSTRUCTIONS>`, `<environment_context>`, `<user_instructions>`, `<skill>`, `<turn_aborted>`, `<subagent_notification>`, and headings starting with `# AGENTS.md instructions`. A user message left empty by this is not user input.
- Threads imported from Claude also contain `<command-name>`, `<local-command-stdout>`, `<system-reminder>`, `<task-notification>` and similar.
- Images: `<image name=... path=...>` and `</image>` come as separate content items; `input_image` is a base64 image and is most of a large file's size.
- Attachments: after `# Files mentioned by the user:` comes a `## name: path` list; the user's own words follow `## My request for Codex:`.
- Escaping: the desktop app stores typed input Markdown-escaped (`\~`, `\_`, `\-`, `&#x20;`); undo it.

## Assistant messages

- Remove `<oai-mem-citation>…</oai-mem-citation>` blocks.

## Size

- Median about 0.6 MB, up to about 100 MB (tool output and base64 images). Parse line by line; never load a whole file into context.
