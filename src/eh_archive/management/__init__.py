"""File-backed deployment management for the systemd installation."""


class ManagementError(RuntimeError):
    def __init__(self, message: str, code: str = "management_error"):
        super().__init__(message)
        self.code = code
