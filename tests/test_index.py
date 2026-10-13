"""Behavioral tests for PyGit's staging-index operations.

Run from your PyGit project root:
    python -m unittest tests.test_index -v
"""

import json
import tempfile
import unittest
from pathlib import Path

from pygit.errors import PyGitError
from pygit.index import load_index, remove_entry, save_entry, stage_entry


class TestIndex(unittest.TestCase):
    def setUp(self):
        """Create a fresh index inside a disposable directory per test."""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.pygit_dir = Path(temp.name) / ".pygit"
        self.pygit_dir.mkdir()
        self.index_path = self.pygit_dir / "index.json"
        self.index_path.write_bytes(b'{"conflicts":[],"entries":[],"version":1}\n')

    def test_load_initial_index(self):
        self.assertEqual(
            load_index(self.pygit_dir),
            {"conflicts": [], "entries": [], "version": 1},
        )

    def test_stage_new_entry(self):
        index = load_index(self.pygit_dir)
        stage_entry(index, "hello.txt", "a" * 64)
        self.assertEqual(
            index["entries"],
            [{"path": "hello.txt", "oid": "a" * 64}],
        )

    def test_stage_existing_entry_replaces_oid(self):
        index = load_index(self.pygit_dir)
        stage_entry(index, "hello.txt", "a" * 64)
        stage_entry(index, "hello.txt", "b" * 64)
        self.assertEqual(len(index["entries"]), 1)
        self.assertEqual(index["entries"][0]["oid"], "b" * 64)

    def test_stage_multiple_entries_uses_utf8_byte_order(self):
        index = load_index(self.pygit_dir)
        for path in ("é.txt", "z.txt", "a.txt", "中.txt"):
            stage_entry(index, path, "c" * 64)
        self.assertEqual(
            [entry["path"] for entry in index["entries"]],
            sorted(("é.txt", "z.txt", "a.txt", "中.txt"), key=lambda p: p.encode("utf-8")),
        )

    def test_remove_entry_leaves_others_unchanged(self):
        index = load_index(self.pygit_dir)
        stage_entry(index, "a.txt", "a" * 64)
        stage_entry(index, "b.txt", "b" * 64)
        remove_entry(index, "a.txt")
        self.assertEqual(index["entries"], [{"path": "b.txt", "oid": "b" * 64}])

    def test_remove_missing_entry_raises_pygit_error(self):
        index = load_index(self.pygit_dir)
        with self.assertRaises(PyGitError):
            remove_entry(index, "missing.txt")

    def test_mutations_are_in_memory_until_save(self):
        original = self.index_path.read_bytes()
        index = load_index(self.pygit_dir)
        stage_entry(index, "new.txt", "d" * 64)
        self.assertEqual(self.index_path.read_bytes(), original)

    def test_save_and_reload_index(self):
        index = load_index(self.pygit_dir)
        stage_entry(index, "main.py", "a" * 64)
        stage_entry(index, "README.md", "b" * 64)
        save_entry(self.pygit_dir, index)
        self.assertEqual(load_index(self.pygit_dir), index)

    def test_save_is_compact_sorted_json_with_one_newline(self):
        index = load_index(self.pygit_dir)
        stage_entry(index, "a.txt", "a" * 64)
        save_entry(self.pygit_dir, index)
        expected = (
            json.dumps(index, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            + "\n"
        ).encode("utf-8")
        self.assertEqual(self.index_path.read_bytes(), expected)
        self.assertTrue(expected.endswith(b"\n"))
        self.assertFalse(expected.endswith(b"\n\n"))

    def test_save_rejects_unsupported_version(self):
        bad_index = {"conflicts": [], "entries": [], "version": 2}
        before = self.index_path.read_bytes()
        with self.assertRaises(PyGitError):
            save_entry(self.pygit_dir, bad_index)
        self.assertEqual(self.index_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
