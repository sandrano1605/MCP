from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

DEFAULT_REQUIRED_STEPS = (
    "Payload_LLM",
    "LLM_Adapter",
    "Parse_JSON_LLM",
    "Semantic_Grounding_Gate",
    "InsightFinal",
    "HTML_Email_Final",
    "Send_Email",
)

_SECRET_KEY_RE = re.compile(r"(?i)(password|passwd|pwd|client[_-]?secret|access[_-]?token|refresh[_-]?token|api[_-]?key|authorization)")


class FlowAuditError(RuntimeError):
    """El export de Power Automate no pudo auditarse de forma segura."""


def load_flow_export(path: Path, *, max_bytes: int = 10_000_000) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"No existe el export de flujo: {path}")
    if path.stat().st_size > max_bytes:
        raise FlowAuditError("El export de Power Automate excede el límite seguro de 10 MB.")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise FlowAuditError("El export de Power Automate no es JSON UTF-8 válido.") from exc
    if not isinstance(data, dict):
        raise FlowAuditError("Se esperaba un objeto JSON en el export de Power Automate.")
    return data


def audit_flow_definition(
    document: dict[str, Any],
    *,
    required_steps: Iterable[str] = DEFAULT_REQUIRED_STEPS,
) -> dict[str, Any]:
    actions = _collect_actions(document)
    action_by_norm = {_norm(action["name"]): action for action in actions}
    required = [str(item) for item in required_steps]
    required_status: list[dict[str, Any]] = []
    missing: list[str] = []

    for expected in required:
        expected_norm = _norm(expected)
        match = action_by_norm.get(expected_norm)
        if match is None:
            match = next(
                (item for key, item in action_by_norm.items() if expected_norm in key or key in expected_norm),
                None,
            )
        present = match is not None
        required_status.append(
            {
                "step": expected,
                "present": present,
                "matched_action": match["name"] if match else None,
                "type": match.get("type") if match else None,
                "has_run_after": bool(match.get("run_after")) if match else False,
            }
        )
        if not present:
            missing.append(expected)

    secret_indicators = _find_secret_indicators(document)
    send_actions = [item for item in actions if "send" in _norm(item["name"]) and "email" in _norm(item["name"])]
    send_after_gate = any(bool(item.get("run_after")) for item in send_actions)
    condition_count = sum(1 for item in actions if str(item.get("type") or "").casefold() in {"if", "condition", "switch"})
    scope_count = sum(1 for item in actions if str(item.get("type") or "").casefold() in {"scope", "foreach", "until"})

    findings: list[dict[str, Any]] = []
    for step in missing:
        findings.append({"kind": "MISSING_REQUIRED_STEP", "severity": "HIGH", "step": step})
    for indicator in secret_indicators:
        findings.append({"kind": "EMBEDDED_SECRET_INDICATOR", "severity": "HIGH", **indicator})
    if send_actions and not send_after_gate:
        findings.append(
            {
                "kind": "SEND_EMAIL_WITHOUT_RUN_AFTER",
                "severity": "MEDIUM",
                "actions": [item["name"] for item in send_actions],
            }
        )

    return {
        "analysis_mode": "STATIC_POWER_AUTOMATE_EXPORT",
        "action_count": len(actions),
        "condition_count": condition_count,
        "scope_count": scope_count,
        "required_step_count": len(required),
        "required_steps_present": len(required) - len(missing),
        "missing_required_steps": missing,
        "required_steps": required_status,
        "send_email_action_count": len(send_actions),
        "send_email_has_run_after": send_after_gate,
        "secret_indicator_count": len(secret_indicators),
        "secret_indicators": secret_indicators,
        "runtime_validated": False,
        "findings": findings,
        "status": "REVIEW" if findings else "PASS",
    }


def _collect_actions(document: dict[str, Any]) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            actions = node.get("actions")
            if isinstance(actions, dict):
                for name, action in actions.items():
                    if not isinstance(action, dict):
                        continue
                    collected.append(
                        {
                            "name": str(name),
                            "path": f"{path}.actions.{name}" if path else f"actions.{name}",
                            "type": action.get("type"),
                            "run_after": sorted(str(key) for key in (action.get("runAfter") or {}).keys())
                            if isinstance(action.get("runAfter"), dict)
                            else [],
                        }
                    )
                    walk(action, f"{path}.actions.{name}" if path else f"actions.{name}")
            for key, value in node.items():
                if key == "actions":
                    continue
                walk(value, f"{path}.{key}" if path else str(key))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(document, "")

    unique: dict[str, dict[str, Any]] = {}
    for item in collected:
        unique[item["path"]] = item
    return list(unique.values())


def _find_secret_indicators(document: Any) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                child_path = f"{path}.{key}" if path else str(key)
                if _SECRET_KEY_RE.search(str(key)) and isinstance(value, str) and value.strip():
                    findings.append({"path": child_path, "secret_type": _secret_type(str(key))})
                walk(value, child_path)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(document, "")
    return findings[:200]


def _secret_type(key: str) -> str:
    normalized = key.casefold()
    if "authorization" in normalized:
        return "authorization"
    if "secret" in normalized:
        return "client_secret"
    if "token" in normalized:
        return "token"
    if "api" in normalized and "key" in normalized:
        return "api_key"
    return "credential"


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())
