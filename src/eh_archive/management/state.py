from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from . import ManagementError

KINDS = {
    "apply_config",
    "restart_supervisor",
    "restart_web",
    "restart_all",
    "git_update",
    "start_web",
    "start_supervisor",
    "start_all",
    "stop_web",
    "stop_supervisor",
    "stop_all",
}
TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}


def now() -> str:
    return datetime.now(UTC).isoformat()


def operation_id(value: str) -> str:
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, AttributeError) as exc:
        raise ManagementError("Invalid operation ID", "invalid_request") from exc
    return value


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            os.chmod(temporary, path.stat().st_mode)
        os.replace(temporary, path)
        if os.name == "posix":
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_json(path: Path, data: dict) -> None:
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2).encode())


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class OperationStore:
    def __init__(self, config):
        self.config = config

    def locate(self, identifier: str) -> Path:
        operation_id(identifier)
        for root in self.config.roots:
            path = root / "history" / identifier
            if (path / "request.json").is_file():
                return path
        raise ManagementError("Operation not found", "not_found")

    def list(self) -> list[dict]:
        states = []
        for root in self.config.roots:
            for path in (root / "history").glob("*/state.json"):
                try:
                    states.append(read_json(path))
                except (OSError, ValueError):
                    continue
        return sorted(states, key=lambda state: state["created_at"], reverse=True)

    def observed(self, state: dict, systemd) -> dict:
        if state["status"] in TERMINAL:
            return state
        age = (datetime.now(UTC) - datetime.fromisoformat(state["heartbeat_at"])).total_seconds()
        if age <= 30:
            return state
        try:
            active = systemd.active(systemd.operation_unit(state["id"]))
        except ManagementError as exc:
            if exc.code != "not_installed":
                return {**state, "executor_status": "unknown"}
            active = False
        if active:
            return {**state, "executor_status": "heartbeat_stale"}
        # Observation is read-only. A lock holder persists recovery decisions.
        return {
            **state,
            "status": "interrupted",
            "executor_status": "lost",
            "error_code": "executor_lost",
            "error": "Executor exited before completion",
        }

    def create(
        self,
        kind: str,
        actor: str,
        *,
        identifier: str | None = None,
        parameters: dict | None = None,
    ) -> Path:
        if kind not in KINDS:
            raise ManagementError("Unknown operation kind", "invalid_request")
        if parameters and kind != "apply_config":
            raise ManagementError("Operation accepts no parameters", "invalid_request")
        identifier = operation_id(identifier or str(uuid.uuid4()))
        path = self.config.management_dir / "history" / identifier
        path.mkdir(parents=True, mode=0o700)
        request = {
            "id": identifier,
            "kind": kind,
            "actor": actor,
            "parameters": parameters or {},
            "created_at": now(),
        }
        write_json(path / "request.json", request)
        write_json(
            path / "state.json",
            {
                **request,
                "status": "pending",
                "phase": "pending",
                "heartbeat_at": now(),
                "started_at": None,
                "finished_at": None,
                "error_code": None,
                "error": None,
            },
        )
        return path


def update_state(path: Path, **changes) -> dict:
    state = read_json(path / "state.json")
    state.update(changes, heartbeat_at=now())
    write_json(path / "state.json", state)
    return state


def event(path: Path, phase: str, **detail) -> None:
    with (path / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": now(), "phase": phase, **detail}, ensure_ascii=False) + "\n")
        handle.flush()


def tail(path: Path, limit: int = 32768) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as handle:
        handle.seek(max(0, path.stat().st_size - limit))
        return handle.read(limit).decode("utf-8", errors="replace")
