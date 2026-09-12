"""Read-only management UI preview using an isolated SQLite demo database."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from dev_web_demo import Database, _db_path, _demo_config_dir, _seed

from eh_archive.management.config import (
    SUPERVISOR_UNIT,
    WEB_UNIT,
    ManagementConfig,
    write_management_config,
)
from eh_archive.management.state import OperationStore, event, update_state
from eh_archive.web import management
from eh_archive.web.app import create_app


class PreviewSystemd:
    def status(self, unit):
        return {
            "LoadState": "loaded",
            "ActiveState": "active" if unit == WEB_UNIT else "inactive",
            "SubState": "running" if unit == WEB_UNIT else "dead",
            "MainPID": "1234",
            "ExecMainStartTimestamp": "preview",
        }


class PreviewGit:
    def __init__(self, config):
        pass

    def inspect(self, **kwargs):
        return {
            "branch": "preview",
            "remote": "origin",
            "old_commit": "a" * 40,
            "target_commit": "a" * 40,
            "available": False,
            "dirty": False,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args()
    database = Database(f"sqlite:///{_db_path.as_posix()}")
    _seed(database)
    directory = Path(tempfile.mkdtemp(prefix="eharchive-management-preview-"))
    config = ManagementConfig(
        repository=Path(__file__).resolve().parents[1],
        config_dir=_demo_config_dir(),
        python=Path(sys.executable),
        management_dir=directory / "history-root",
    )
    management_path = directory / "management.toml"
    write_management_config(config, management_path)
    store = OperationStore(config)
    path = store.create("git_update", "preview")
    update_state(
        path,
        status="succeeded",
        phase="completed",
        old_commit="a" * 40,
        target_commit="b" * 40,
        previous_services={
            WEB_UNIT: True,
            SUPERVISOR_UNIT: False,
            "control": "paused",
        },
    )
    event(path, "verify_repository", status="completed")
    event(path, "health:supervisor", status="not_applicable")
    (path / "operation.log").write_text("Read-only UI preview. No services were changed.\n")
    management.Systemd = PreviewSystemd
    management.GitRepository = PreviewGit
    app = create_app(database, config_dir=config.config_dir, management_config=management_path)
    from fastapi.responses import JSONResponse

    @app.middleware("http")
    async def readonly(request, call_next):
        if request.method not in {"GET", "HEAD"}:
            return JSONResponse({"detail": "Read-only UI preview"}, status_code=403)
        return await call_next(request)

    import uvicorn

    print(f"Read-only preview: http://127.0.0.1:{args.port}/system", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
