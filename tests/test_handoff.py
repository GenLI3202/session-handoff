"""End-to-end tests on synthetic session files. Standard library only:

    python3 -m unittest discover -s tests -v      (pytest works too)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "skills" / "session-handoff" / "scripts" / "handoff.py"

CODEX_ID = "019a0000-0000-7000-8000-000000000001"
CODEX_ID_2 = "019a0000-0000-7000-8000-000000000002"
CLAUDE_ID = "c1a0de00-0000-4000-8000-000000000001"
CLAUDE_ID_2 = "c1a0de00-0000-4000-8000-000000000002"


def write_jsonl(path: Path, records: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")


def codex_msg(role: str, text: str, ts: str) -> dict:
    kind = "input_text" if role == "user" else "output_text"
    return {"timestamp": ts, "type": "response_item",
            "payload": {"type": "message", "role": role, "content": [{"type": kind, "text": text}]}}


def make_codex(root: Path, sid: str, day: str, turns: list, cwd: str = "/work/proj") -> Path:
    path = root / ".codex" / "sessions" / "2026" / "01" / day / ("rollout-2026-01-%sT10-00-00-%s.jsonl" % (day, sid))
    records = [{"timestamp": "2026-01-%sT10:00:00Z" % day, "type": "session_meta",
                "payload": {"cwd": cwd, "thread_source": "user"}}]
    for i, (user, assistant) in enumerate(turns):
        records.append(codex_msg("user", user, "2026-01-%sT10:%02d:00Z" % (day, i * 2 + 1)))
        records.append(codex_msg("assistant", assistant, "2026-01-%sT10:%02d:30Z" % (day, i * 2 + 1)))
    write_jsonl(path, records)
    return path


def index_codex(root: Path, entries: list) -> None:
    lines = [{"id": i, "thread_name": n, "updated_at": "2026-01-02T00:00:00Z"} for i, n in entries]
    write_jsonl(root / ".codex" / "session_index.jsonl", lines)


def make_claude(root: Path, sid: str, title: str, turns: list, extra: list = ()) -> Path:
    path = root / ".claude" / "projects" / "-work-proj" / (sid + ".jsonl")
    records = [{"type": "ai-title", "aiTitle": title, "sessionId": sid}]
    for i, (user, assistant) in enumerate(turns):
        ts = "2026-01-03T10:%02d:00Z" % (i * 2)
        records.append({"type": "user", "cwd": "/work/proj", "timestamp": ts, "message": {"content": user}})
        records.append({"type": "assistant", "timestamp": ts,
                        "message": {"content": [{"type": "thinking", "thinking": "SECRET-THOUGHT"},
                                                {"type": "text", "text": assistant}]}})
    records += list(extra)
    write_jsonl(path, records)
    return path


class CliCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def run_cli(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        base = {k: v for k, v in os.environ.items()
                if not k.startswith(("CODEX_", "CLAUDE_", "SESSION_HANDOFF_", "XDG_", "LC_", "LANG"))}
        base.update(SESSION_HANDOFF_HOME=str(self.home), SESSION_HANDOFF_NO_CACHE="1",
                    SESSION_HANDOFF_LANG="en", PYTHONIOENCODING="utf-8")
        base.update(env or {})
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                              encoding="utf-8", env=base)


class TestCodex(CliCase):
    def setUp(self) -> None:
        super().setUp()
        make_codex(self.home, CODEX_ID, "02", [
            ("<environment_context>cwd=/x</environment_context>\nplan the migration", "Step one is a dry run."),
            ("what about rollback?", "Keep a snapshot. <oai-mem-citation>x</oai-mem-citation>"),
        ])
        index_codex(self.home, [(CODEX_ID, "migration plan")])

    def test_show_by_name_filters_injected_blocks(self) -> None:
        r = self.run_cli("show", "migration plan")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("plan the migration", r.stdout)
        self.assertIn("Keep a snapshot.", r.stdout)
        self.assertNotIn("environment_context", r.stdout)
        self.assertNotIn("oai-mem-citation", r.stdout)
        self.assertIn("Working directory: /work/proj", r.stdout)

    def test_show_by_id_prefix_and_path(self) -> None:
        self.assertEqual(self.run_cli("show", CODEX_ID[:8]).returncode, 0)
        path = next((self.home / ".codex" / "sessions").rglob("rollout-*.jsonl"))
        r = self.run_cli("show", str(path))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("rollback", r.stdout)

    def test_partial_name_matches(self) -> None:
        self.assertEqual(self.run_cli("show", "migration").returncode, 0)

    def test_not_found(self) -> None:
        r = self.run_cli("show", "no such conversation")
        self.assertEqual(r.returncode, 1)
        self.assertIn("No conversation matches", r.stdout)

    def test_missing_path_is_an_error(self) -> None:
        r = self.run_cli("show", "/nonexistent/x.jsonl")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("File not found", r.stderr)

    def test_unnamed_session_hidden_unless_all(self) -> None:
        make_codex(self.home, CODEX_ID_2, "03", [("hello", "hi")])
        self.assertNotIn(CODEX_ID_2, self.run_cli("list").stdout)
        self.assertIn(CODEX_ID_2, self.run_cli("list", "--all").stdout)

    def test_codex_home_env_override(self) -> None:
        alt = self.home / "elsewhere"
        make_codex(alt, CODEX_ID_2, "04", [("alt question", "alt answer")])
        index_codex(alt, [(CODEX_ID_2, "alt session")])
        r = self.run_cli("show", "alt session", env={"CODEX_HOME": str(alt / ".codex")})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("alt answer", r.stdout)

    def test_config_file_override(self) -> None:
        alt = self.home / "elsewhere"
        make_codex(alt, CODEX_ID_2, "04", [("alt question", "alt answer")])
        index_codex(alt, [(CODEX_ID_2, "alt session")])
        cfg = self.home / ".config" / "session-handoff" / "config.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps({"codex_home": str(alt / ".codex")}), encoding="utf-8")
        self.assertEqual(self.run_cli("show", "alt session").returncode, 0)

    def test_lang_flag_switches_output(self) -> None:
        r = self.run_cli("--lang", "zh", "show", "migration plan")
        self.assertIn("接续材料", r.stdout)
        self.assertNotIn("Handoff material", r.stdout)


class TestClaude(CliCase):
    def setUp(self) -> None:
        super().setUp()
        extra = [
            {"type": "user", "message": {"content": [{"type": "tool_result", "content": "TOOL-OUTPUT"}]}},
            {"type": "user", "isMeta": True, "message": {"content": "META-NOISE"}},
            {"type": "user", "isSidechain": True, "message": {"content": "SIDECHAIN-NOISE"}},
            {"type": "user", "message": {"content": "<system-reminder>REMINDER</system-reminder>"}},
        ]
        make_claude(self.home, CLAUDE_ID, "Budget review", [
            ("summarise the budget", "Revenue is flat."), ("and costs?", "Costs rose 4%.")], extra)

    def test_filters_non_conversation_records(self) -> None:
        r = self.run_cli("show", "Budget review")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Costs rose 4%.", r.stdout)
        for noise in ("TOOL-OUTPUT", "META-NOISE", "SIDECHAIN-NOISE", "REMINDER", "SECRET-THOUGHT"):
            self.assertNotIn(noise, r.stdout)

    def test_duplicate_names_need_a_pick(self) -> None:
        make_claude(self.home, CLAUDE_ID_2, "Budget review", [("older chat", "older answer")])
        os.utime(self.home / ".claude" / "projects" / "-work-proj" / (CLAUDE_ID_2 + ".jsonl"), (1, 1))
        r = self.run_cli("show", "Budget review")
        self.assertEqual(r.returncode, 2)
        self.assertIn("Found 2 matching", r.stdout)
        self.assertIn("last user input: and costs?", r.stdout)
        picked = self.run_cli("show", "Budget review", "--pick", "1")
        self.assertEqual(picked.returncode, 0, picked.stderr)
        self.assertEqual(self.run_cli("show", "Budget review", "--pick", "9").returncode, 2)

    def test_claude_config_dir_override(self) -> None:
        alt = self.home / "alt-claude"
        (alt / "projects").mkdir(parents=True)
        (self.home / ".claude" / "projects").rename(alt / "projects")
        r = self.run_cli("show", "Budget review", env={"CLAUDE_CONFIG_DIR": str(alt)})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_untitled_session_uses_first_message(self) -> None:
        make_claude(self.home, CLAUDE_ID_2, "", [("a very specific opening question", "ok")])
        path = self.home / ".claude" / "projects" / "-work-proj" / (CLAUDE_ID_2 + ".jsonl")
        path.write_text("\n".join(path.read_text(encoding="utf-8").splitlines()[1:]) + "\n", encoding="utf-8")
        out = self.run_cli("list", "--query", "specific opening").stdout
        self.assertIn("a very specific opening question", out)

    def test_compaction_summary_kept(self) -> None:
        turns = [("q%d" % i, "a%d" % i) for i in range(6)]
        summary = {"type": "user", "isCompactSummary": True, "timestamp": "2026-01-03T09:00:00Z",
                   "message": {"content": "SUMMARY-OF-EARLIER-WORK"}}
        make_claude(self.home, CLAUDE_ID_2, "Long chat", turns, [])
        path = self.home / ".claude" / "projects" / "-work-proj" / (CLAUDE_ID_2 + ".jsonl")
        lines = path.read_text(encoding="utf-8").splitlines()
        lines.insert(5, json.dumps(summary))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        r = self.run_cli("show", "Long chat", "-n", "2")
        self.assertIn("SUMMARY-OF-EARLIER-WORK", r.stdout)
        self.assertIn("Earlier user input", r.stdout)


class TestCrossSource(CliCase):
    def test_source_filter_and_path_dispatch(self) -> None:
        make_codex(self.home, CODEX_ID, "02", [("codex question", "codex answer")])
        index_codex(self.home, [(CODEX_ID, "shared name")])
        make_claude(self.home, CLAUDE_ID, "shared name", [("claude question", "claude answer")])
        both = self.run_cli("show", "shared name")
        self.assertEqual(both.returncode, 2)
        only = self.run_cli("show", "shared name", "--source", "claude")
        self.assertIn("claude answer", only.stdout)
        self.assertNotIn("codex answer", only.stdout)

    def test_max_chars_truncates_but_keeps_latest_turns(self) -> None:
        big = "x" * 9000
        make_claude(self.home, CLAUDE_ID, "Big", [("q%d" % i, big + " end%d" % i) for i in range(6)])
        r = self.run_cli("show", "Big", "-n", "0", "--max-chars", "12000")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("q5", r.stdout)
        self.assertLess(len(r.stdout), 12000 + 3000)  # limit applies to the body, header is extra

    def test_out_file(self) -> None:
        make_claude(self.home, CLAUDE_ID, "Out", [("hello", "world")])
        target = self.home / "sub" / "handoff.md"
        r = self.run_cli("show", "Out", "--out", str(target))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("world", target.read_text(encoding="utf-8"))

    def test_session_files_are_not_modified(self) -> None:
        path = make_claude(self.home, CLAUDE_ID, "Readonly", [("hello", "world")])
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        self.run_cli("show", "Readonly")
        self.run_cli("list")
        self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))


class TestDoctor(CliCase):
    def test_reports_ok_when_sources_parse(self) -> None:
        make_codex(self.home, CODEX_ID, "02", [("hello", "world")])
        make_claude(self.home, CLAUDE_ID, "T", [("hello", "world")])
        r = self.run_cli("doctor")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("[Codex]", r.stdout)
        self.assertIn("[Claude]", r.stdout)

    def test_flags_nothing_found(self) -> None:
        r = self.run_cli("doctor")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no supported agent", r.stdout)

    def test_flags_format_drift(self) -> None:
        path = make_codex(self.home, CODEX_ID, "02", [("hello", "world")])
        write_jsonl(path, [{"timestamp": "2026-01-02T10:00:00Z", "kind": "future-format", "body": "?"}])
        r = self.run_cli("doctor")
        self.assertEqual(r.returncode, 1)
        self.assertIn("PROBLEM", r.stdout)


if __name__ == "__main__":
    unittest.main()
