#!/usr/bin/env python3
"""Find a conversation from another coding agent in local records and print handoff material.

Read-only toward session files. The Claude source keeps a small title cache in
~/.cache/session-handoff/ (disable with SESSION_HANDOFF_NO_CACHE=1).

  handoff.py doctor
  handoff.py list [--source NAME|all] [--query TEXT] [--limit 20] [--all]
  handoff.py show TARGET [--source ...] [-n 4] [--pick K] [--max-chars 24000] [--out FILE]

Global option: --lang en|zh (output language; default follows SESSION_HANDOFF_LANG, the
config file, then the locale).

TARGET is a conversation name, a session ID (or its first 8+ characters), or a path to
the record file. Exit codes: 0 ok, 1 not found / problem, 2 several matches (candidates printed).
"""
from __future__ import annotations

import argparse
import importlib
import pkgutil
import platform
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import i18n  # noqa: E402
from common import group_turns, local_time, one_line, render_handoff  # noqa: E402
from config import config_path  # noqa: E402
from i18n import t  # noqa: E402

REQUIRED = ("NAME", "LABEL", "roots", "owns", "sessions", "session_for_path", "messages")


def discover() -> list:
    """Names of all usable source modules in scripts/sources/ (a broken one is skipped with a warning)."""
    import sources
    names = []
    for info in pkgutil.iter_modules(sources.__path__):
        if info.name.startswith("_"):
            continue
        try:
            mod = importlib.import_module("sources." + info.name)
        except Exception as exc:  # a broken third-party adapter must not take the others down
            print("[sources.%s] cannot be imported: %s" % (info.name, exc), file=sys.stderr)
            continue
        missing = [a for a in REQUIRED if not hasattr(mod, a)]
        if missing:
            print("[sources.%s] skipped, missing: %s" % (info.name, ", ".join(missing)), file=sys.stderr)
            continue
        names.append(info.name)
    return names


SOURCES = discover()


def load(names: list) -> list:
    return [importlib.import_module("sources." + n) for n in names]


def selected(opt: str) -> list:
    return SOURCES if opt == "all" else [opt]


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().casefold()


def gather(mods: list, include_all: bool) -> list:
    out = []
    for m in mods:
        try:
            out += [(m, s) for s in m.sessions(include_all=include_all)]
        except Exception as exc:  # one broken source must not hide the others
            print(t("source_failed", label=m.LABEL, err=exc, name=m.NAME), file=sys.stderr)
    return out


def looks_like_path(target: str) -> bool:
    return "/" in target or "\\" in target or target.endswith(".jsonl") or target.startswith("~")


def resolve(target: str, mods: list) -> list:
    """Return list of (module, session). Path > ID > exact name > partial name."""
    p = Path(target).expanduser()
    if p.is_file():
        for m in load(SOURCES):
            if m.owns(p):
                return [(m, m.session_for_path(p))]
        raise SystemExit(t("unknown_owner", path=p))
    if looks_like_path(target):
        raise SystemExit(t("file_missing", path=p))

    key = norm(target)
    if re.fullmatch(r"[0-9a-f-]{8,36}", key):
        hits = [(m, s) for m, s in gather(mods, include_all=True) if s["id"].lower().startswith(key)]
        if hits:
            return hits

    pool = gather(mods, include_all=False)
    exact = [(m, s) for m, s in pool
             if key in {norm(s["title"])} | {norm(a) for a in s["aliases"]}]
    if exact:
        return exact
    return [(m, s) for m, s in pool
            if key in norm(s["title"]) or any(key in norm(a) for a in s["aliases"])]


def last_user(m, s: dict) -> str:
    last = ""
    try:
        for role, text, _ in m.messages(Path(s["path"])):
            if role == "user":
                last = text
    except OSError:
        pass
    return one_line(last, 80)


def print_candidates(hits: list, detail: bool) -> None:
    for k, (m, s) in enumerate(hits, 1):
        print("[%d] %s · %s · %s" % (k, s["source"], local_time(s["updated"]), s["title"] or t("unnamed")))
        print(t("cand_dir", v=s["cwd"] or t("unknown")))
        print(t("cand_id", v=s["id"]))
        if s["note"]:
            print(t("cand_note", v=s["note"]))
        if detail:
            print(t("cand_last", v=last_user(m, s) or t("none")))
        print(t("cand_file", v=s["path"]))


