import json

from .microsoft_stack import (
    dependency_status,
    route_work,
    stack_manifest,
    validate_layout_contract,
)
from .models import ToolResult
from .server import CAPABILITIES, mcp


_V18_CAPABILITIES = [
    {
        "tool": "artel_v18_stack_info",
        "mode": "read",
        "purpose": "Describe la arquitectura ARTEL + Microsoft Skills/MCP y su prioridad de evidencia.",
    },
    {
        "tool": "artel_v18_dependency_status",
        "mode": "read",
        "purpose": "Comprueba dependencias locales Microsoft sin ejecutar procesos ni exponer secretos.",
    },
    {
        "tool": "artel_v18_route_work",
        "mode": "read",
        "purpose": "Enruta planificación, diseño, PBIR, modelo, runtime, Power Automate o certificación al stack correcto.",
    },
    {
        "tool": "artel_v18_validate_layout_contract",
        "mode": "read",
        "purpose": "Valida bounds y overlaps básicos de un layout_contract de Design Brief antes de PBIR authoring.",
    },
]

for capability in _V18_CAPABILITIES:
    if not any(item.get("tool") == capability["tool"] for item in CAPABILITIES):
        CAPABILITIES.append(capability)


@mcp.tool(
    name="artel_v18_stack_info",
    annotations={
        "title": "Arquitectura ARTEL V1.8 Microsoft Skills",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def artel_v18_stack_info() -> ToolResult:
    return ToolResult(
        ok=True,
        status="PASS",
        operation="artel_v18_stack_info",
        data=stack_manifest(),
    )


@mcp.tool(
    name="artel_v18_dependency_status",
    annotations={
        "title": "Dependencias Microsoft Power BI",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def artel_v18_dependency_status() -> ToolResult:
    data = dependency_status()
    required = (
        data["npx"]["available"],
        data["powerbi_report_author"]["available"],
        data["powerbi_desktop_bridge"]["available"],
    )
    return ToolResult(
        ok=True,
        status="PASS" if all(required) else "WARNING",
        operation="artel_v18_dependency_status",
        data=data,
        warnings=[] if all(required) else [
            "Faltan una o más dependencias locales; el router puede continuar y marcar la fase afectada como bloqueada/manual."
        ],
    )


@mcp.tool(
    name="artel_v18_route_work",
    annotations={
        "title": "Enrutar trabajo Power BI/Power Automate",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def artel_v18_route_work(intent: str, allow_writes: bool = False) -> ToolResult:
    data = route_work(intent, allow_writes=allow_writes)
    return ToolResult(
        ok=True,
        status="PASS",
        operation="artel_v18_route_work",
        data=data,
        warnings=[
            "allow_writes solo expresa intención de ruta; las escrituras reales siguen sujetas a ARTEL_ALLOW_WRITES, dry_run, confirm y checkpoint."
        ] if allow_writes else [],
    )


@mcp.tool(
    name="artel_v18_validate_layout_contract",
    annotations={
        "title": "Validar contrato de layout Power BI",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def artel_v18_validate_layout_contract(layout_contract_json: str) -> ToolResult:
    try:
        payload = json.loads(layout_contract_json)
    except json.JSONDecodeError as exc:
        return ToolResult(
            ok=False,
            status="FAIL",
            operation="artel_v18_validate_layout_contract",
            findings=[{"code": "INVALID_JSON", "message": str(exc)}],
        )
    if not isinstance(payload, dict):
        return ToolResult(
            ok=False,
            status="FAIL",
            operation="artel_v18_validate_layout_contract",
            findings=[{"code": "LAYOUT_CONTRACT_MUST_BE_OBJECT"}],
        )
    result = validate_layout_contract(payload)
    return ToolResult(
        ok=True,
        status="PASS" if result["status"] == "PASS" else "WARNING",
        operation="artel_v18_validate_layout_contract",
        data=result,
        findings=result["findings"],
    )
