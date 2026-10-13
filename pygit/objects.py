from pathlib import Path
from . import errors
import hashlib
import zlib

OBJECT_TYPES = ["blob", "tree", "commit"]

def build_payload(object_type: str, content: bytes) -> bytes:
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
    obj_envelope = build_payload(object_type, content)
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
        raise errors.PyGitError(4, "E_READ_OBJECT", f"Failed to read object: {oid}")
    
    obj = zlib.decompress(compressed_obj)
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