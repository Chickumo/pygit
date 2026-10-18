from pathlib import Path
from . import index
from . import errors
from pygit.repository import find_repo

def status(args):
    """Show the status of the repository."""
    pygit_dir = find_repo()
    tmp_dir = pygit_dir.parent
    while tmp_dir.parent != tmp_dir:
        if (tmp_dir / ".pygit").exists() or (tmp_dir / ".pygit").is_symlink():
            pygit_dir = tmp_dir / ".pygit"
            break
        tmp_dir = tmp_dir.parent
    if not pygit_dir.exists():
        raise errors.PyGitError(1, "E_NOT_REPOSITORY", f"Not pygit repository found!: {pygit_dir.parent}")

    try:
        with open(pygit_dir / 'HEAD', 'r') as head_file: 
            head = head_file.read().strip().split(': refs/heads/')[1]
    except Exception as e:
        raise errors.PyGitError(1, "E_INVALID_HEAD", f"Invalid HEAD file: {e}")
    print(f"On branch: \033[32m{head}\033[0m")

    try:
        with open(pygit_dir / 'refs' / 'heads' / head, 'r') as head_ref_file:
            head_commit = head_ref_file.read().strip()
    except FileNotFoundError:
        print(f"\n\nHEAD commit: \033[31mNo commits yet\033[0m")
    else:
        print(f"HEAD commit: \033[31m{head_commit}\033[0m")

    print(f"\nStaged files:")
    data = index.load_index(pygit_dir)
    for entry in data["entries"]:
        print(f"  {entry}")

    head