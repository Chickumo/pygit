class PyGitError(Exception):
    """Base class for PyGit errors."""
    def __init__(self, code: int, error:str, message: str):
        super().__init__(message)
        self.code = code
        self.error = error

def raise_InvalidRepositoryFormat():
    raise PyGitError(3, "E_CORRUPT_FORMAT", "Invalid repository FORMAT")

def raise_FileNotFound(file_path: str):
    raise PyGitError(4, "E_FILE_NOT_FOUND", f"File not found: {file_path}")
