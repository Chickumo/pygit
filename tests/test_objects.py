
import unittest
import tempfile
from pathlib import Path

from pygit.objects import (
    store_blob,
    read_blob,
    object_path,
)


class TestObjects(unittest.TestCase):

    def setUp(self):
        """Create a temporary object database for each test."""

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)

        self.pygit_dir = Path(temp.name) / ".pygit"
        (self.pygit_dir / "objects").mkdir(parents=True)

    def test_store_and_read_blob(self):
        """Stored blob content should be retrieved exactly."""

        content = b"Hello PyGit!"

        oid = store_blob(self.pygit_dir, content)
        restored = read_blob(self.pygit_dir, oid)

        self.assertEqual(restored, content)
        self.assertEqual(len(oid), 64)

    def test_duplicate_blob(self):
        """Identical contents should reuse the same object."""

        content = b"Same content"

        oid1 = store_blob(self.pygit_dir, content)
        oid2 = store_blob(self.pygit_dir, content)

        self.assertEqual(oid1, oid2)
        self.assertTrue(object_path(self.pygit_dir, oid1).is_file())

    def test_empty_blob(self):
        """An empty file should be stored and restored."""

        content = b""

        oid = store_blob(self.pygit_dir, content)
        restored = read_blob(self.pygit_dir, oid)

        self.assertEqual(restored, content)

    def test_binary_blob(self):
        """Binary content must be preserved exactly."""

        content = b"\x00\xff\x10\x80"

        oid = store_blob(self.pygit_dir, content)
        restored = read_blob(self.pygit_dir, oid)

        self.assertEqual(restored, content)

if __name__ == "__main__":
    unittest.main()
