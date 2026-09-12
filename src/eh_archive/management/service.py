from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from . import ManagementError
from .config import DEFAULT_CONFIG, load_management_config
from .lock import deployment_lock
from .state import TERMINAL, OperationStore, now, read_json, update_state, write_json
from .systemd import Systemd


@contextmanager
def control_guard(component: str, management_path: Path = DEFAULT_CONFIG):
    if component != "supervisor" or not management_path.exists():
        yield
        return
    with deployment_lock():
        ensure_idle(OperationStore(load_management_config(management_path)), Systemd())
        yield


def ensure_idle(store: OperationStore, systemd: Systemd) -> None:
    for state in store.list():
        if state["status"] in TERMINAL:
            continue
        age = (datetime.now(UTC) - datetime.fromisoformat(state["heartbeat_at"])).total_seconds()
        if age < 30 or systemd.active(systemd.operation_unit(state["id"])):
            raise ManagementError("Another operation is pending or running", "operation_conflict")
        path = store.locate(state["id"])
        if state["kind"] == "apply_config" and (path / "configuration.json").exists():
            from .configuration import restore

            restore(store.config, path)
        update_state(
            path,
            status="interrupted",
            finished_at=now(),
            error_code="executor_lost",
            error="Executor exited before completion",
        )


def submit(kind: str, actor: str, *, management_path: Path = DEFAULT_CONFIG, prepare=None) -> dict:
    systemd = Systemd()
    with deployment_lock():
        config = load_management_config(management_path)
        store = OperationStore(config)
        ensure_idle(store, systemd)
        path = store.create(kind, actor)
        try:
            metadata = prepare(config, path) if prepare else None
            systemd.command("start", systemd.operation_unit(path.name), wait=False)
        except Exception as exc:
            update_state(
                path,
                status="failed",
                error_code=getattr(exc, "code", "submit_failed"),
                error=str(exc),
                finished_at=now(),
            )
            raise
        result = read_json(path / "state.json")
        if metadata is not None:
            result["configuration"] = metadata
        return result


def cancel(identifier: str, *, management_path: Path = DEFAULT_CONFIG) -> dict:
    store = OperationStore(load_management_config(management_path))
    path = store.locate(identifier)
    state = read_json(path / "state.json")
    if state["status"] != "running" or state["phase"] != "wait_for_supervisor_exit":
        raise ManagementError("Cancellation is only available while draining", "operation_conflict")
    write_json(path / "cancel.json", {"requested_at": now()})
    return {"id": identifier, "cancel_requested": True}
