from __future__ import annotations

from . import ManagementError
from .systemd import CommandRunner


class GitRepository:
    def __init__(self, config, runner: CommandRunner | None = None):
        self.config = config
        self.runner = runner or CommandRunner()

    def run(self, *args, **kwargs) -> str:
        return self.runner.run(["git", *args], cwd=self.config.repository, **kwargs)

    def inspect(self, *, fetch=False, require_clean=False) -> dict:
        from pathlib import Path

        if (
            Path(self.run("rev-parse", "--show-toplevel")).resolve()
            != self.config.repository.resolve()
        ):
            raise ManagementError("Repository root differs from installation", "invalid_repository")
        branch = self.run("symbolic-ref", "--short", "HEAD")
        if branch != self.config.branch:
            raise ManagementError("Current branch differs from installation", "invalid_branch")
        self.run("remote", "get-url", self.config.remote)
        dirty = bool(self.run("status", "--porcelain"))
        if require_clean and dirty:
            raise ManagementError("Git worktree is not clean", "dirty_worktree")
        if fetch:
            self.run("fetch", "--prune", self.config.remote, timeout=300)
        old = self.run("rev-parse", "--verify", "HEAD^{commit}")
        reference = f"refs/remotes/{self.config.remote}/{self.config.branch}"
        try:
            target = self.run("rev-parse", "--verify", f"{reference}^{{commit}}")
        except ManagementError:
            if fetch:
                raise
            return {
                "branch": branch,
                "remote": self.config.remote,
                "old_commit": old,
                "target_commit": None,
                "dirty": dirty,
                "available": False,
            }
        base = self.run("merge-base", old, target)
        fast_forward = base == old
        if require_clean and not fast_forward:
            raise ManagementError("Update cannot fast-forward", "not_fast_forward")
        return {
            "branch": branch,
            "remote": self.config.remote,
            "old_commit": old,
            "target_commit": target,
            "dirty": dirty,
            "fast_forward": fast_forward,
            "available": old != target,
            "commits": self.run("log", "--oneline", "--max-count=30", f"{old}..{target}"),
            "files": self.run("diff", "--stat", old, target),
        }

    def checkout(self, target: str) -> None:
        self.run("merge", "--ff-only", target)

    def restore(self, old: str) -> None:
        # --keep refuses to overwrite intervening local edits.
        self.run("reset", "--keep", old)
