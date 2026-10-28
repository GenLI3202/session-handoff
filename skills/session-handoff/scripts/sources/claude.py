"""Claude source: <CLAUDE_CONFIG_DIR or ~/.claude>/projects/<encoded cwd>/<session id>.jsonl (Claude Code
CLI and the Code tab of Claude Desktop), plus local Claude Desktop agent sessions under
<desktop app dir>/local-agent-mode-sessions/**/.claude/projects/.

Format notes and known pitfalls: references/source-claude.md
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from common import home, iter_jsonl, last_timestamp, make_session, one_line, stamp, strip_tags
from config import setting, xdg_dir
from i18n import t

NAME = "claude"
LABEL = "Claude"

NOISE_TAGS = [
    "command-name", "command-message", "command-args", "local-command-stdout",
    "local-command-stderr", "local-command-caveat", "system-reminder",
]
CACHE_VERSION = 1


def _config_dir() -> Path:
    return Path(setting("CLAUDE_CONFIG_DIR", "claude_home") or home() / ".claude").expanduser()


def _app_dirs() -> list:
    """Claude Desktop's data directory. Every OS-specific location is a candidate; only existing ones are read."""
    explicit = setting("CLAUDE_DESKTOP_DIR", "claude_desktop_dir")
    if explicit:
        return [Path(explicit).expanduser()]
    h = home()
    cands = [h / "Library" / "Application Support" / "Claude"]                       # macOS
    appdata = None if os.environ.get("SESSION_HANDOFF_HOME") else os.environ.get("APPDATA")
    cands.append(Path(appdata) / "Claude" if appdata else h / "AppData" / "Roaming" / "Claude")  # Windows
    cands.append(xdg_dir("XDG_CONFIG_HOME", ".config") / "Claude")                   # Linux
    return cands


def roots() -> list:
    return [_config_dir() / "projects"] + [d / "local-agent-mode-sessions" for d in _app_dirs()]


def owns(path: Path) -> bool:
    return path.suffix == ".jsonl" and path.parent.parent.name == "projects"


def _transcripts() -> list:
    out = []
    main = _config_dir() / "projects"
    if main.is_dir():
        out += list(main.glob("*/*.jsonl"))
    for app in _app_dirs():
        agent = app / "local-agent-mode-sessions"
        if agent.is_dir():
            for proj in agent.glob("**/.claude/projects"):
                out += list(proj.glob("*/*.jsonl"))
    return out


def _desktop_titles() -> dict:
    """cliSessionId -> title from Claude Desktop session metadata (local_*.json)."""
    out = {}
    for app in _app_dirs():
        for sub in ("claude-code-sessions", "local-agent-mode-sessions"):
            base = app / sub
            if not base.is_dir():
                continue
            for p in base.glob("**/local_*.json"):
                if ".claude" in p.parts:
                    continue
                try:
                    d = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if not isinstance(d, dict):
                    continue
                sid = d.get("cliSessionId") or d.get("sessionId")
                title = (d.get("title") or "").strip()
                if sid and title:
                    out[sid] = {"title": title, "cwd": d.get("cwd") or ""}
    return out


def _text(record: dict) -> str:
    msg = record.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = "\n".join(
            b.get("text") or "" for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    else:
        return ""
    return strip_tags(text, NOISE_TAGS).strip()


def _scan(path: Path) -> dict:
    """One pass over a transcript: titles, last cwd, first real user message."""
    info = {"custom": "", "ai": "", "agent": "", "cwd": "", "first": ""}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            hit_title = "custom-title" in line or "ai-title" in line or "agent-name" in line
            hit_cwd = '"cwd"' in line
            need_first = not info["first"] and '"user"' in line
            if not (hit_title or hit_cwd or need_first):
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            kind = r.get("type")
            if kind == "custom-title":
                info["custom"] = r.get("customTitle") or info["custom"]
            elif kind == "ai-title":
                info["ai"] = r.get("aiTitle") or info["ai"]
            elif kind == "agent-name":
                info["agent"] = r.get("agentName") or info["agent"]
            if r.get("cwd"):
                info["cwd"] = r["cwd"]
            if (need_first and kind == "user" and not r.get("isMeta")
                    and not r.get("isSidechain") and not r.get("isCompactSummary")):
                text = _text(r)
                if text:
                    info["first"] = one_line(text, 60)
    return info


def _cache_path() -> Path:
    return xdg_dir("XDG_CACHE_HOME", ".cache") / "session-handoff" / "claude-index.json"


def _load_cache() -> dict:
    if os.environ.get("SESSION_HANDOFF_NO_CACHE"):
        return {}
    try:
        d = json.loads(_cache_path().read_text(encoding="utf-8"))
        return d.get("files", {}) if d.get("v") == CACHE_VERSION else {}
    except (OSError, ValueError):
        return {}


def _save_cache(files: dict) -> None:
    if os.environ.get("SESSION_HANDOFF_NO_CACHE"):
        return
    try:
        p = _cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"v": CACHE_VERSION, "files": files}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)
    except OSError:
        pass


def _build(path: Path, info: dict, desktop: dict) -> dict:
    sid = path.stem
    d = desktop.get(sid, {})
    titles = [info["custom"], d.get("title", ""), info["ai"], info["agent"]]
    aliases = [x for x in titles if x]
    title = aliases[0] if aliases else info["first"]
    note = "" if aliases else t("note_untitled")
    return make_session(
        source=LABEL, id=sid, title=title, aliases=aliases, cwd=info["cwd"] or d.get("cwd", ""),
        path=str(path), updated=last_timestamp(path), note=note,
    )


def sessions(include_all: bool = False) -> list:
    cache = _load_cache()
    fresh = {}
    desktop = _desktop_titles()
    out = []
    for path in _transcripts():
        try:
            st = path.stat()
        except OSError:
            continue
        key = str(path)
        c = cache.get(key)
        if c and c.get("m") == st.st_mtime and c.get("s") == st.st_size:
            info = c["i"]
        else:
            try:
                info = _scan(path)
            except OSError:
                continue
        fresh[key] = {"m": st.st_mtime, "s": st.st_size, "i": info}
        out.append(_build(path, info, desktop))
    _save_cache(fresh)
    return out


def session_for_path(path: Path) -> dict:
    return _build(path, _scan(path), _desktop_titles())


def messages(path: Path):
    """Yield (role, text, ts). Skips tool results, injected (isMeta) and sub-agent (isSidechain)
    records, thinking and image blocks. Compaction summaries come out as role 'summary'."""
    for r in iter_jsonl(path):
        kind = r.get("type")
        if kind not in ("user", "assistant") or r.get("isSidechain"):
            continue
        ts = stamp(r.get("timestamp"))
        text = _text(r)
        if not text:
            continue
        if r.get("isCompactSummary"):
            yield ("summary", text, ts)
            continue
        if r.get("isMeta"):
            continue
        yield (kind, text, ts)
