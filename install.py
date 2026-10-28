#!/usr/bin/env python3
"""Install the session-handoff skill into the skill folders of the agents found on this machine.

  python3 install.py                 install into every detected agent
  python3 install.py --dry-run       show what would happen
  python3 install.py --target DIR    install into DIR/session-handoff (repeatable; skips detection)

Re-run after pulling updates. Only ever replaces a folder named session-handoff.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

NAME = "session-handoff"
SRC = Path(__file__).resolve().parent / "skills" / NAME


def detected_targets() -> list:
    """(agent, skills folder) for every agent whose data folder exists on this machine."""
    home = Path.home()
    claude = Path(os.environ.get("CLAUDE_CONFIG_DIR") or home / ".claude").expanduser()
    codex = Path(os.environ.get("CODEX_HOME") or home / ".codex").expanduser()
    found = []
    if claude.is_dir():
        found.append(("Claude Code", claude / "skills"))
    if codex.is_dir() or (home / ".agents").is_dir():
        found.append(("Codex", home / ".agents" / "skills"))
    if (home / ".gemini").is_dir():
        found.append(("Gemini CLI", home / ".gemini" / "skills"))
    return found


def install(label: str, skills_dir: Path, dry_run: bool) -> bool:
    dest = skills_dir / NAME
    if dest.is_symlink():
        print("skip  %s: %s is a symlink (left alone)" % (label, dest))
        return False
    if dest.exists() and dest.resolve() == SRC.resolve():
        print("skip  %s: %s is the source folder" % (label, dest))
        return False
    print("%s %s -> %s" % ("would install" if dry_run else "install", label, dest))
    if dry_run:
        return True
    skills_dir.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(SRC, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--target", action="append", default=[], metavar="DIR",
                    help="skills folder to install into (repeatable)")
    args = ap.parse_args()

    if not (SRC / "SKILL.md").is_file():
        print("cannot find %s; run install.py from a full checkout" % (SRC / "SKILL.md"), file=sys.stderr)
        return 1
    targets = [("custom", Path(t).expanduser()) for t in args.target] or detected_targets()
    if not targets:
        print("No supported agent folder found (~/.claude, ~/.codex, ~/.agents, ~/.gemini).\n"
              "Use --target <skills folder> for your agent.")
        return 1
    done = [install(label, d, args.dry_run) for label, d in targets]
    if args.dry_run or not any(done):
        return 0
    print("\nSelf-check (doctor):\n")
    return subprocess.call([sys.executable, str(SRC / "scripts" / "handoff.py"), "doctor"])


if __name__ == "__main__":
    sys.exit(main())
