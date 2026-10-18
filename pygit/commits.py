from pathlib import Path
import json
import os
import re
import tempfile
import time

from . import errors, index, objects
from .repository import find_repo

def build_tree(pygit_dir: Path, entries: list[dict]) -> str:
    """Convert flat index paths into hierarchical directory trees."""
    root = {}

    for entry in entries:
        path = entry["path"]
        parts = path.split("/")

        if any(part in ("", ".", "..") for part in parts):
            raise errors.PyGitError(3, "E_CORRUPT", f"Invalid indexed path: {path}")

        # Validate the staged object. Do not read the working file.
        objects.read_blob(pygit_dir, entry["oid"])

        directory = root

        for part in parts[:-1]:
            directory = directory.setdefault(part, {})

            if not isinstance(directory, dict):
                raise errors.PyGitError(3, "E_CORRUPT", f"File/directory conflict in index: {path}")

        filename = parts[-1]

        if filename in directory:
            raise errors.PyGitError(3, "E_CORRUPT", f"Duplicate or conflicting indexed path: {path}")

        directory[filename] = entry["oid"]

    def store_directory(directory: dict) -> str:
        tree_entries = []

        for name, value in directory.items():
            if isinstance(value, dict):
                oid = store_directory(value)
                object_type = "tree"
            else:
                oid = value
                object_type = "blob"

            tree_entries.append({
                "name": name,
                "oid": oid,
                "type": object_type,
            })

        return objects.store_tree(pygit_dir, tree_entries)

    return store_directory(root)


def read_head(pygit_dir: Path) -> tuple[Path, str | None]:
    """Return the reference to update and its current commit ID."""
    head_path = pygit_dir / "HEAD"
    head = head_path.read_bytes()

    attached = re.fullmatch(
        rb"ref: refs/heads/([A-Za-z][A-Za-z0-9_-]{0,31})\n",
        head,
    )

    if attached:
        branch = attached.group(1).decode("ascii")
        target = pygit_dir / "refs" / "heads" / branch

        try:
            contents = target.read_bytes()
        except FileNotFoundError:
            # Your initializer uses pewpew; the specification uses main.
            if branch not in ("pewpew", "main"):
                raise errors.PyGitError(3, "E_CORRUPT", f"Missing branch reference: {branch}")
            return target, None
    else:
        target = head_path
        contents = head

    if re.fullmatch(rb"[0-9a-f]{64}\n", contents) is None:
        raise errors.PyGitError(3, "E_CORRUPT", "Invalid HEAD or branch reference")

    return target, contents[:-1].decode("ascii")


def publish_ref(pygit_dir: Path, target: Path, oid: str) -> None:
    """Replace the reference only after the new objects are stored."""
    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=pygit_dir / "tmp", delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write((oid + "\n").encode("ascii"))
            temporary.flush()
            os.fsync(temporary.fileno())

        os.replace(temporary_path, target)

    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def commit(args):
    """Commit staged bytes and advance the current branch or detached HEAD."""
    try:
        author = args.author
        message = args.message

        if (
            not author.strip()
            or len(author.encode("utf-8")) > 256
            or any(ord(char) < 32 or ord(char) == 127 for char in author)
        ):
            raise ValueError(
                "Author must be nonblank, at most 256 UTF-8 bytes, "
                "and contain no control characters"
            )

        if (
            not message.strip()
            or len(message.encode("utf-8")) > 4096
            or "\0" in message
        ):
            raise ValueError(
                "Message must be nonblank, at most 4096 UTF-8 bytes, "
                "and contain no NUL"
            )

        if args.timestamp is None:
            timestamp = int(time.time())
        else:
            if re.fullmatch(r"0|[1-9][0-9]{0,11}", args.timestamp) is None:
                raise ValueError(
                    "Timestamp must be unsigned decimal seconds "
                    "without leading zeros"
                )
            timestamp = int(args.timestamp)

        if not 0 <= timestamp <= 253402300799:
            raise ValueError("Timestamp is outside the supported range")

    except ValueError as exc:
        raise errors.PyGitError(1, "E_ARGUMENT", str(exc)) from exc

    pygit_dir = find_repo()
    lock_path = pygit_dir / "LOCK"
    owns_lock = False

    try:
        try:
            lock = lock_path.open("xb")
        except FileExistsError as exc:
            raise errors.PyGitError(
                5, "E_LOCKED", "Repository is locked",
            ) from exc

        owns_lock = True

        with lock:
            lock.write(b"pygit-lock-v1\n")

        if (pygit_dir / "MERGE.json").exists():
            raise errors.PyGitError(
                1, "E_STATE", "Cannot commit while a merge is pending",
            )

        staged = index.load_index(pygit_dir)

        if staged["conflicts"]:
            raise errors.PyGitError(
                1, "E_STATE", "Cannot commit unresolved conflicts",
            )

        target, parent_oid = read_head(pygit_dir)

        previous_tree = None

        if parent_oid is not None:
            previous_commit = objects.read_commit(pygit_dir, parent_oid)
            previous_tree = previous_commit["tree"]
            objects.read_tree(pygit_dir, previous_tree)

        tree_oid = build_tree(pygit_dir, staged["entries"])

        if parent_oid is None:
            unchanged = not staged["entries"]
        else:
            unchanged = tree_oid == previous_tree

        if unchanged and not args.allow_empty:
            raise errors.PyGitError(
                1, "E_EMPTY", "Nothing staged to commit",
            )

        commit_oid = objects.store_commit(
            pygit_dir=pygit_dir,
            tree=tree_oid,
            parents=[] if parent_oid is None else [parent_oid],
            author=author,
            message=message,
            timestamp=timestamp,
        )

        publish_ref(pygit_dir, target, commit_oid)

    except OSError as exc:
        raise errors.PyGitError(
            4, "E_IO", f"Cannot create commit: {exc}",
        ) from exc

    finally:
        if owns_lock:
            lock_path.unlink()

    print(json.dumps({"commit": commit_oid}, separators=(",", ":")))