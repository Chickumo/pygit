class PyGitError(Exception):
    """Base class for PyGit errors."""
    def __init__(self, code: int, error:str, message: str):
        super().__init__(message)
        self.code = code
        self.error = error
