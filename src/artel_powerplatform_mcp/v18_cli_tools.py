from .microsoft_cli import desktop_manifest, desktop_open, desktop_status, validate_pbir
from .models import ToolResult
from .server import CAPABILITIES, mcp


_CAPABILITIES = [
    {
        "tool": "artel_v18_validate_pbir_official",
        "mode": "local-read",
        "purpose": "Valida PBIP/PBIR con el CLI oficial de Microsoft Power BI Report Authoring.",
    },
    {
        "tool": "artel_v18_powerbi_desktop_status",
        "mode": "local-read",
        "purpose": "Consulta instancias Power BI Desktop mediante el Desktop Bridge oficial.",
    },
    {
        "tool": "artel_v18_powerbi_desktop_manifest",
        "mode": "local-read",
        "purpose": "Obtiene el manifest seguro de una instancia Desktop por PID.",
    },
    {
        "tool": "artel_v18_powerbi_desktop_open",
        "mode": "local-open",
        "purpose": "Abre un PBIP/PBIX mediante el Desktop Bridge oficial, sin modificar el archivo.",
    },
]

for capability in _CAPABILITIES:
    if not any(item.get("tool") == capability["tool"] for item in CAPABILITIES):
        CAPABILITIES.append(capability)


def _to_tool_result(operation: str, result: dict) -> ToolResult:
    raw_status = result.get("status")
    if raw_status == "PASS":
        status = "PASS"
        ok = True
    elif raw_status == "BLOCKED":
        status = "BLOCKED"
        ok = False
    else:
        status = "FAIL"
        ok = False
    findings = []
    if result.get("reason"):
        findings.append({"code": result["reason"]})
    return ToolResult(
        ok=ok,
        status=status,
        operation=operation,
        data=result,
        findings=findings,
    )


@mcp.tool(
    name="artel_v18_validate_pbir_official",
    annotations={
        "title": "Validar PBIR con Microsoft CLI",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def artel_v18_validate_pbir_official(path: str) -> ToolResult:
    return _to_tool_result("artel_v18_validate_pbir_official", validate_pbir(path))


@mcp.tool(
    name="artel_v18_powerbi_desktop_status",
    annotations={
        "title": "Estado Power BI Desktop Bridge",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def artel_v18_powerbi_desktop_status(wait_seconds: int = 30) -> ToolResult:
    return _to_tool_result("artel_v18_powerbi_desktop_status", desktop_status(wait_seconds=wait_seconds))


@mcp.tool(
    name="artel_v18_powerbi_desktop_manifest",
    annotations={
        "title": "Manifest Power BI Desktop",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def artel_v18_powerbi_desktop_manifest(pid: int) -> ToolResult:
    return _to_tool_result("artel_v18_powerbi_desktop_manifest", desktop_manifest(pid))


@mcp.tool(
    name="artel_v18_powerbi_desktop_open",
    annotations={
        "title": "Abrir Power BI Desktop",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def artel_v18_powerbi_desktop_open(path: str) -> ToolResult:
    return _to_tool_result("artel_v18_powerbi_desktop_open", desktop_open(path))
