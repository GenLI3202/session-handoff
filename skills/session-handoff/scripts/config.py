"""Where things live on this machine: environment variable > config file > default.

Config file: <XDG_CONFIG_HOME or ~/.config>/session-handoff/config.json, e.g.
  {"codex_home": "/data/codex", "claude_home": "~/claude-alt", "claude_desktop_dir": "...", "lang": "zh"}
See references/adapting.md.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def home() -> Path:
    """Root that contains .codex / .claude. Override with SESSION_HANDOFF_HOME for tests."""
    return Path(os.environ.get("SESSION_HANDOFF_HOME") or Path.home())


def xdg_dir(env_name: str, default_rel: str) -> Path:
    """XDG base directory; ignored while SESSION_HANDOFF_HOME is set so tests stay isolated."""
    if not os.environ.get("SESSION_HANDOFF_HOME") and os.environ.get(env_name):
        return Path(os.environ[env_name])
    return home() / default_rel


def config_path() -> Path:
    return xdg_dir("XDG_CONFIG_HOME", ".config") / "session-handoff" / "config.json"


def _file_config() -> dict:
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def setting(env_name: str, key: str, default=None):
    """First non-empty of: environment variable, config-file key, default."""
    value = os.environ.get(env_name)
    if value:
        return value
    return _file_config().get(key) or default
