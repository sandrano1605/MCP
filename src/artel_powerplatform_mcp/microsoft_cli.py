import json
import re
import subprocess
from pathlib import Path
from shutil import which
from typing import Any


_MAX_OUTPUT = 12000


def _sanitize(text: str) -> str:
    value = text or ""
    value = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(access[_-]?token\s*[=:]\s*)[^\s,;]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)([?&]sig=)[^&\s]+", r"\1[REDACTED]", value)
    return value[:_MAX_OUTPUT]


def _parse_output(stdout: str) -> Any:
    stripped = (stdout or "").strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return _sanitize(stripped)


def _run(executable: str, args: list[str], *, timeout: int = 90) -> dict[str, Any]:
    resolved = which(executable)
    if not resolved:
        return {
            "status": "BLOCKED",
            "reason": "EXECUTABLE_NOT_FOUND",
            "executable": executable,
            "exit_code": None,
            "secrets_returned": False,
        }
    try:
        completed = subprocess.run(
            [resolved, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "BLOCKED",
            "reason": "TIMEOUT",
            "executable": executable,
            "exit_code": None,
            "secrets_returned": False,
        }

    stdout = _parse_output(completed.stdout)
    stderr = _sanitize(completed.stderr or "")
    return {
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "executable": executable,
        "exit_code": completed.returncode,
        "stdout": stdout,
        "stderr": stderr or None,
        "secrets_returned": False,
    }


def validate_pbir(path: str) -> dict[str, Any]:
    target = Path(path).expanduser()
    if not target.exists():
        return {
            "status": "FAIL",
            "reason": "PATH_NOT_FOUND",
            "path_exists": False,
            "secrets_returned": False,
        }
    result = _run("powerbi-report-author", ["validate", str(target), "--pretty"], timeout=120)
    result["path_exists"] = True
    result["operation"] = "validate_pbir"
    result["writes"] = 0
    return result


def desktop_status(*, wait_seconds: int = 30) -> dict[str, Any]:
    wait = max(0, min(int(wait_seconds), 120))
    result = _run("powerbi-desktop", ["status", "--wait-seconds", str(wait)], timeout=wait + 20)
    result["operation"] = "desktop_status"
    result["writes"] = 0
    return result


def desktop_manifest(pid: int) -> dict[str, Any]:
    if int(pid) <= 0:
        return {
            "status": "FAIL",
            "reason": "INVALID_PID",
            "operation": "desktop_manifest",
            "writes": 0,
            "secrets_returned": False,
        }
    result = _run("powerbi-desktop", ["manifest", "--pid", str(int(pid))], timeout=60)
    result["operation"] = "desktop_manifest"
    result["writes"] = 0
    return result


def desktop_open(path: str) -> dict[str, Any]:
    target = Path(path).expanduser()
    if not target.exists():
        return {
            "status": "FAIL",
            "reason": "PATH_NOT_FOUND",
            "path_exists": False,
            "operation": "desktop_open",
            "writes": 0,
            "secrets_returned": False,
        }
    if target.suffix.casefold() not in {".pbip", ".pbix"}:
        return {
            "status": "FAIL",
            "reason": "UNSUPPORTED_FILE_TYPE",
            "path_exists": True,
            "operation": "desktop_open",
            "writes": 0,
            "secrets_returned": False,
        }
    result = _run("powerbi-desktop", ["open", str(target)], timeout=60)
    result["path_exists"] = True
    result["operation"] = "desktop_open"
    result["writes"] = 0
    return result
