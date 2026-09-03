from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import load_settings
from .model_policy import assess_model_policy
from .models import ToolResult
from .pbir import inspect_pbir_parts, load_local_pbir_parts
from .planning import build_combined_plan
from .server import CAPABILITIES, mcp
from .tmdl import inspect_tmdl_parts, load_local_tmdl_parts

_EXTENSION_CAPABILITIES = [
    {
        "tool": "artel_extension_info",
        "mode": "read",
        "purpose": "Informar versión y capacidades de la capa de policy/planning.",
    },
    {
        "tool": "artel_tmdl_assess_local_security",
        "mode": "read",
        "purpose": "Evaluar postura RLS y riesgos de relaciones con expectativa explícita de aislamiento.",
    },
    {
        "tool": "artel_plan_local_bi",
        "mode": "read",
        "purpose": "Generar un plan combinado PBIR/TMDL en DRY_RUN, sin modificar archivos.",
    },
]

for capability in _EXTENSION_CAPABILITIES:
    if not any(item.get("tool") == capability["tool"] for item in CAPABILITIES):
        CAPABILITIES.append(capability)


def _project_path(value: str | None) -> Path:
    path = Path(value).expanduser() if value else load_settings().bi_project_path
    if not path:
        raise ValueError("Indica project_path o configura ARTEL_BI_PROJECT_PATH.")
    return path


@mcp.tool(
    name="artel_extension_info",
    annotations={
        "title": "Información de extensiones ARTEL MCP",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def artel_extension_info() -> ToolResult:
    return ToolResult(
        ok=True,
        status="PASS",
        operation="artel_extension_info",
        data={
            "extension_contract_version": "1.6-dry-run",
            "security_policy": True,
            "combined_planner": True,
            "writes_exposed": False,
            "apply_supported": False,
        },
    )


@mcp.tool(
    name="artel_tmdl_assess_local_security",
    annotations={
        "title": "Evaluar seguridad TMDL local",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def artel_tmdl_assess_local_security(
    project_path: str | None = None,
    semantic_model_name: str | None = None,
    expect_rls: bool = False,
) -> ToolResult:
    """Evalúa RLS/relaciones de un modelo local sin ejecutar DAX ni modificar TMDL."""
    selected_model, parts = load_local_tmdl_parts(
        _project_path(project_path),
        semantic_model_name=semantic_model_name,
    )
    model = inspect_tmdl_parts(parts, max_items=500)
    assessed = assess_model_policy(model, expect_rls=expect_rls)
    status = "WARNING" if assessed.get("status") == "REVIEW" else "PASS"
    return ToolResult(
        ok=True,
        status=status,
        operation="artel_tmdl_assess_local_security",
        data={
            "source": "local",
            "semantic_model": selected_model,
            "expect_rls": expect_rls,
            "assessment": assessed,
        },
        findings=assessed.get("findings", []),
        warnings=[
            "La postura de seguridad es estática; el aislamiento efectivo requiere certificación runtime."
        ],
    )


@mcp.tool(
    name="artel_plan_local_bi",
    annotations={
        "title": "Planificar cambios BI local en DRY_RUN",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def artel_plan_local_bi(
    project_path: str | None = None,
    report_name: str | None = None,
    semantic_model_name: str | None = None,
    expect_rls: bool = False,
    include_canvas: bool = True,
    include_model: bool = True,
    max_findings: int = 100,
) -> ToolResult:
    """Genera un plan combinado PBIR/TMDL. Nunca escribe: apply=false por contrato."""
    if not include_canvas and not include_model:
        raise ValueError("Debes incluir al menos canvas o model.")

    root = _project_path(project_path)
    canvas: dict[str, Any] | None = None
    model: dict[str, Any] | None = None
    metadata: dict[str, Any] = {"source": "local", "expect_rls": expect_rls}

    if include_canvas:
        selected_report, pbir_parts = load_local_pbir_parts(root, report_name=report_name)
        canvas = inspect_pbir_parts(pbir_parts, include_visuals=False, max_findings=max_findings)
        metadata["report"] = selected_report

    if include_model:
        selected_model, tmdl_parts = load_local_tmdl_parts(root, semantic_model_name=semantic_model_name)
        model = inspect_tmdl_parts(tmdl_parts, max_items=500)
        metadata["semantic_model"] = selected_model

    plan = build_combined_plan(model=model, canvas=canvas, expect_rls=expect_rls)
    status = "WARNING" if plan.get("status") == "REVIEW" else "PASS"
    findings = []
    for domain in (plan.get("model_plan"), plan.get("canvas_plan")):
        if domain:
            findings.extend(domain.get("actions", []))

    return ToolResult(
        ok=True,
        status=status,
        operation="artel_plan_local_bi",
        data={**metadata, "plan": plan},
        findings=findings,
        warnings=[
            "Plan DRY_RUN únicamente: no se generan ni aplican patches PBIR/TMDL en esta versión."
        ],
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
