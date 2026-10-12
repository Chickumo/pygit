def init(args):
    """Initialize a new repository in the specified directory."""
    dir_path = args.directory/".pygit"
    if dir_path.exists():
        print(f"Repository already exists at {dir_path.resolve()}")
        return
    dir_path.mkdir(parents=True, exist_ok=True)
    print(f"Initialized PyGit repository at {dir_path.resolve()}")