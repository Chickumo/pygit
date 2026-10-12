import argparse
from pathlib import Path

def main():

    version = "1.0.0"
    parser = argparse.ArgumentParser(prog="pygit", 
        color = True, 
        formatter_class=argparse.RawDescriptionHelpFormatter, 
        usage="pygit <command> [options]", 
        description='''
        --------------------------------
        My own VCS tool TwT!''')
    parser.add_argument("-v", "--version", help="Show the version of pygit", action="version", version="%(prog)s " + version)
    subparsers = parser.add_subparsers(dest="command", required=True)

    #PARSER FOR STATUS COMMAND
    status_parser = subparsers.add_parser("status", help="Show the status of the repository")
    status_parser.set_defaults(func=status)

    #PARSER FOR ADD COMMAND
    add_parser = subparsers.add_parser("add", help="Add files to the staging area")
    add_parser.add_argument("paths", nargs="+")
    add_parser.set_defaults(func=add)

    #PARSER FOR UNSTAGE COMMAND
    unstage_parser = subparsers.add_parser("unstage", help="Unstage files from the staging area")
    unstage_parser.add_argument("paths", nargs="+")
    unstage_parser.set_defaults(func=unstage)

    #PARSER FOR RM COMMAND
    rm_parser = subparsers.add_parser("rm", help="Remove files from the repository")
    rm_parser.add_argument("paths", nargs="+")
    rm_parser.add_argument("--cached", action="store_true", help="Remove files from the index only")
    rm_parser.add_argument("--force", action="store_true", help="Force removal of files")
    rm_parser.set_defaults(func=rm)

    #PARSER FOR INIT COMMAND
    init_parser = subparsers.add_parser("init", help="Initialize a new repository in the specified directory [Default: pwd]")
    init_parser.add_argument("directory", nargs="?", type=Path, default=Path("."))
    init_parser.set_defaults(func=init)

    args = parser.parse_args()
    args.func(args)

def init(args):
    """Initialize a new repository in the specified directory."""
    dir_path = args.directory/".pygit"
    if dir_path.exists():
        print(f"Repository already exists at {dir_path.resolve()}")
        return
    dir_path.mkdir(parents=True, exist_ok=True)
    print(f"Initialized PyGit repository at {dir_path.resolve()}")

def status(args):
    """Show the status of the repository."""
    pass

def add(args):
    """Add files to the staging area."""
    for path in args.paths:
        print(f"Staging: {path}")
    pass

def unstage(args):
    """Unstage files from the staging area."""
    for path in args.paths:
        print(f"Unstaging: {path}")
    pass

def rm(args):
    """Remove files from the repository."""
    print(f"Removing files: {args.paths}")
    print(f"Cached: {args.cached}")
    print(f"Force: {args.force}")

    pass

if __name__ == "__main__":
    main()