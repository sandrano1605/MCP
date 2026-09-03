from __future__ import annotations

from pathlib import Path
from typing import Any

from .certification import certify_local_bi, run_self_test
from .config import load_settings
from .flow_audit import DEFAULT_REQUIRED_STEPS, audit_flow_definition, load_flow_export
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
        "purpose": "Informar versión y capacidades de policy/planning/certificación.",
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
    {
        "tool": "artel_self_test",
        "mode": "read",
        "purpose": "Ejecutar laboratorio end-to-end offline con PBIR, TMDL, DAX, RLS, Power Automate y guardas.",
    },
    {
        "tool": "artel_audit_power_automate_export",
        "mode": "read",
        "purpose": "Auditar un export JSON de Power Automate sin exponer secretos.",
    },
    {
        "tool": "artel_certify_local_bi",
        "mode": "read",
        "purpose": "Ejecutar auditoría completa read-only de un PBIP real y opcionalmente su export Power Automate.",
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
            "extension_contract_version": "1.7-e2e",
            "security_policy": True,
            "combined_planner": True,
            "offline_self_test": True,
            "power_automate_export_audit": True,
            "local_full_certification": True,
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


@mcp.tool(
    name="artel_self_test",
    annotations={
        "title": "ARTEL MCP self-test end-to-end",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def artel_self_test() -> ToolResult:
    """Crea un laboratorio temporal y certifica PBIR, TMDL, DAX, RLS, flow y guardas sin cloud ni escrituras."""
    result = run_self_test()
    return ToolResult(
        ok=result.get("status") == "PASS",
        status="PASS" if result.get("status") == "PASS" else "FAIL",
        operation="artel_self_test",
        data=result,
        findings=[item for item in result.get("checks", []) if item.get("status") != "PASS"],
    )


@mcp.tool(
    name="artel_audit_power_automate_export",
    annotations={
        "title": "Auditar export Power Automate",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def artel_audit_power_automate_export(
    flow_path: str,
    required_steps_csv: str | None = None,
) -> ToolResult:
    """Audita estructura, runAfter, pasos críticos e indicadores de secretos en un export JSON local."""
    required = [item.strip() for item in required_steps_csv.split(",") if item.strip()] if required_steps_csv else list(DEFAULT_REQUIRED_STEPS)
    result = audit_flow_definition(load_flow_export(Path(flow_path).expanduser()), required_steps=required)
    return ToolResult(
        ok=True,
        status="WARNING" if result.get("status") == "REVIEW" else "PASS",
        operation="artel_audit_power_automate_export",
        data=result,
        findings=result.get("findings", []),
        warnings=["Auditoría estática del export; no certifica una ejecución runtime del flujo."],
    )


@mcp.tool(
    name="artel_certify_local_bi",
    annotations={
        "title": "Certificar PBIP local end-to-end",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def artel_certify_local_bi(
    project_path: str | None = None,
    flow_path: str | None = None,
    expect_rls: bool = False,
    max_findings: int = 100,
) -> ToolResult:
    """Consolida inventario, canvas, modelo, medidas, policy, planner, secretos y flow sin modificar el proyecto."""
    result = certify_local_bi(
        _project_path(project_path),
        flow_path=Path(flow_path).expanduser() if flow_path else None,
        expect_rls=expect_rls,
        max_findings=max_findings,
    )
    status = result.get("status")
    return ToolResult(
        ok=status != "FAIL",
        status="FAIL" if status == "FAIL" else ("WARNING" if status == "REVIEW" else "PASS"),
        operation="artel_certify_local_bi",
        data=result,
        findings=result.get("project_findings", []),
        warnings=[
            "Certificación local read-only: runtime Power BI/Fabric/Power Automate y aislamiento por vendedor se reportan aparte."
        ],
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
