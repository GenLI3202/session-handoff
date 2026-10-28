"""Codex source: <CODEX_HOME or ~/.codex>/sessions/**/rollout-*-<id>.jsonl, names in session_index.jsonl.

Format notes and known pitfalls: references/source-codex.md
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

from common import home, iter_jsonl, last_timestamp, make_session, stamp, strip_tags
from config import setting
from i18n import t

NAME = "codex"
LABEL = "Codex"

# Blocks Codex injects into user messages (context, skills, notices), plus Claude Code
# command tags that appear in threads Codex imported from Claude.
INJECTED_TAGS = [
    "recommended_plugins", "INSTRUCTIONS", "environment_context", "user_instructions",
    "skill", "turn_aborted", "subagent_notification", "permissions[\\w -]*",
    "apps_instructions", "collaboration_mode", "user_shell_command",
    "command-name", "command-message", "command-args", "local-command-stdout",
    "local-command-stderr", "local-command-caveat", "system-reminder", "task-notification",
]
ASSISTANT_TAGS = ["oai-mem-citation"]
SKIP_THREAD_SOURCES = {"subagent", "guardian_review"}


def _root() -> Path:
    return Path(setting("CODEX_HOME", "codex_home") or home() / ".codex").expanduser()


def roots() -> list:
    r = _root()
    return [r / "sessions", r / "archived_sessions", r / "session_index.jsonl"]


def owns(path: Path) -> bool:
    return path.suffix == ".jsonl" and path.name.startswith("rollout-")


def _id_from_name(name: str) -> str:
    # rollout-YYYY-MM-DDTHH-MM-SS-<36-char id>.jsonl
    return name[:-6][-36:]


def _files() -> dict:
    out = {}
    for sub in ("sessions", "archived_sessions"):
        base = _root() / sub
        if base.is_dir():
            for p in base.glob("**/rollout-*.jsonl"):
                out[_id_from_name(p.name)] = p
    return out


def _meta(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            first = json.loads(fh.readline())
        return first.get("payload") or {}
    except (OSError, ValueError):
        return {}


def _names() -> dict:
    """id -> {"title": latest name, "aliases": all names}. Renames append new lines."""
    out = {}
    idx = _root() / "session_index.jsonl"
    if idx.is_file():
        for r in iter_jsonl(idx):
            sid, name = r.get("id"), (r.get("thread_name") or "").strip()
            if not sid or not name:
                continue
            ts = r.get("updated_at") or ""
            e = out.setdefault(sid, {"title": name, "ts": ts, "aliases": []})
            if name not in e["aliases"]:
                e["aliases"].append(name)
            if ts >= e["ts"]:
                e["title"], e["ts"] = name, ts
    # threads Codex imported from Claude: names live in the import ledger
    ledger = _root() / "external_agent_session_imports.json"
    if ledger.is_file():
        try:
            recs = json.loads(ledger.read_text(encoding="utf-8")).get("records", [])
        except (OSError, ValueError):
            recs = []
        for r in recs:
            sid = r.get("imported_thread_id")
            if sid and sid not in out:
                title = (r.get("title") or "").strip()
                out[sid] = {"title": title, "ts": "", "aliases": [title] if title else [],
                            "imported_from": r.get("source_path", "")}
    return out


def sessions(include_all: bool = False) -> list:
    files = _files()
    names = _names()
    out = []
    ids = set(files) if include_all else set(names) & set(files)
    for sid in ids:
        path = files[sid]
        meta = _meta(path)
        if not include_all and meta.get("thread_source") in SKIP_THREAD_SOURCES:
            continue
        n = names.get(sid, {})
        note = ""
        if n.get("imported_from"):
            note = t("note_imported", path=n["imported_from"])
        if meta.get("thread_source") in SKIP_THREAD_SOURCES:
            note = (note + "; " if note else "") + t("note_subagent")
        out.append(make_session(
            source=LABEL, id=sid, title=n.get("title", ""), aliases=n.get("aliases", []),
            cwd=meta.get("cwd", ""), path=str(path), updated=last_timestamp(path), note=note,
        ))
    return out


def session_for_path(path: Path) -> dict:
    sid = _id_from_name(path.name)
    n = _names().get(sid, {})
    return make_session(source=LABEL, id=sid, title=n.get("title", ""), aliases=n.get("aliases", []),
                        cwd=_meta(path).get("cwd", ""), path=str(path), updated=last_timestamp(path))


def _unescape(text: str) -> str:
    """Codex Desktop stores typed input Markdown-escaped (\\~, \\_, &#x20;)."""
    text = html.unescape(text)
    return re.sub(r"\\([\\`*_{}\[\]()#+\-.!~<>|&])", r"\1", text)


def _files_mentioned(text: str) -> str:
    """'# Files mentioned by the user: ## name: path ... ## My request for Codex: <text>'
    -> '<text>' followed by one attachment line."""
    if "# Files mentioned by the user:" not in text:
        return text
    head, sep, request = text.partition("## My request for Codex:")
    files = re.findall(r"(?m)^## (.+?): (\S.*)$", head)
    note = "[attachments: %s]" % "; ".join(p for _, p in files) if files else ""
    body = request if sep else re.sub(r"(?s)# Files mentioned by the user:.*", "", text)
    return (body.strip() + ("\n" + note if note else "")).strip()


def _clean_user(text: str) -> str:
    text = strip_tags(text, INJECTED_TAGS)
    text = re.sub(r"(?im)^#+ AGENTS\.md instructions.*$", "", text)
    text = re.sub(r"(?is)<image\b[^>]*>\s*</image>", "", text)
    return _files_mentioned(text.strip())


def messages(path: Path):
    """Yield (role, text, ts) for user/assistant text and compaction summaries."""
    for r in iter_jsonl(path):
        kind = r.get("type")
        p = r.get("payload") if isinstance(r.get("payload"), dict) else {}
        ts = stamp(r.get("timestamp"))
        if kind == "compacted":
            msg = (p.get("message") or "").strip()
            if msg:
                yield ("summary", msg, ts)
            continue
        if kind != "response_item" or p.get("type") != "message":
            continue
        role = p.get("role")
        if role not in ("user", "assistant"):
            continue
        parts = []
        for c in p.get("content") or []:
            if isinstance(c, dict) and c.get("type") in ("input_text", "output_text", "text"):
                parts.append(c.get("text") or "")
        text = "\n".join(parts)
        if role == "user":
            text = _unescape(_clean_user(text))
        else:
            text = strip_tags(text, ASSISTANT_TAGS).strip()
        if text:
            yield (role, text, ts)
