from __future__ import annotations

import asyncio
import json
import re
from typing import Any
from urllib.parse import quote, urlparse
from uuid import UUID

import httpx

POWER_AUTOMATE_API_VERSION = "2024-10-01"
POWER_AUTOMATE_API_BASE_URL = "https://api.powerplatform.com"
RETRYABLE_STATUS = {429, 502, 503, 504}

POWER_AUTOMATE_REQUIRED_SIGNALS: dict[str, tuple[str, ...]] = {
    "payload_llm": ("payload_llm",),
    "llm_adapter": ("llm_adapter",),
    "parse_json_llm": ("parse_json_llm",),
    "g8_percentage_gate": ("g8_percentage_gate",),
    "semantic_grounding_gate": ("semantic_grounding_gate",),
    "insight_final": ("insight_final",),
    "audit_contract": ("audit_contract",),
    "html_email_final": ("html_email_final",),
    "send_email_v2": ("send_email_v2", "send_an_email_v2"),
}


class PowerAutomateApiError(RuntimeError):
    """Error sanitizado al consultar Power Automate mediante Power Platform API."""


def parse_make_power_automate_url(url: str) -> tuple[str, str]:
    """Extrae environment y flow ID desde una URL de make.powerautomate.com sin persistirlos."""
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.hostname != "make.powerautomate.com":
        raise ValueError("power_automate_url debe usar https://make.powerautomate.com.")
    parts = [part for part in parsed.path.split("/") if part]
    try:
        env_index = parts.index("environments")
        flow_index = parts.index("flows")
        environment_id = parts[env_index + 1]
        workflow_id = parts[flow_index + 1]
    except (ValueError, IndexError) as exc:
        raise ValueError("URL Power Automate sin environment/flow reconocible.") from exc
    _validate_environment_id(environment_id)
    return environment_id, _validate_uuid(workflow_id, "workflow_id")


def _validate_uuid(value: str, field_name: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise ValueError(f"{field_name} debe ser un GUID válido.") from exc


def _validate_environment_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,160}", value):
        raise ValueError("environment_id contiene caracteres no permitidos.")
    return value


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        value = payload.get("value")
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _normalized_json(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).casefold()
    return re.sub(r"[^a-z0-9]+", "_", text)


def summarize_flow_actions(payload: Any) -> dict[str, Any]:
    """Resume acciones sin devolver parámetros/valores que podrían contener secretos."""
    actions = _items(payload)
    signals: dict[str, bool] = {}
    for signal, aliases in POWER_AUTOMATE_REQUIRED_SIGNALS.items():
        signals[signal] = any(
            any(alias in _normalized_json(action) for alias in aliases)
            for action in actions
        )
    names: list[str] = []
    for action in actions:
        name = next(
            (
                action.get(key)
                for key in ("actionName", "name", "displayName", "operationId")
                if action.get(key)
            ),
            None,
        )
        if name:
            names.append(str(name)[:160])
    return {
        "action_count": len(actions),
        "signal_count": sum(1 for present in signals.values() if present),
        "required_signal_count": len(signals),
        "signals": signals,
        "action_names": names[:100],
        "raw_parameters_returned": False,
    }


def summarize_flow_runs(payload: Any) -> dict[str, Any]:
    """Resume historial real de runs sin devolver inputs/outputs de acciones."""
    runs = _items(payload)
    summaries: list[dict[str, Any]] = []
    for run in runs:
        run_id = next((run.get(key) for key in ("flowRunId", "runId", "id", "name") if run.get(key)), None)
        status = next((run.get(key) for key in ("status", "state", "runStatus") if run.get(key)), None)
        start = next((run.get(key) for key in ("startTime", "startDateTime", "startedOn", "createdOn") if run.get(key)), None)
        end = next((run.get(key) for key in ("endTime", "endDateTime", "finishedOn", "modifiedOn") if run.get(key)), None)
        summaries.append(
            {
                "run_id": str(run_id)[:160] if run_id is not None else None,
                "status": str(status)[:80] if status is not None else None,
                "start_time": str(start)[:80] if start is not None else None,
                "end_time": str(end)[:80] if end is not None else None,
            }
        )
    summaries.sort(key=lambda item: item.get("start_time") or "", reverse=True)
    success_count = sum(
        1
        for item in summaries
        if str(item.get("status") or "").casefold() in {"success", "succeeded", "passed", "pass"}
    )
    failed_count = sum(
        1
        for item in summaries
        if str(item.get("status") or "").casefold() in {"fail", "failed", "failure", "cancelled", "canceled"}
    )
    return {
        "run_count": len(summaries),
        "success_count": success_count,
        "failed_count": failed_count,
        "latest_run": summaries[0] if summaries else None,
        "recent_runs": summaries[:20],
        "action_inputs_outputs_returned": False,
    }


class PowerAutomateApiClient:
    """Cliente read-only para Power Automate en Power Platform API 2024-10-01."""

    def __init__(
        self,
        token: str,
        *,
        base_url: str = POWER_AUTOMATE_API_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not token:
            raise ValueError("Power Automate API requiere token.")
        normalized = base_url.rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Power Automate API base_url debe usar HTTPS.")
        self.token = token
        self.base_url = normalized
        self.client = client

    async def list_cloud_flows(self, environment_id: str, workflow_id: str) -> Any:
        return await self._get(
            f"/powerautomate/environments/{quote(_validate_environment_id(environment_id), safe='-_.')}/cloudFlows",
            {"workflowId": _validate_uuid(workflow_id, "workflow_id")},
        )

    async def list_flow_actions(self, environment_id: str, workflow_id: str) -> Any:
        return await self._get(
            f"/powerautomate/environments/{quote(_validate_environment_id(environment_id), safe='-_.')}/flowActions",
            {"workflowId": _validate_uuid(workflow_id, "workflow_id")},
        )

    async def list_flow_runs(self, environment_id: str, workflow_id: str) -> Any:
        return await self._get(
            f"/powerautomate/environments/{quote(_validate_environment_id(environment_id), safe='-_.')}/flowRuns",
            {"workflowId": _validate_uuid(workflow_id, "workflow_id")},
        )

    async def _get(self, path: str, params: dict[str, str]) -> Any:
        query = {**params, "api-version": POWER_AUTOMATE_API_VERSION}
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        owns_client = self.client is None
        active_client = self.client or httpx.AsyncClient(timeout=30.0)
        try:
            for attempt in range(1, 4):
                try:
                    response = await active_client.get(f"{self.base_url}{path}", params=query, headers=headers)
                except httpx.RequestError as exc:
                    if attempt == 3:
                        raise PowerAutomateApiError("Power Platform API no respondió después de los reintentos.") from exc
                    await asyncio.sleep(0.25 * attempt)
                    continue
                if response.status_code in RETRYABLE_STATUS and attempt < 3:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = max(0.0, float(retry_after)) if retry_after else 0.25 * attempt
                    except ValueError:
                        delay = 0.25 * attempt
                    await asyncio.sleep(min(delay, 5.0))
                    continue
                if response.status_code == 204:
                    return {"value": []}
                if response.status_code < 200 or response.status_code >= 300:
                    raise PowerAutomateApiError(
                        f"Power Platform API devolvió HTTP {response.status_code}; revisa permisos, environment y flow."
                    )
                try:
                    return response.json()
                except ValueError as exc:
                    raise PowerAutomateApiError("Power Platform API devolvió JSON inválido.") from exc
            raise PowerAutomateApiError("Power Platform API agotó reintentos.")
        finally:
            if owns_client:
                await active_client.aclose()
