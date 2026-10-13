def init(args):
    """Initialize a new repository in the specified directory."""

    from pathlib import Path
    import shutil
    from . import errors

    dir_path = Path(args.directory).absolute() / ".pygit"

    if not Path(args.directory).is_dir():
        raise errors.PyGitError(1, "E_PATH_NOT_FOUND", f"Invalid Directory: {dir_path.parent}")
    
    tmp_dir = dir_path.parent.parent
    while tmp_dir.parent != tmp_dir:
        if (tmp_dir / ".pygit").exists() or (tmp_dir / ".pygit").is_symlink():
            raise errors.PyGitError(1, "E_NESTED", f"Repository already exists at {tmp_dir}")
        tmp_dir = tmp_dir.parent

    try:
        dir_path.mkdir()
    except FileExistsError:
        raise errors.PyGitError(1, "E_ALREADY_INITIALIZED", f"Repository already exists at {dir_path}")

    except OSError as exc:
        raise errors.PyGitError(4, "E_IO", f"Cannot create repository: {exc}") from exc

    try:
        (dir_path / "refs" / "heads").mkdir(parents=True)
        (dir_path / "tmp").mkdir()
        (dir_path / "objects").mkdir()
        (dir_path / "FORMAT").write_bytes(b"pygit-format 1\n")
        (dir_path / "HEAD").write_bytes(b"ref: refs/heads/pewpew\n")
        (dir_path / "index.json").write_bytes(b'{"conflicts":[],"entries":[],"version":1}\n')
    except OSError as exc:
        try:
            shutil.rmtree(dir_path)
        except OSError as cleanup_exc:
            raise errors.PyGitError(4, "E_IO", f"Initialization failed: {exc} and,\ncleanup failed: {cleanup_exc}") from cleanup_exc

        raise errors.PyGitError(4, "E_IO", f"Initialization failed: {exc}") from exc

    print(f"Initialized PyGit repository at {dir_path.absolute()}")
    print(f"============================================================")
    print(f"FORMAT: pygit-format 1")
    print(f"HEAD: ref: refs/heads/pewpew")
    print('INDEX: {"conflicts":[],"entries":[],"version":1}')