def cmd_list(args) -> int:
    pool = gather(load(selected(args.source)), include_all=args.all)
    if args.query:
        q = norm(args.query)
        pool = [(m, s) for m, s in pool
                if q in norm(s["title"]) or any(q in norm(a) for a in s["aliases"]) or q in norm(s["cwd"])]
    pool.sort(key=lambda x: x[1]["updated"] or 0, reverse=True)
    print_candidates(pool[: args.limit], detail=False)
    if len(pool) > args.limit:
        print(t("list_more", total=len(pool), limit=args.limit))
    return 0


def cmd_show(args) -> int:
    hits = resolve(args.target, load(selected(args.source)))
    hits.sort(key=lambda x: x[1]["updated"] or 0, reverse=True)
    if not hits:
        print(t("no_match", target=args.target))
        return 1
    if len(hits) > 1 and not args.pick:
        print(t("multi_match", n=len(hits)))
        print_candidates(hits[:10], detail=True)
        if len(hits) > 10:
            print(t("multi_more", n=len(hits) - 10))
        return 2
    if args.pick and not 1 <= args.pick <= len(hits):
        print(t("pick_range", n=len(hits)))
        return 2
    m, s = hits[(args.pick or 1) - 1]
    turns = group_turns(m.messages(Path(s["path"])))
    if not turns:
        print(t("no_text", path=s["path"], name=m.NAME))
        return 1
    text = render_handoff(s, turns, args.n, args.max_chars)
    if args.out:
        out = Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(t("written", path=out, n=len(text)))
    else:
        print(text)
    return 0


def cmd_doctor(_args) -> int:
    """Report what this machine looks like and whether each source still parses."""
    cfg = config_path()
    print(t("doc_env", py=platform.python_version(), os=platform.platform(), lang=i18n.current()))
    print(t("doc_config", path=cfg, state=t("doc_present") if cfg.is_file() else t("doc_absent")))
    problems = 0
    found_any = False
    for m in load(SOURCES):
        print("\n[%s] (%s)" % (m.LABEL, m.NAME))
        print(t("doc_roots"))
        for r in m.roots():
            print("    %s %s" % ("✓" if r.exists() else "✗", r))
        try:
            pool = m.sessions(include_all=True)
        except Exception as exc:
            print(t("doc_error", err=exc))
            problems += 1
            continue
        if not pool:
            print(t("doc_none"))
            continue
        found_any = True
        pool.sort(key=lambda s: s["updated"] or 0, reverse=True)
        sample = pool[:5]
        ok = 0
        for s in sample:
            try:
                if group_turns(m.messages(Path(s["path"]))):
                    ok += 1
            except Exception:  # unreadable or malformed counts as "no text"
                pass
        print(t("doc_count", n=len(pool), checked=len(sample), ok=ok))
        if ok == 0:
            print(t("doc_drift"))
            problems += 1
    if not found_any:
        print("\n" + t("doc_nothing"))
        problems += 1
    if not problems:
        print("\n" + t("doc_ok"))
    return 1 if problems else 0


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to a legacy code page
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="Read another agent's local session record and print handoff material")
    ap.add_argument("--lang", choices=["en", "zh"], help="output language (default: auto)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    choices = SOURCES + ["all"]

    d = sub.add_parser("doctor", help="check which sources exist on this machine and whether they parse")
    d.set_defaults(func=cmd_doctor)

    a = sub.add_parser("list", help="list conversations")
    a.add_argument("--source", choices=choices, default="all")
    a.add_argument("--query", help="filter by name or directory")
    a.add_argument("--limit", type=int, default=20)
    a.add_argument("--all", action="store_true", help="include unnamed Codex sessions and sub-agent sessions")
    a.set_defaults(func=cmd_list)

    b = sub.add_parser("show", help="print handoff material")
    b.add_argument("target", help="conversation name, session ID (first 8+ characters) or record file path")
    b.add_argument("--source", choices=choices, default="all")
    b.add_argument("-n", type=int, default=4, help="how many recent turns to give in full (default 4, 0 = all)")
    b.add_argument("--pick", type=int, help="which match to use when there are several")
    b.add_argument("--max-chars", type=int, default=24000, help="output size limit (default 24000)")
    b.add_argument("--out", help="write to a file instead of printing")
    b.set_defaults(func=cmd_show)

    args = ap.parse_args(argv)
    if args.lang:
        i18n.set_lang(args.lang)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
