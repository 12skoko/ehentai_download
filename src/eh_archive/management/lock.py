from contextlib import contextmanager

from . import ManagementError
from .config import LOCK_PATH


@contextmanager
def deployment_lock(*, blocking: bool = False):
    try:
        import fcntl
    except ImportError as exc:
        raise ManagementError(
            "Deployment management requires Linux", "unsupported_platform"
        ) from exc
    LOCK_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with LOCK_PATH.open("a+b") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError as exc:
            raise ManagementError(
                "Another deployment operation is running", "operation_conflict"
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
