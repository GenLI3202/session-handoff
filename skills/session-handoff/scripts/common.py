"""Shared helpers: JSONL reading, text cleanup, turn grouping, Markdown output.

Compatible with Python 3.9. Standard library only.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Optional

from config import home  # noqa: F401  (re-exported for the source adapters)
from i18n import t


def iter_jsonl(path) -> Iterator[dict]:
    """Yield parsed records line by line; skip lines that are not valid JSON."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def iso_to_epoch(value) -> Optional[float]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def local_time(epoch: Optional[float]) -> str:
    if epoch is None:
        return "?"
    return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def last_timestamp(path) -> Optional[float]:
    """Epoch of the last record's "timestamp" (read from the file tail); file mtime as fallback."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            fh.seek(max(0, size - 262144))
            tail = fh.read().decode("utf-8", errors="replace")
        for line in reversed(tail.splitlines()):
            m = re.search(r'"timestamp"\s*:\s*"([^"]+)"', line)
            if m:
                epoch = iso_to_epoch(m.group(1))
                if epoch:
                    return epoch
        return os.path.getmtime(path)
    except OSError:
        return None


def stamp(iso_value) -> str:
    epoch = iso_to_epoch(iso_value)
    return local_time(epoch) if epoch else ""


def strip_tags(text: str, tags: Iterable[str]) -> str:
    """Remove <tag ...>...</tag> blocks for the given tag-name patterns."""
    if not text:
        return ""
    names = "|".join(tags)
    return re.sub(r"(?is)<(%s)\b[^>]*>.*?</\1\s*>" % names, "", text)


def one_line(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def make_session(**kw) -> dict:
    s = {
        "source": "",
        "id": "",
        "title": "",
        "aliases": [],
        "cwd": "",
        "path": "",
        "updated": None,
        "note": "",
    }
    s.update(kw)
    return s


# ---------------------------------------------------------------- turns

def group_turns(messages) -> list:
    """messages: iterable of (role, text, ts) with role in user/assistant/summary.

    Returns a list of turns: {"user": str|None, "ts": str|None, "assistant": [str], "summary": bool}
    """
    turns = []
    current = None
    for role, text, ts in messages:
        if role == "summary":
            if current:
                turns.append(current)
            turns.append({"user": None, "ts": ts, "assistant": [text], "summary": True})
            current = None
        elif role == "user":
            if current:
                turns.append(current)
            current = {"user": text, "ts": ts, "assistant": [], "summary": False}
        elif role == "assistant":
            if current is None:
                current = {"user": None, "ts": ts, "assistant": [], "summary": False}
            current["assistant"].append(text)
    if current:
        turns.append(current)
    return turns


def _shorten(text: str, keep: int) -> str:
    if len(text) <= keep:
        return text
    half = keep // 2
    cut = len(text) - 2 * half
    return text[:half] + "\n\n" + t("elided", n=cut) + "\n\n" + text[-half:]


def _render_turn(turn: dict) -> str:
    stamp_text = turn.get("ts") or ""
    suffix = " · " + stamp_text if stamp_text else ""
    if turn["summary"]:
        return "### %s%s\n\n%s\n" % (t("summary_head"), suffix, "\n\n".join(turn["assistant"]))
    label = t("turn", n=turn["no"]) if turn["no"] else t("turn_start")
    parts = ["### %s%s" % (label, suffix)]
    if turn["user"] is not None:
        parts.append(t("role_user") + "\n\n" + turn["user"])
    if turn["assistant"]:
        parts.append(t("role_assistant") + "\n\n" + "\n\n".join(turn["assistant"]))
    else:
        parts.append(t("role_assistant") + "\n\n" + t("no_reply"))
    return "\n\n".join(parts) + "\n"


def render_handoff(session: dict, turns: list, recent: int, max_chars: int) -> str:
    """recent = number of most recent user turns to give in full (0 = all)."""
    no = 0
    numbered = []
    for turn in turns:
        turn = dict(turn, assistant=list(turn["assistant"]))
        if not turn["summary"] and turn["user"] is not None:
            no += 1
        turn["no"] = 0 if turn["summary"] or (turn["user"] is None and no == 0) else no
        numbered.append(turn)
    total = no

    start = 0
    if recent > 0 and total > recent:
        first_no = total - recent + 1
        start = next(i for i, x in enumerate(numbered)
                     if not x["summary"] and x["user"] is not None and x["no"] == first_no)
    win = numbered[start:]
    older = numbered[:start]
    # the latest compaction summary before the window covers everything older: keep it in full
    last_summary = max((i for i, x in enumerate(older) if x["summary"]), default=None)
    if last_summary is not None:
        win = [older[last_summary]] + win
        older = older[:last_summary] + older[last_summary + 1:]

    def body(items: list) -> str:
        return "\n".join(_render_turn(x) for x in items)

    def is_user_turn(x: dict) -> bool:
        return not x["summary"] and x["user"] is not None

    # 1) move whole older turns to the excerpt list, keeping at least 2 user turns in full
    text = body(win)
    while len(text) > max_chars and sum(1 for x in win if is_user_turn(x)) > 2:
        moved = win.pop(1 if win[0]["summary"] and len(win) > 1 else 0)
        older.append(moved)
        text = body(win)

    # 2) still too long: halve the longest single message, earlier turns first, last turn last
    def longest(items: list):
        best = None
        for ti, x in enumerate(items):
            for mi, m in enumerate(x["assistant"]):
                if best is None or len(m) > best[0]:
                    best = (len(m), ti, "a", mi)
            if x["user"] and (best is None or len(x["user"]) > best[0]):
                best = (len(x["user"]), ti, "u", 0)
        return best

    for scope in ("earlier", "all"):
        while len(text) > max_chars:
            items = win[:-1] if scope == "earlier" and len(win) > 1 else win
            best = longest(items)
            if not best or best[0] <= 3000:
                break
            size, ti, kind, mi = best
            keep = max(3000, size // 2)
            original = items[ti]["assistant"][mi] if kind == "a" else items[ti]["user"]
            shortened = _shorten(original, keep)
            if len(shortened) >= len(original):  # the elision marker made it longer: cannot shrink further
                break
            if kind == "a":
                items[ti]["assistant"][mi] = shortened
            else:
                items[ti]["user"] = shortened
            text = body(win)
    if len(text) > max_chars:
        text = _shorten(text, max_chars)

    shown = sum(1 for x in win if is_user_turn(x))
    head = [
        t("h_title", title=session.get("title") or t("unnamed")),
        "",
        t("h_source", v=session["source"]),
        t("h_id", v=session.get("id", "")),
        t("h_cwd", v=session.get("cwd") or t("unknown")),
        t("h_file", v=session.get("path", "")),
        t("h_updated", v=local_time(session.get("updated"))),
        t("h_turns", total=total, shown=shown, older=t("h_turns_older") if older else ""),
    ]
    if session.get("note"):
        head.append(t("h_note", v=session["note"]))
    head += ["", t("h_disclaimer"), ""]
    if older:
        head += [t("h_older"), ""]
        rows = []
        for x in older:
            if x["summary"]:
                rows.append(t("older_compacted"))
            elif x["user"] is not None:
                rows.append("%d. %s" % (x["no"], one_line(x["user"], 120)))
        if len(rows) > 23:  # first 3 show where it started, last 20 lead into the recent turns
            rows = rows[:3] + [t("older_elided", n=len(rows) - 23)] + rows[-20:]
        head += rows
        head.append("")
    head += [t("h_recent"), ""]
    return "\n".join(head) + text
