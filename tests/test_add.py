"""Integration tests for PyGit's threaded `add` command.

Place this file at tests/test_add.py and run from the project root:

    python -m unittest tests.test_add -v
    python -m unittest discover -s tests -v

Each test uses a fresh temporary repository and never modifies your real .pygit.
These tests target the current regular-file-only add implementation.
"""

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from pygit import index, objects
from pygit.errors import PyGitError
from pygit.pygit_add import add


class TestAdd(unittest.TestCase):
    def setUp(self):
        """Set up an isolated working tree, object database, and staging index."""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)

        self.root = Path(temp.name).resolve()
        self.pygit_dir = self.root / ".pygit"
        (self.pygit_dir / "objects").mkdir(parents=True)
        self.index_path = self.pygit_dir / "index.json"
        self.index_path.write_bytes(
            b'{"conflicts":[],"entries":[],"version":1}\n'
        )

        original_cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, original_cwd)

    def write_file(self, relative_path: str, content: bytes) -> Path:
        """Create a file in the temporary working tree."""
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def run_add(self, *paths: str | Path) -> None:
        """Call the real command handler with argparse-like arguments."""
        add(SimpleNamespace(paths=[str(path) for path in paths]))

    def staged_entries(self) -> list[dict]:
        return index.load_index(self.pygit_dir)["entries"]

    @staticmethod
    def expected_blob_oid(content: bytes) -> str:
        """Independently calculate the SHA-256 ID of a PyGit blob."""
        envelope = f"blob {len(content)}\0".encode("ascii") + content
        return hashlib.sha256(envelope).hexdigest()

    def test_add_one_file_stores_blob_and_stages_repository_relative_path(self):
        content = b'print("hello")\n'
        self.write_file("hello.py", content)

        self.run_add("hello.py")

        entries = self.staged_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["path"], "hello.py")
        self.assertEqual(entries[0]["oid"], self.expected_blob_oid(content))
        self.assertTrue(objects.object_path(self.pygit_dir, entries[0]["oid"]).is_file())
        self.assertEqual(objects.read_blob(self.pygit_dir, entries[0]["oid"]), content)

    def test_add_multiple_files_preserves_all_entries_and_utf8_order(self):
        contents = {
            "z.py": b"z\n",
            "a.txt": b"a\n",
            "src/helper.py": b"helper\n",
            "\u00e9.txt": b"accented\n",
        }
        for path, content in contents.items():
            self.write_file(path, content)

        self.run_add(*contents)

        entries = self.staged_entries()
        expected_paths = sorted(contents, key=lambda p: p.encode("utf-8"))
        self.assertEqual([entry["path"] for entry in entries], expected_paths)
        for entry in entries:
            with self.subTest(path=entry["path"]):
                self.assertEqual(
                    objects.read_blob(self.pygit_dir, entry["oid"]),
                    contents[entry["path"]],
                )

    def test_add_from_nested_directory_uses_repository_relative_path(self):
        self.write_file("src/pkg/module.py", b"module data\n")
        os.chdir(self.root / "src" / "pkg")

        self.run_add("module.py")

        entries = self.staged_entries()
        self.assertEqual([entry["path"] for entry in entries], ["src/pkg/module.py"])

    def test_add_using_absolute_path_still_stores_relative_path(self):
        absolute_path = self.write_file("src/main.py", b"absolute path\n")

        self.run_add(absolute_path)

        self.assertEqual(self.staged_entries()[0]["path"], "src/main.py")

    def test_readding_modified_file_updates_oid_without_duplicate(self):
        source = self.write_file("main.py", b"old version\n")
        self.run_add("main.py")
        first_oid = self.staged_entries()[0]["oid"]

        source.write_bytes(b"new version\n")
        self.run_add("main.py")

        entries = self.staged_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["path"], "main.py")
        self.assertNotEqual(entries[0]["oid"], first_oid)
        self.assertEqual(objects.read_blob(self.pygit_dir, first_oid), b"old version\n")
        self.assertEqual(
            objects.read_blob(self.pygit_dir, entries[0]["oid"]),
            b"new version\n",
        )

    def test_identical_files_share_one_blob_oid(self):
        same_bytes = b"identical contents\n"
        self.write_file("first.txt", same_bytes)
        self.write_file("second.txt", same_bytes)

        self.run_add("first.txt", "second.txt")

        entries = self.staged_entries()
        self.assertEqual([entry["path"] for entry in entries], ["first.txt", "second.txt"])
        self.assertEqual(entries[0]["oid"], entries[1]["oid"])
        self.assertEqual(objects.read_blob(self.pygit_dir, entries[0]["oid"]), same_bytes)

    def test_binary_and_empty_files_are_staged_correctly(self):
        contents = {"binary.bin": b"\x00\xff\x80\n", "empty.txt": b""}
        for path, content in contents.items():
            self.write_file(path, content)

        self.run_add(*contents)

        for entry in self.staged_entries():
            with self.subTest(path=entry["path"]):
                self.assertEqual(
                    objects.read_blob(self.pygit_dir, entry["oid"]),
                    contents[entry["path"]],
                )

    def test_missing_file_raises_pygit_error_and_does_not_modify_index(self):
        before = self.index_path.read_bytes()

        with self.assertRaises(PyGitError):
            self.run_add("does_not_exist.txt")

        self.assertEqual(self.index_path.read_bytes(), before)

    def test_directory_cannot_be_added_yet(self):
        (self.root / "folder").mkdir()
        before = self.index_path.read_bytes()

        with self.assertRaises(PyGitError):
            self.run_add("folder")

        self.assertEqual(self.index_path.read_bytes(), before)

    def test_file_outside_repository_is_rejected(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        external_file = Path(outside.name) / "external.txt"
        external_file.write_bytes(b"outside\n")
        before = self.index_path.read_bytes()

        with self.assertRaises(PyGitError):
            self.run_add(external_file)

        self.assertEqual(self.index_path.read_bytes(), before)

    def test_internal_pygit_file_is_rejected(self):
        before = self.index_path.read_bytes()

        with self.assertRaises(PyGitError):
            self.run_add(".pygit/index.json")

        self.assertEqual(self.index_path.read_bytes(), before)

    def test_invalid_path_in_batch_prevents_partial_index_update(self):
        self.write_file("valid.txt", b"good\n")
        before = self.index_path.read_bytes()

        with self.assertRaises(PyGitError):
            self.run_add("valid.txt", "missing.txt")

        self.assertEqual(self.index_path.read_bytes(), before)
        self.assertEqual(self.staged_entries(), [])

    def test_worker_read_error_propagates_and_index_remains_unchanged(self):
        self.write_file("good.txt", b"good\n")
        bad_path = self.write_file("unreadable.txt", b"bad\n")
        before = self.index_path.read_bytes()
        original_read_bytes = Path.read_bytes

        def simulated_read_error(path: Path) -> bytes:
            if path == bad_path:
                raise OSError("simulated failure inside a worker")
            return original_read_bytes(path)

        with mock.patch.object(Path, "read_bytes", simulated_read_error):
            with self.assertRaises(PyGitError):
                self.run_add("good.txt", "unreadable.txt")

        self.assertEqual(self.index_path.read_bytes(), before)
        self.assertEqual(self.staged_entries(), [])

    def test_add_preserves_previously_staged_files(self):
        self.write_file("already.txt", b"already staged\n")
        self.write_file("new.txt", b"new staged\n")
        self.run_add("already.txt")

        self.run_add("new.txt")

        self.assertEqual(
            [entry["path"] for entry in self.staged_entries()],
            ["already.txt", "new.txt"],
        )

    def test_multi_file_add_saves_index_once(self):
        for name in ("one.txt", "two.txt", "three.txt"):
            self.write_file(name, name.encode("utf-8"))
        original_save_entry = index.save_entry

        with mock.patch.object(index, "save_entry", wraps=original_save_entry) as saved:
            self.run_add("one.txt", "two.txt", "three.txt")

        self.assertEqual(saved.call_count, 1)
        self.assertEqual(len(self.staged_entries()), 3)

    def test_twenty_files_are_all_staged_by_thread_pool(self):
        contents = {
            f"batch/file_{n:02}.txt": f"content {n}\n".encode("ascii")
            for n in range(20)
        }
        for path, content in contents.items():
            self.write_file(path, content)

        self.run_add(*reversed(list(contents)))

        entries = self.staged_entries()
        self.assertEqual(len(entries), 20)
        self.assertEqual(
            [entry["path"] for entry in entries],
            sorted(contents, key=lambda path: path.encode("utf-8")),
        )
        for entry in entries:
            with self.subTest(path=entry["path"]):
                self.assertEqual(
                    entry["oid"],
                    self.expected_blob_oid(contents[entry["path"]]),
                )
                self.assertEqual(
                    objects.read_blob(self.pygit_dir, entry["oid"]),
                    contents[entry["path"]],
                )


if __name__ == "__main__":
    unittest.main()
