import unittest
import tempfile
from pathlib import Path
from pygit.errors import PyGitError

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
        content = b"Same content"

        oid1 = store_blob(self.pygit_dir, content)
        path = object_path(self.pygit_dir, oid1)

        original_bytes = path.read_bytes()

        oid2 = store_blob(self.pygit_dir, content)

        self.assertEqual(oid1, oid2)
        self.assertEqual(path.read_bytes(), original_bytes)
        
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

    def test_corrupted_object(self):
        """Corrupted object should raise an error."""

        content = b"Corrupted content"

        oid = store_blob(self.pygit_dir, content)

        # Corrupt the object by modifying its file
        obj_path = object_path(self.pygit_dir, oid)
        with open(obj_path, "wb") as f:
            f.write(b"corrupted data")

        with self.assertRaises(PyGitError):
            read_blob(self.pygit_dir, oid)

    def test_missing_object(self):
        """Reading a non-existent object should raise an error."""

        missing_oid = "1" * 64  # A fake OID that doesn't exist

        with self.assertRaises(PyGitError):
            read_blob(self.pygit_dir, missing_oid)
    
    def test_corrupted_duplicate(self):
        """Storing content whose existing object has been corrupted should raise an error."""

        content = b"Original content"

        oid = store_blob(self.pygit_dir, content)

        # Corrupt the object by modifying its file
        obj_path = object_path(self.pygit_dir, oid)
        with open(obj_path, "wb") as f:
            f.write(b"corrupted data")

        with self.assertRaises(PyGitError):
            store_blob(self.pygit_dir, content)

if __name__ == "__main__":
    unittest.main()
