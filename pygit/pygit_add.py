from . import index
from . import objects
from . import errors
from concurrent.futures import ThreadPoolExecutor
from pygit.repository import to_repo_relative, find_repo
from pathlib import Path
import threading

def add(args):
    """Add files to the staging area."""
    pygit_dir = find_repo().resolve()
    files = [to_repo_relative(path, pygit_dir) for path in args.paths]
    data = index.load_index(pygit_dir)
    object_lock = threading.Lock()

    def worker(file_paths):
        """Worker function to process a file path."""
        absolute_path, relative_path = file_paths
        try:
            content = absolute_path.read_bytes()
        except OSError as exc:
            raise errors.PyGitError(1, "E_FILE_READ_FAILED", f"Cannot read file: {absolute_path}") from exc
        
        with object_lock:
            oid = objects.store_blob(pygit_dir, content)
        return relative_path, oid

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(worker, files))
    for(relative_path, oid) in results:
        index.stage_entry(data, relative_path, oid)
    index.save_entry(pygit_dir, data)