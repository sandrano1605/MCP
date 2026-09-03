from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .clients import FabricClient, PowerBIClient
from .config import load_settings
from .power_automate_api import (
    PowerAutomateApiClient,
    parse_make_power_automate_url,
    summarize_flow_actions,
    summarize_flow_runs,
)
from .tmdl import inspect_tmdl_parts, load_local_tmdl_parts

_RUNTIME_REQUIRED_SIGNALS = (
    "payload_llm",
    "llm_adapter",
    "parse_json_llm",
    "g8_percentage_gate",
    "semantic_grounding_gate",
    "insight_final",
    "audit_contract",
    "html_email_final",
    "send_email_v2",
)

_SELLER_STRONG_TERMS = (
    "vendedor",
    "seller",
    "salesperson",
    "sales_rep",
    "salesrep",
    "sales representative",
    "representante_ventas",
    "ejecutivo_ventas",
)
_SELLER_WEAK_TERMS = ("pernr", "vkgrp", "sales_group", "grupo_vendedores")
_SELLER_EXCLUDE_TERMS = ("solicitante", "cliente", "customer", "kunnr", "shipto", "soldto")


def _status(value: str, **extra: Any) -> dict[str, Any]:
    return {"status": value, **extra}


def _extract_rows(response: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(response, dict):
        return rows
    for result in response.get("results") or []:
        if not isinstance(result, dict):
            continue
        for table in result.get("tables") or []:
            if not isinstance(table, dict):
                continue
            for row in table.get("rows") or []:
                if isinstance(row, dict):
                    rows.append(row)
    return rows


def _row_value(row: dict[str, Any], name: str) -> Any:
    target = name.casefold()
    for key, value in row.items():
        normalized = str(key).strip("[]").casefold()
        if normalized == target or normalized.endswith("." + target):
            return value
    return None


def _dax_string(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _parse_column_ref(value: str) -> tuple[str, str]:
    match = re.fullmatch(r"\s*'?([^'\[]+)'?\s*\[([^\]]+)\]\s*", value)
    if not match:
        raise ValueError("seller_column debe tener formato Tabla[Columna].")
    return match.group(1).strip(), match.group(2).strip()


def build_seller_isolation_query(seller_column: str, expected_value: str) -> str:
    table, column = _parse_column_ref(seller_column)
    table_ref = "'" + table.replace("'", "''") + "'"
    column_ref = column.replace("]", "]]" )
    ref = f"{table_ref}[{column_ref}]"
    expected = _dax_string(expected_value)
    return (
        "EVALUATE\n"
        "ROW(\n"
        f"  \"VISIBLE_SELLERS\", COUNTROWS(VALUES({ref})),\n"
        f"  \"EXPECTED_VISIBLE\", COUNTROWS(FILTER(VALUES({ref}), {ref} = {expected})),\n"
        f"  \"OTHER_SELLERS\", COUNTROWS(FILTER(VALUES({ref}), NOT ISBLANK({ref}) && {ref} <> {expected}))\n"
        ")"
    )


def discover_seller_columns(project_path: Path) -> dict[str, Any]:
    """Busca candidatos de vendedor en el TMDL sin asumir que cliente/solicitante es vendedor."""
    _model_name, parts = load_local_tmdl_parts(project_path)
    model = inspect_tmdl_parts(parts, include_columns=True, max_items=5000)
    candidates: list[dict[str, Any]] = []
    for table in model.get("tables") or []:
        table_name = str(table.get("name") or "")
        for column in table.get("columns") or []:
            column_name = str(column.get("name") or "")
            source_column = str(column.get("source_column") or "")
            text = f"{table_name} {column_name} {source_column}".casefold()
            normalized = re.sub(r"[^a-z0-9áéíóúñ]+", "_", text)
            if any(term in normalized for term in _SELLER_EXCLUDE_TERMS):
                continue
            score = 0
            matched: list[str] = []
            for term in _SELLER_STRONG_TERMS:
                normalized_term = re.sub(r"[^a-z0-9áéíóúñ]+", "_", term.casefold())
                if normalized_term in normalized:
                    score += 100
                    matched.append(term)
            for term in _SELLER_WEAK_TERMS:
                if term in normalized:
                    score += 30
                    matched.append(term)
            if score:
                candidates.append(
                    {
                        "column": f"{table_name}[{column_name}]",
                        "score": score,
                        "matched_terms": sorted(set(matched)),
                        "hidden": bool(column.get("is_hidden")),
                    }
                )
    candidates.sort(key=lambda item: (-int(item["score"]), str(item["column"]).casefold()))
    strong = [item for item in candidates if int(item["score"]) >= 100]
    selected = strong[0]["column"] if len(strong) == 1 else None
    return {
        "selected": selected,
        "candidate_count": len(candidates),
        "strong_candidate_count": len(strong),
        "candidates": candidates[:20],
        "selection_mode": "AUTO_UNAMBIGUOUS" if selected else "REVIEW_REQUIRED" if candidates else "NOT_FOUND",
    }


def _flatten_evidence(value: Any, *, prefix: str = "") -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            items.extend(_flatten_evidence(child, prefix=child_prefix))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            items.extend(_flatten_evidence(child, prefix=f"{prefix}[{index}]"))
    else:
        items.append((prefix, str(value)))
    return items


def audit_power_automate_runtime_evidence(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    flattened = _flatten_evidence(payload)
    haystack = "\n".join(f"{key}={value}" for key, value in flattened).casefold()
    normalized = re.sub(r"[^a-z0-9]+", "_", haystack)

    signals = {signal: signal in normalized for signal in _RUNTIME_REQUIRED_SIGNALS}
    signal_count = sum(1 for present in signals.values() if present)
    has_run_id = any(
        re.search(r"(^|[._])run_?id$", key.casefold()) and value.strip()
        for key, value in flattened
    )
    successful_status = any(
        key.casefold().endswith("status") and value.strip().casefold() in {"success", "succeeded", "passed", "pass"}
        for key, value in flattened
    )
    has_runtime_time = any(
        any(token in key.casefold() for token in ("starttime", "start_time", "endtime", "end_time", "timestamp", "run_started"))
        and value.strip()
        for key, value in flattened
    )
    filename_pre = "pre_" in path.name.casefold() or "pre-" in path.name.casefold()
    runtime_evidence = has_run_id and successful_status and has_runtime_time and not filename_pre
    critical_signals = signals["g8_percentage_gate"] and signals["semantic_grounding_gate"] and signals["send_email_v2"]

    if runtime_evidence and signal_count == len(_RUNTIME_REQUIRED_SIGNALS) and critical_signals:
        status = "PASS"
    elif runtime_evidence:
        status = "REVIEW"
    else:
        status = "NOT_RUNTIME_EVIDENCE"

    return {
        "status": status,
        "runtime_evidence": runtime_evidence,
        "successful_status": successful_status,
        "run_id_present": has_run_id,
        "runtime_timestamp_present": has_runtime_time,
        "precert_filename": filename_pre,
        "required_signal_count": len(_RUNTIME_REQUIRED_SIGNALS),
        "signal_count": signal_count,
        "signals": signals,
        "token_values_exposed": False,
    }


async def _power_bi_probe(token: str | None, base_url: str, dataset_id: str | None) -> tuple[dict[str, Any], int]:
    if not token or not dataset_id:
        return _status("NOT_CONFIGURED", authenticated=bool(token), dataset_configured=bool(dataset_id)), 0
    query = 'EVALUATE ROW("ARTEL_RUNTIME_PROBE", 1)'
    response = await PowerBIClient(base_url, token, dataset_id).execute_dax(query)
    rows = _extract_rows(response)
    value = _row_value(rows[0], "ARTEL_RUNTIME_PROBE") if rows else None
    return _status("PASS" if value == 1 else "FAIL", rows=len(rows), probe_value=value, query_kind="DETERMINISTIC_ROW"), 1


async def _seller_probe(
    *,
    base_url: str,
    dataset_id: str | None,
    seller_column: str | None,
    seller_a: str | None,
    seller_b: str | None,
) -> tuple[dict[str, Any], int]:
    token_a = os.getenv("ARTEL_POWERBI_SELLER_A_TOKEN") or None
    token_b = os.getenv("ARTEL_POWERBI_SELLER_B_TOKEN") or None
    if not all((dataset_id, seller_column, seller_a, seller_b, token_a, token_b)):
        return _status(
            "NOT_CONFIGURED",
            mode="IDENTITY_ISOLATION",
            dataset_configured=bool(dataset_id),
            seller_column_configured=bool(seller_column),
            seller_values_configured=bool(seller_a and seller_b),
            identities_configured=bool(token_a and token_b),
        ), 0
    if token_a == token_b:
        return _status("FAIL", mode="IDENTITY_ISOLATION", reason="SELLER_TOKENS_IDENTICAL"), 0

    results: list[dict[str, Any]] = []
    calls = 0
    for label, token, expected in (("A", token_a, seller_a), ("B", token_b, seller_b)):
        query = build_seller_isolation_query(str(seller_column), str(expected))
        response = await PowerBIClient(base_url, token, dataset_id).execute_dax(query)
        calls += 1
        rows = _extract_rows(response)
        row = rows[0] if rows else {}
        visible = _row_value(row, "VISIBLE_SELLERS")
        expected_visible = _row_value(row, "EXPECTED_VISIBLE")
        other = _row_value(row, "OTHER_SELLERS")
        passed = expected_visible == 1 and other == 0 and visible == 1
        results.append(
            {
                "identity": label,
                "status": "PASS" if passed else "FAIL",
                "visible_sellers": visible,
                "expected_visible": expected_visible,
                "other_sellers": other,
            }
        )

    status = "PASS" if all(item["status"] == "PASS" for item in results) else "FAIL"
    return _status(status, mode="IDENTITY_ISOLATION", identities=results), calls


async def _fabric_probe(
    token: str | None,
    base_url: str,
    *,
    workspace_id: str | None,
    report_id: str | None,
    semantic_model_id: str | None,
) -> tuple[dict[str, Any], int]:
    if not token:
        return _status("NOT_CONFIGURED", authenticated=False), 0
    client = FabricClient(base_url, token)
    workspaces = await client.list_workspaces(max_pages=20)
    calls = max(1, int(workspaces.get("pages") or 1))
    result: dict[str, Any] = {
        "status": "PASS",
        "authenticated": True,
        "workspace_count": workspaces.get("count"),
        "definition_probe": "NOT_REQUESTED",
    }
    if workspace_id and report_id:
        report = await client.get_report_definition(workspace_id, report_id, definition_format="PBIR", max_polls=20)
        calls += 1
        result["report_definition"] = "PASS" if isinstance(report, dict) and report.get("definition") else "FAIL"
    if workspace_id and semantic_model_id:
        model = await client.get_semantic_model_definition(workspace_id, semantic_model_id, definition_format="TMDL", max_polls=20)
        calls += 1
        result["semantic_model_definition"] = "PASS" if isinstance(model, dict) and model.get("definition") else "FAIL"
    if workspace_id and (report_id or semantic_model_id):
        result["definition_probe"] = "PASS" if all(
            result.get(key, "PASS") == "PASS" for key in ("report_definition", "semantic_model_definition")
        ) else "FAIL"
        if result["definition_probe"] == "FAIL":
            result["status"] = "FAIL"
    return result, calls


def _list_count(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict) and isinstance(payload.get("value"), list):
        return len(payload["value"])
    return 0


async def _power_automate_api_probe(
    token: str | None,
    base_url: str,
    *,
    power_automate_url: str | None,
    environment_id: str | None,
    workflow_id: str | None,
) -> tuple[dict[str, Any], int]:
    parsed_environment: str | None = None
    parsed_workflow: str | None = None
    if power_automate_url:
        parsed_environment, parsed_workflow = parse_make_power_automate_url(power_automate_url)
    target_environment = environment_id or parsed_environment or os.getenv("POWER_AUTOMATE_ENVIRONMENT_ID") or None
    target_workflow = workflow_id or parsed_workflow or os.getenv("POWER_AUTOMATE_FLOW_ID") or None

    if not target_environment or not target_workflow:
        return _status(
            "NOT_CONFIGURED",
            authenticated=bool(token),
            target_configured=False,
            flow_discovery="NOT_RUN",
            action_inventory="NOT_RUN",
            run_history="NOT_RUN",
        ), 0
    if not token:
        return _status(
            "NOT_CONFIGURED",
            authenticated=False,
            target_configured=True,
            flow_discovery="NOT_RUN",
            action_inventory="NOT_RUN",
            run_history="NOT_RUN",
        ), 0

    client = PowerAutomateApiClient(token, base_url=base_url)
    flows = await client.list_cloud_flows(target_environment, target_workflow)
    actions = await client.list_flow_actions(target_environment, target_workflow)
    runs = await client.list_flow_runs(target_environment, target_workflow)
    calls = 3

    flow_count = _list_count(flows)
    action_summary = summarize_flow_actions(actions)
    run_summary = summarize_flow_runs(runs)
    all_signals = action_summary["signal_count"] == action_summary["required_signal_count"]

    if flow_count == 0:
        status = "FAIL"
    elif action_summary["action_count"] == 0:
        status = "REVIEW"
    elif run_summary["run_count"] == 0:
        status = "REVIEW"
    elif not all_signals:
        status = "REVIEW"
    else:
        status = "PASS"

    return _status(
        status,
        authenticated=True,
        target_configured=True,
        flow_discovery="PASS" if flow_count > 0 else "FAIL",
        flow_count=flow_count,
        action_inventory="PASS" if action_summary["action_count"] > 0 else "REVIEW",
        action_count=action_summary["action_count"],
        structural_signal_count=action_summary["signal_count"],
        structural_required_signal_count=action_summary["required_signal_count"],
        structural_signals=action_summary["signals"],
        action_names=action_summary["action_names"],
        run_history="PASS" if run_summary["run_count"] > 0 else "REVIEW",
        run_count=run_summary["run_count"],
        successful_run_count=run_summary["success_count"],
        failed_run_count=run_summary["failed_count"],
        latest_run=run_summary["latest_run"],
        runtime_action_outputs_validated=False,
        raw_parameters_returned=False,
        token_values_exposed=False,
    ), calls


async def run_runtime_certification(
    project_path: Path,
    *,
    dataset_id: str | None = None,
    seller_column: str | None = None,
    seller_a: str | None = None,
    seller_b: str | None = None,
    flow_run_evidence: Path | None = None,
    power_automate_url: str | None = None,
    power_automate_environment_id: str | None = None,
    power_automate_flow_id: str | None = None,
    fabric_workspace_id: str | None = None,
    fabric_report_id: str | None = None,
    fabric_semantic_model_id: str | None = None,
) -> dict[str, Any]:
    if not project_path.is_dir():
        raise FileNotFoundError(f"No existe el proyecto: {project_path}")
    settings = load_settings()
    target_dataset = dataset_id or settings.powerbi_dataset_id
    explicit_seller_column = seller_column or os.getenv("ARTEL_SELLER_COLUMN") or None
    seller_discovery = discover_seller_columns(project_path) if not explicit_seller_column else {
        "selected": explicit_seller_column,
        "candidate_count": 1,
        "strong_candidate_count": 1,
        "candidates": [{"column": explicit_seller_column, "score": "EXPLICIT", "matched_terms": []}],
        "selection_mode": "EXPLICIT",
    }
    effective_seller_column = explicit_seller_column or seller_discovery.get("selected")

    power_bi, pbi_calls = await _power_bi_probe(settings.powerbi_access_token, settings.powerbi_api_base_url, target_dataset)
    seller, seller_calls = await _seller_probe(
        base_url=settings.powerbi_api_base_url,
        dataset_id=target_dataset,
        seller_column=effective_seller_column,
        seller_a=seller_a or os.getenv("ARTEL_SELLER_A_VALUE") or None,
        seller_b=seller_b or os.getenv("ARTEL_SELLER_B_VALUE") or None,
    )
    seller["column_discovery"] = seller_discovery
    seller["effective_column"] = effective_seller_column

    fabric, fabric_calls = await _fabric_probe(
        settings.fabric_access_token,
        settings.fabric_api_base_url,
        workspace_id=fabric_workspace_id or os.getenv("FABRIC_WORKSPACE_ID") or None,
        report_id=fabric_report_id or os.getenv("FABRIC_REPORT_ID") or None,
        semantic_model_id=fabric_semantic_model_id or os.getenv("FABRIC_SEMANTIC_MODEL_ID") or None,
    )

    power_automate_api, power_automate_calls = await _power_automate_api_probe(
        settings.powerplatform_access_token,
        settings.powerplatform_api_base_url or "https://api.powerplatform.com",
        power_automate_url=power_automate_url,
        environment_id=power_automate_environment_id,
        workflow_id=power_automate_flow_id,
    )

    if flow_run_evidence:
        power_automate = audit_power_automate_runtime_evidence(flow_run_evidence)
    else:
        power_automate = _status("NOT_CONFIGURED", runtime_evidence=False)

    probes = {
        "power_bi_dax": power_bi,
        "seller_identity_isolation": seller,
        "fabric": fabric,
        "power_automate_api": power_automate_api,
        "power_automate": power_automate,
    }
    statuses = [probe["status"] for probe in probes.values()]
    if "FAIL" in statuses:
        overall = "FAIL"
    elif all(status == "PASS" for status in statuses):
        overall = "PASS"
    elif "REVIEW" in statuses or "NOT_RUNTIME_EVIDENCE" in statuses:
        overall = "REVIEW"
    else:
        overall = "BLOCKED"

    return {
        "certification_version": "1.7-runtime",
        "mode": "RUNTIME_READ_ONLY",
        "status": overall,
        "project_name": project_path.name,
        "probes": probes,
        "cloud_calls": pbi_calls + seller_calls + fabric_calls + power_automate_calls,
        "writes": 0,
        "secrets_returned": False,
        "seller_isolation_pass_requires_two_distinct_identities": True,
        "power_automate_full_runtime_pass_requires_action_level_evidence": True,
    }
