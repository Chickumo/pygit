from pathlib import Path
from . import errors

def status(args):
    """Show the status of the repository."""
    dir_path = Path(".").absolute() / ".pygit"

    tmp_dir = dir_path.parent
    while tmp_dir.parent != tmp_dir:
        if (tmp_dir / ".pygit").exists() or (tmp_dir / ".pygit").is_symlink():
            dir_path = tmp_dir / ".pygit"
            break
        tmp_dir = tmp_dir.parent
    if not dir_path.exists() or not dir_path.is_symlink():
        raise errors.PyGitError(1, "E_NOT_REPOSITORY", f"Not pygit repository found!: {dir_path.parent}")

    with open(dir_path / 'HEAD', 'r') as head_file: 
        head = head_file.read().strip().split(': refs/heads/')[1]
    print(f"On branch: \033[32m{head}\033[0m")

    try:
        with open(dir_path / 'refs' / 'heads' / head, 'r') as head_ref_file:
            head_commit = head_ref_file.read().strip()
    except FileNotFoundError:
        print(f"\n\nHEAD commit: \033[31mNo commits yet\033[0m")
    else:
        print(f"HEAD commit: \033[31m{head_commit}\033[0m")