"""Validation and failure-path tests for PyGit's staging index.

Run from your PyGit project root:
    python -m unittest tests.test_index_validation -v

Some cases may fail until load_index() validates all required fields and types.
That is intentional: the failures identify missing validation rules.
"""

import json
import tempfile
import unittest
from pathlib import Path

from pygit.errors import PyGitError
from pygit.index import load_index


class TestIndexValidation(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.pygit_dir = Path(temp.name) / ".pygit"
        self.pygit_dir.mkdir()
        self.index_path = self.pygit_dir / "index.json"

    def write_json(self, data):
        self.index_path.write_text(json.dumps(data) + "\n", encoding="utf-8")

    def assert_invalid_index(self, data):
        self.write_json(data)
        with self.assertRaises(PyGitError):
            load_index(self.pygit_dir)

    def test_missing_index_file_raises_pygit_error(self):
        with self.assertRaises(PyGitError):
            load_index(self.pygit_dir)

    def test_malformed_json_raises_pygit_error(self):
        self.index_path.write_text('{"entries": [', encoding="utf-8")
        with self.assertRaises(PyGitError):
            load_index(self.pygit_dir)

    def test_top_level_list_is_not_an_index(self):
        self.assert_invalid_index([])

    def test_missing_version_is_invalid(self):
        self.assert_invalid_index({"conflicts": [], "entries": []})

    def test_missing_entries_is_invalid(self):
        self.assert_invalid_index({"conflicts": [], "version": 1})

    def test_missing_conflicts_is_invalid(self):
        self.assert_invalid_index({"entries": [], "version": 1})

    def test_unsupported_version_is_invalid(self):
        self.assert_invalid_index({"conflicts": [], "entries": [], "version": 2})

    def test_entries_must_be_a_list(self):
        self.assert_invalid_index({"conflicts": [], "entries": "not-a-list", "version": 1})

    def test_conflicts_must_be_a_list(self):
        self.assert_invalid_index({"conflicts": "not-a-list", "entries": [], "version": 1})


if __name__ == "__main__":
    unittest.main()
