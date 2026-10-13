from pathlib import Path
import os
from . import errors

def find_repo() -> Path:
    """Find the nearest .pygit directory."""
    tmp_dir = Path.cwd()
    while True:
        candidate = tmp_dir / ".pygit"
        if candidate.is_dir():
            return candidate
        if tmp_dir.parent == tmp_dir:
            break

        tmp_dir = tmp_dir.parent
    raise errors.PyGitError(1, "E_NO_REPOSITORY", "Not inside a PyGit repository")

def to_repo_relative(path: str | Path, pygit_dir: Path) -> tuple[Path, str]:
    """Convert a working-file path into a repository-root-relative path."""
    repo_root = pygit_dir.resolve().parent
    source = Path(path)

    if source.is_symlink():
        raise errors.PyGitError(1, "E_UNSUPPORTED_PATH",f"Symbolic links are not supported: {path}")

    try:
        absolute_path = source.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise errors.PyGitError(1, "E_PATH_NOT_FOUND", f"Cannot access file: {path}") from exc

    if not absolute_path.is_file():
        raise errors.PyGitError(1, "E_PATH_NOT_FILE", f"Path is not a regular file: {path}")

    try:
        relative_path = absolute_path.relative_to(repo_root)
    except ValueError as exc:
        raise errors.PyGitError(1, "E_PATH_OUTSIDE_REPOSITORY", f"File is outside the repository: {path}") from exc

    if relative_path.parts[0] == ".pygit":
        raise errors.PyGitError(1, "E_INTERNAL_PATH", "Cannot stage files inside .pygit")

    return absolute_path, relative_path.as_posix()