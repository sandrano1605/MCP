from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from .clients import PowerBIClient, PowerPlatformClient
from .config import load_settings
from .guards import evaluate_mutation
from .local_audit import inspect_project, scan_for_embedded_secrets, validate_blueprint
from .models import ToolResult, ok_result

mcp = FastMCP("artel_powerplatform_mcp")

CAPABILITIES = [
    {
        "tool": "artel_list_capabilities",
        "mode": "read",
        "purpose": "Descubrir las capacidades disponibles del servidor.",
    },
    {
        "tool": "artel_health",
        "mode": "read",
        "purpose": "Comprobar configuración sin revelar secretos.",
    },
    {
        "tool": "artel_inspect_bi_project",
        "mode": "read",
        "purpose": "Inventariar PBIP, TMDL, PBIR, DAX y documentación local.",
    },
    {
        "tool": "artel_validate_s510_blueprint",
        "mode": "read",
        "purpose": "Validar guardas críticas del blueprint S510.",
    },
    {
        "tool": "artel_scan_embedded_secrets",
        "mode": "read",
        "purpose": "Detectar indicadores de secretos sin devolver sus valores.",
    },
    {
        "tool": "artel_powerbi_execute_dax",
        "mode": "cloud-read",
        "purpose": "Ejecutar una consulta DAX mediante Power BI ExecuteQueries.",
    },
    {
        "tool": "artel_powerplatform_request",
        "mode": "guarded-cloud",
        "purpose": "Invocar una API Power Platform configurada; escrituras requieren triple guarda.",
    },
]


def _project_path(value: str | None) -> Path:
    path = Path(value).expanduser() if value else load_settings().bi_project_path
    if not path:
        raise ValueError("Indica project_path o configura ARTEL_BI_PROJECT_PATH.")
    return path


@mcp.tool(
    name="artel_list_capabilities",
    annotations={
        "title": "Descubrir capacidades ARTEL MCP",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def artel_list_capabilities() -> ToolResult:
    """Lista las tools principales y su modo de operación para facilitar autodiscovery por cualquier LLM."""

    return ok_result(
        "artel_list_capabilities",
        status="PASS",
        data={
            "server": "artel_powerplatform_mcp",
            "contract_version": "1.1",
            "capabilities": CAPABILITIES,
        },
    )


@mcp.tool(
    name="artel_health",
    annotations={
        "title": "Estado seguro ARTEL MCP",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def artel_health() -> ToolResult:
    """Comprueba configuración y disponibilidad local sin revelar tokens, IDs o rutas completas."""

    settings = load_settings()
    project_configured = settings.bi_project_path is not None
    project_exists = bool(settings.bi_project_path and settings.bi_project_path.is_dir())
    return ok_result(
        "artel_health",
        status="PASS",
        data={
            "project_path_configured": project_configured,
            "project_path_exists": project_exists,
            "writes_enabled": settings.allow_writes,
            "powerbi_token_configured": bool(settings.powerbi_access_token),
            "powerbi_dataset_configured": bool(settings.powerbi_dataset_id),
            "powerplatform_token_configured": bool(settings.powerplatform_access_token),
            "powerplatform_base_url_configured": bool(settings.powerplatform_api_base_url),
        },
    )


@mcp.tool(
    name="artel_inspect_bi_project",
    annotations={
        "title": "Inspeccionar proyecto PBIP ARTEL",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def artel_inspect_bi_project(project_path: str | None = None) -> ToolResult:
    """Inspecciona un proyecto Power BI local. Si se omite project_path usa ARTEL_BI_PROJECT_PATH."""

    result = inspect_project(_project_path(project_path))
    return ok_result("artel_inspect_bi_project", status="PASS", data=result)


@mcp.tool(
    name="artel_validate_s510_blueprint",
    annotations={
        "title": "Validar blueprint S510",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def artel_validate_s510_blueprint(project_path: str | None = None) -> ToolResult:
    """Valida guardas críticas del blueprint S510 sin modificar el proyecto."""

    result = validate_blueprint(_project_path(project_path))
    return ToolResult(
        ok=bool(result["valid"]),
        status="PASS" if result["valid"] else "FAIL",
        operation="artel_validate_s510_blueprint",
        data=result,
    )


@mcp.tool(
    name="artel_scan_embedded_secrets",
    annotations={
        "title": "Buscar secretos incrustados",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def artel_scan_embedded_secrets(project_path: str | None = None, limit: int = 100) -> ToolResult:
    """Detecta indicadores de credenciales sin devolver el valor encontrado."""

    result = scan_for_embedded_secrets(_project_path(project_path), limit=limit)
    findings = result.pop("findings")
    warnings = [result["warning"]] if result.get("warning") else []
    return ToolResult(
        ok=True,
        status="WARNING" if findings else "PASS",
        operation="artel_scan_embedded_secrets",
        data=result,
        findings=findings,
        warnings=warnings,
    )


@mcp.tool(
    name="artel_powerbi_execute_dax",
    annotations={
        "title": "Ejecutar consulta DAX",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def artel_powerbi_execute_dax(query: str, dataset_id: str | None = None) -> ToolResult:
    """Ejecuta DAX contra un semantic model con Power BI ExecuteQueries. dataset_id debe ser GUID."""

    if len(query) > 100_000:
        raise ValueError("La consulta DAX excede el máximo de 100000 caracteres.")
    settings = load_settings()
    result = await PowerBIClient(
        settings.powerbi_api_base_url,
        settings.powerbi_access_token,
        settings.powerbi_dataset_id,
    ).execute_dax(query, dataset_id)
    return ok_result(
        "artel_powerbi_execute_dax",
        status="PASS",
        data={"response": result},
    )


@mcp.tool(
    name="artel_powerplatform_request",
    annotations={
        "title": "Solicitud Power Platform controlada",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def artel_powerplatform_request(
    method: Literal["GET", "POST", "PATCH", "PUT", "DELETE"],
    path: str,
    payload: dict[str, Any] | None = None,
    dry_run: bool = True,
    confirm: bool = False,
) -> ToolResult:
    """Invoca una API Power Platform configurada.

    GET es lectura. POST/PATCH/PUT requieren dry_run=false, confirm=true y ARTEL_ALLOW_WRITES=true.
    DELETE permanece bloqueado en esta etapa.
    """

    if not path.startswith("/") or path.startswith("//") or len(path) > 500:
        raise ValueError("path debe comenzar con un único '/' y tener como máximo 500 caracteres.")

    settings = load_settings()
    decision = evaluate_mutation(
        method,
        dry_run=dry_run,
        confirm=confirm,
        allow_writes=settings.allow_writes,
    )

    if not decision.allowed:
        return ToolResult(
            ok=True,
            status="DRY_RUN" if decision.reason == "DRY_RUN_ENABLED" else "BLOCKED",
            operation="artel_powerplatform_request",
            data={
                "would_call": method,
                "path": path,
                "reason": decision.reason,
                "writes_enabled": settings.allow_writes,
            },
        )

    result = await PowerPlatformClient(
        settings.powerplatform_api_base_url,
        settings.powerplatform_access_token,
    ).request(method, path, json=payload)
    return ok_result(
        "artel_powerplatform_request",
        status="PASS",
        data={"response": result},
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
