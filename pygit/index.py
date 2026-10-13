from pathlib import Path
import json
from . import errors

INDEX_FILENAME = "index.json"

def load_index(pygit_dir: Path) -> dict:
    """Read and parse repository's staging index."""
    index_path = pygit_dir / INDEX_FILENAME
    if not index_path.exists():
        raise errors.PyGitError(1, "E_INDEX_NOT_FOUND", f"Index file not found: {index_path}")

    try:
        with open(index_path, "r") as f:
            index_data = json.load(f)
        if not isinstance(index_data, dict):
            raise errors.PyGitError(2, "E_INDEX_WRONG_FORMAT", f"Index file is corrupted: {index_path}")
        elif "version" not in index_data or "entries" not in index_data or "conflicts" not in index_data:
            raise errors.PyGitError(2, "E_INDEX_WRONG_FORMAT", f"Index file is corrupted: {index_path}")
        elif "version" in index_data and index_data["version"] != 1:
            raise errors.PyGitError(2, "E_UNSUPPORTED_INDEX_VERSION", f"Unsupported index version: {index_data.get('version')}")
        elif "entries" in index_data and not isinstance(index_data["entries"], list):
            raise errors.PyGitError(2, "E_INDEX_WRONG_FORMAT", f"Index file is corrupted: {index_path}")
        elif "conflicts" in index_data and not isinstance(index_data["conflicts"], list):
            raise errors.PyGitError(2, "E_INDEX_WRONG_FORMAT", f"Index file is corrupted: {index_path}")
    except json.JSONDecodeError as exc:
        raise errors.PyGitError(2, "E_INDEX_WRONG_FORMAT", f"Index file is corrupted: {index_path}") from exc

    return index_data

def stage_entry(index: dict, path: str, oid: str) -> None:
    """Add or update an entry in the staging index."""
    
    if path in [entry["path"] for entry in index["entries"]]:
        for entry in index["entries"]:
            if entry["path"] == path:
                entry["oid"] = oid
                break
    else:
        index["entries"].append({"path": path, "oid": oid})
    index["entries"].sort(key=lambda e: e["path"].encode("utf-8"))
    
    paths = [entry["path"] for entry in index["entries"]]
    if len(paths) != len(set(paths)):
        raise errors.PyGitError(2, "E_INDEX_DUPLICATE_ENTRY", f"Duplicate entry found in index: {path}")

def remove_entry(index: dict, path: str) -> None:
    """Remove a staged file mapping from index"""
    initial_count = len(index["entries"])
    index["entries"] = [entry for entry in index["entries"] if entry["path"] != path]
    if len(index["entries"]) == initial_count:
        raise errors.PyGitError(2, "E_INDEX_ENTRY_NOT_FOUND", f"Entry not found in index: {path}")

def save_entry(pygit_dir: Path, index: dict) -> None:
    """Persist the staging index to index.json"""
    if index.get("version") != 1:
        raise errors.PyGitError(2, "E_UNSUPPORTED_INDEX_VERSION", f"Unsupported index version: {index.get('version')}")
    index_path = pygit_dir / INDEX_FILENAME
    try:
        with open(index_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(index, f, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            f.write("\n")
    except OSError as exc:
        raise errors.PyGitError(3, "E_INDEX_WRITE_FAILED", f"Failed to write index file: {index_path}") from exc