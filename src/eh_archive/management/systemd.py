from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path

from . import ManagementError
from .config import SUPERVISOR_UNIT, WEB_UNIT
from .state import operation_id


class CommandRunner:
    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path
        self._lock = threading.Lock()

    def log(self, value: str) -> None:
        with self._lock:
            if self.log_path:
                with self.log_path.open("a", encoding="utf-8") as handle:
                    handle.write(value + "\n")
                    handle.flush()
                print(value, flush=True)

    def run(self, argv, *, cwd=None, timeout=120, check=True) -> str:
        argv = [str(value) for value in argv]
        self.log("$ " + subprocess.list2cmdline(argv))
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "PIP_NO_INPUT": "1"}
        try:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                start_new_session=os.name == "posix",
            )
        except OSError as exc:
            self.log(str(exc))
            raise ManagementError(
                f"Command could not complete: {argv[0]}: {exc}", "command_failed"
            ) from exc
        output = deque(maxlen=10000)

        def consume():
            with process.stdout:
                for line in process.stdout:
                    output.append(line)
                    self.log(line.rstrip())

        reader = threading.Thread(target=consume, daemon=True)
        reader.start()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait()
            raise ManagementError(f"Command timed out: {argv[0]}", "command_timeout") from exc
        finally:
            reader.join()
        text = "".join(output).strip()
        self.log(f"exit_code={process.returncode}")
        if check and process.returncode:
            raise ManagementError(
                f"{argv[0]} exited with {process.returncode}: {text[-2000:]}", "command_failed"
            )
        return text


class Systemd:
    def __init__(self, runner: CommandRunner | None = None):
        self.runner = runner or CommandRunner()

    @staticmethod
    def operation_unit(identifier: str) -> str:
        return f"eharchive-operation@{operation_id(identifier)}.service"

    def _validate(self, unit: str) -> None:
        if unit in (WEB_UNIT, SUPERVISOR_UNIT):
            return
        prefix = "eharchive-operation@"
        if unit.startswith(prefix) and unit.endswith(".service"):
            operation_id(unit[len(prefix) : -len(".service")])
            return
        raise ManagementError("Unsupported systemd unit", "invalid_request")

    def status(self, unit: str) -> dict:
        self._validate(unit)
        output = self.runner.run(
            [
                "systemctl",
                "show",
                unit,
                "--no-pager",
                "--property=LoadState,ActiveState,SubState,MainPID,ExecMainStartTimestamp,Result",
            ]
        )
        result = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
        if result.get("LoadState") == "not-found":
            raise ManagementError(f"Unit not installed: {unit}", "not_installed")
        return result

    def active(self, unit: str) -> bool:
        try:
            status = self.status(unit)
        except ManagementError as exc:
            if exc.code == "not_installed" and unit.startswith("eharchive-operation@"):
                return False
            raise
        return status.get("ActiveState") in {
            "active",
            "activating",
            "reloading",
            "deactivating",
        }

    def command(self, action: str, unit: str, *, wait=True) -> None:
        self._validate(unit)
        if action not in {"start", "stop", "reset-failed"}:
            raise ManagementError("Unsupported systemd action", "invalid_request")
        self.runner.run(["systemctl", action, *([] if wait else ["--no-block"]), unit])


def require_linux_root() -> None:
    if sys.platform != "linux" or os.geteuid() != 0:
        raise ManagementError("This command requires Linux and root", "unsupported_platform")
