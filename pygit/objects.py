from pathlib import Path
from . import errors
import hashlib
import zlib
import json

OBJECT_TYPES = ["blob", "tree", "commit"]

def build_envelope(object_type: str, content: bytes) -> bytes:
    """Build the uncompressed representation for an object."""
    if object_type not in OBJECT_TYPES:
        raise errors.PyGitError(2, "E_INVALID_OBJECT_TYPE", f"Invalid object type: {object_type}")
    header = f"{object_type} {len(content)}\0".encode()
    return header + content

def generate_oid(envelope: bytes) -> str:
    """Compute the SHA-256 object identifier."""
    return hashlib.sha256(envelope).hexdigest()

def object_path(pygit_dir: Path, oid: str) -> Path:
    """Determine where an object belongs in the repository."""
    return pygit_dir / "objects" / oid[:2] / oid[2:]

def write_object(pygit_dir: Path, object_type: str, content: bytes) -> str:
    """Store an immutable object in the object database."""
    obj_envelope = build_envelope(object_type, content)
    oid = generate_oid(obj_envelope)
    obj_path = object_path(pygit_dir, oid)
    compressed_obj = zlib.compress(obj_envelope, level=6)
    obj_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(obj_path, "xb") as obj_file:
            obj_file.write(compressed_obj)
    except FileExistsError:
        read_obj_type, read_obj_content = read_object(pygit_dir, oid)
        if read_obj_type != object_type or read_obj_content != content:
            raise errors.PyGitError(5, "E_CORRUPT_OBJECT", f"Object already exists but content/type mismatch: {oid}")
        pass
    except Exception as e:
        raise errors.PyGitError(3, "E_WRITE_OBJECT", f"Failed to write object: {e}")
    return oid

def read_object(pygit_dir: Path, oid: str) -> tuple[str, bytes]:
    """Retrieve and validate an object by its identifier."""
    obj_path = object_path(pygit_dir, oid)
    if not obj_path.exists():
        raise errors.PyGitError(4, "E_OBJECT_NOT_FOUND", f"Object not found: {oid}")
    try:
        with open(obj_path, "rb") as obj_file:
            compressed_obj = obj_file.read()
    except Exception as e:
        raise errors.PyGitError(4, "E_READ_OBJECT", f"Failed to read object: {oid} due to {e}")
    
    try:
        obj = zlib.decompress(compressed_obj)
    except Exception as e:
        raise errors.PyGitError(5, "E_CORRUPT_OBJECT", f"Failed to decompress object: {oid}")
    header, separator, payload = obj.partition(b"\0")
    if separator != b"\x00":
        raise errors.PyGitError(5, "E_CORRUPT_OBJECT",f"Missing NUL separator: {oid}")
    obj_type = header.decode("ascii").split(' ')[0]
    if obj_type not in OBJECT_TYPES:
        raise errors.PyGitError(2, "E_INVALID_OBJECT_TYPE", f"Invalid object type: {obj_type}")   
    payload_size = header.decode("ascii").split(' ')[1]
    if len(payload) != int(payload_size):
        raise errors.PyGitError(5, "E_CORRUPT_PAYLOAD_SIZE_MISMATCH", f"Corrupt object: {oid}, expected size:{payload_size}, found size: {len(header[1])}")
    oid_new = generate_oid(obj)
    if oid_new != oid:
        raise errors.PyGitError(5, "E_CORRUPT_OID_MISMATCH", f"Corrupt object: {oid}, expected oid:{oid}, found oid: {oid_new}")
    return obj_type, payload

def store_blob(pygit_dir: Path, content: bytes) -> str:
    """Store file contents as a blob."""
    return write_object(pygit_dir, "blob", content)

def read_blob(pygit_dir: Path, oid: str) -> bytes:
    """Retrieve original bytes of a stored blob"""
    blob_type, blob_content = read_object(pygit_dir, oid)
    if blob_type != "blob":
        raise errors.PyGitError(2, "E_INVALID_OBJECT_TYPE", f"Expected blob, found {blob_type}")
    return blob_content

def _encode_json(data: dict) -> bytes:
    """Canonical JSON: deterministic keys, compact UTF-8, no trailing newline."""
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def store_tree(pygit_dir: Path, entries: list[dict]) -> str:
    """
    Store one directory.

    Each entry: {"name": "file.txt", "oid": "...", "type": "blob"}
    or: {"name": "src", "oid": "...", "type": "tree"}
    """
    tree = {
        "entries": sorted(
            entries,
            key=lambda entry: entry["name"].encode("utf-8"),
        ),
        "version": 1,
    }
    return write_object(pygit_dir, "tree", _encode_json(tree))


def read_tree(pygit_dir: Path, oid: str) -> dict:
    """Read one directory tree."""
    object_type, content = read_object(pygit_dir, oid)

    if object_type != "tree":
        raise errors.PyGitError(2, "E_INVALID_OBJECT_TYPE", f"Expected tree, found {object_type}")

    try:
        return json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise errors.PyGitError(3, "E_CORRUPT", f"Invalid tree payload: {oid}") from exc


def store_commit(pygit_dir: Path, tree: str, parents: list[str], author: str, message: str, timestamp: int) -> str:
    """Store a commit pointing to a root tree and its parent commits."""
    commit_data = {
        "author": author,
        "message": message,
        "parents": parents,
        "timestamp": timestamp,
        "tree": tree,
        "version": 1,
    }
    return write_object(pygit_dir, "commit", _encode_json(commit_data))


def read_commit(pygit_dir: Path, oid: str) -> dict:
    """Read a commit's metadata."""
    object_type, content = read_object(pygit_dir, oid)

    if object_type != "commit":
        raise errors.PyGitError(2, "E_INVALID_OBJECT_TYPE", f"Expected commit, found {object_type}")

    try:
        return json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise errors.PyGitError(3, "E_CORRUPT", f"Invalid commit payload: {oid}") from exc