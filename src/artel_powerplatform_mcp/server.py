from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from .auth import AuthBroker
from .clients import FabricClient, PowerBIClient, PowerPlatformClient
from .config import load_settings
from .definitions import summarize_definition
from .guards import evaluate_mutation
from .local_audit import inspect_project, scan_for_embedded_secrets, validate_blueprint
from .models import ToolResult, ok_result

mcp = FastMCP("artel_powerplatform_mcp")
AUTH_BROKER = AuthBroker()

CAPABILITIES = [
    {"tool": "artel_list_capabilities", "mode": "read", "purpose": "Descubrir las capacidades disponibles del servidor."},
    {"tool": "artel_health", "mode": "read", "purpose": "Comprobar configuración sin revelar secretos."},
    {"tool": "artel_auth_status", "mode": "read", "purpose": "Consultar estado de autenticación sin devolver tokens."},
    {"tool": "artel_auth_begin_device_code", "mode": "auth", "purpose": "Iniciar autenticación Entra Device Code sin exponer credenciales."},
    {"tool": "artel_auth_complete_device_code", "mode": "auth", "purpose": "Completar Device Code y mantener el token únicamente en memoria."},
    {"tool": "artel_inspect_bi_project", "mode": "read", "purpose": "Inventariar PBIP, TMDL, PBIR, DAX y documentación local."},
    {"tool": "artel_validate_s510_blueprint", "mode": "read", "purpose": "Validar guardas críticas del blueprint S510."},
    {"tool": "artel_scan_embedded_secrets", "mode": "read", "purpose": "Detectar indicadores de secretos sin devolver sus valores."},
    {"tool": "artel_powerbi_execute_dax", "mode": "cloud-read", "purpose": "Ejecutar una consulta DAX mediante Power BI ExecuteQueries."},
    {"tool": "artel_fabric_list_workspaces", "mode": "cloud-read", "purpose": "Descubrir workspaces Fabric accesibles para la identidad actual."},
    {"tool": "artel_fabric_list_items", "mode": "cloud-read", "purpose": "Listar items de un workspace Fabric."},
    {"tool": "artel_fabric_get_item", "mode": "cloud-read", "purpose": "Obtener metadatos de un item Fabric."},
    {"tool": "artel_fabric_get_report_definition", "mode": "cloud-read", "purpose": "Obtener y resumir la definición PBIR de un Report Fabric."},
    {"tool": "artel_fabric_get_semantic_model_definition", "mode": "cloud-read", "purpose": "Obtener y resumir la definición TMDL de un Semantic Model Fabric."},
    {"tool": "artel_powerplatform_request", "mode": "guarded-cloud", "purpose": "Invocar una API Power Platform configurada; escrituras requieren triple guarda."},
]


def _project_path(value: str | None) -> Path:
    path = Path(value).expanduser() if value else load_settings().bi_project_path
    if not path:
        raise ValueError("Indica project_path o configura ARTEL_BI_PROJECT_PATH.")
    return path


def _fabric_client() -> FabricClient:
    settings = load_settings()
    return FabricClient(settings.fabric_api_base_url, AUTH_BROKER.get_token("fabric"))


@mcp.tool(
    name="artel_list_capabilities",
    annotations={"title": "Descubrir capacidades ARTEL MCP", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def artel_list_capabilities() -> ToolResult:
    """Lista las tools principales y su modo de operación para facilitar autodiscovery por cualquier LLM."""
    return ok_result(
        "artel_list_capabilities",
        status="PASS",
        data={"server": "artel_powerplatform_mcp", "contract_version": "1.3", "capabilities": CAPABILITIES},
    )


@mcp.tool(
    name="artel_health",
    annotations={"title": "Estado seguro ARTEL MCP", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
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
            "entra_device_code_configured": bool(settings.entra_client_id and settings.entra_tenant),
            "fabric_authenticated": AUTH_BROKER.status("fabric")["authenticated"],
            "powerbi_authenticated": AUTH_BROKER.status("powerbi")["authenticated"],
            "powerbi_dataset_configured": bool(settings.powerbi_dataset_id),
            "powerplatform_authenticated": AUTH_BROKER.status("powerplatform")["authenticated"],
            "powerplatform_base_url_configured": bool(settings.powerplatform_api_base_url),
            "token_values_exposed": False,
        },
    )


@mcp.tool(
    name="artel_auth_status",
    annotations={"title": "Estado de autenticación ARTEL", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def artel_auth_status(resource: Literal["fabric", "powerbi", "powerplatform"]) -> ToolResult:
    """Devuelve solamente metadatos seguros del estado de autenticación; jamás devuelve el access token."""
    return ok_result("artel_auth_status", status="PASS", data=AUTH_BROKER.status(resource))


@mcp.tool(
    name="artel_auth_begin_device_code",
    annotations={"title": "Iniciar Device Code ARTEL", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def artel_auth_begin_device_code(resource: Literal["fabric", "powerbi", "powerplatform"] = "fabric") -> ToolResult:
    """Inicia Microsoft Entra Device Code Flow. Devuelve código/URL de inicio, nunca tokens."""
    result = AUTH_BROKER.begin_device_flow(resource)
    return ok_result("artel_auth_begin_device_code", status="PASS", data=result)


@mcp.tool(
    name="artel_auth_complete_device_code",
    annotations={"title": "Completar Device Code ARTEL", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def artel_auth_complete_device_code(flow_id: str) -> ToolResult:
    """Completa el Device Code iniciado previamente y conserva el access token solo en memoria del proceso."""
    result = AUTH_BROKER.complete_device_flow(flow_id)
    return ok_result("artel_auth_complete_device_code", status="PASS", data=result)


@mcp.tool(
    name="artel_inspect_bi_project",
    annotations={"title": "Inspeccionar proyecto PBIP ARTEL", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def artel_inspect_bi_project(project_path: str | None = None) -> ToolResult:
    """Inspecciona un proyecto Power BI local. Si se omite project_path usa ARTEL_BI_PROJECT_PATH."""
    result = inspect_project(_project_path(project_path))
    return ok_result("artel_inspect_bi_project", status="PASS", data=result)


@mcp.tool(
    name="artel_validate_s510_blueprint",
    annotations={"title": "Validar blueprint S510", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
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
    annotations={"title": "Buscar secretos incrustados", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
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
    annotations={"title": "Ejecutar consulta DAX", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def artel_powerbi_execute_dax(query: str, dataset_id: str | None = None) -> ToolResult:
    """Ejecuta DAX contra un semantic model con Power BI ExecuteQueries. dataset_id debe ser GUID."""
    if len(query) > 100_000:
        raise ValueError("La consulta DAX excede el máximo de 100000 caracteres.")
    settings = load_settings()
    result = await PowerBIClient(
        settings.powerbi_api_base_url,
        AUTH_BROKER.get_token("powerbi"),
        settings.powerbi_dataset_id,
    ).execute_dax(query, dataset_id)
    return ok_result("artel_powerbi_execute_dax", status="PASS", data={"response": result})


@mcp.tool(
    name="artel_fabric_list_workspaces",
    annotations={"title": "Listar workspaces Fabric", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def artel_fabric_list_workspaces(roles: str | None = None, max_pages: int = 20) -> ToolResult:
    """Lista workspaces Fabric accesibles. Requiere Workspace.Read.All o permiso equivalente."""
    result = await _fabric_client().list_workspaces(roles=roles, max_pages=max_pages)
    return ok_result("artel_fabric_list_workspaces", status="PASS", data=result)


@mcp.tool(
    name="artel_fabric_list_items",
    annotations={"title": "Listar items Fabric", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def artel_fabric_list_items(workspace_id: str, item_type: str | None = None, max_pages: int = 20) -> ToolResult:
    """Lista items de un workspace Fabric. Puede filtrar por tipo, por ejemplo Report o SemanticModel."""
    result = await _fabric_client().list_items(workspace_id, item_type=item_type, max_pages=max_pages)
    return ok_result("artel_fabric_list_items", status="PASS", data=result)


@mcp.tool(
    name="artel_fabric_get_item",
    annotations={"title": "Obtener item Fabric", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def artel_fabric_get_item(workspace_id: str, item_id: str) -> ToolResult:
    """Obtiene metadatos de un item Fabric sin modificarlo."""
    result = await _fabric_client().get_item(workspace_id, item_id)
    return ok_result("artel_fabric_get_item", status="PASS", data={"item": result})


@mcp.tool(
    name="artel_fabric_get_report_definition",
    annotations={"title": "Obtener definición PBIR Fabric", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def artel_fabric_get_report_definition(
    workspace_id: str,
    report_id: str,
    definition_format: Literal["PBIR", "PBIR-Legacy"] = "PBIR",
    include_content: bool = False,
    max_content_chars: int = 20_000,
    max_polls: int = 20,
) -> ToolResult:
    """Recupera la definición pública de un Report. Por defecto devuelve manifiesto sin payload para ahorrar contexto."""
    response = await _fabric_client().get_report_definition(
        workspace_id,
        report_id,
        definition_format=definition_format,
        max_polls=max_polls,
    )
    definition = summarize_definition(
        response,
        include_content=include_content,
        max_content_chars=max_content_chars,
    )
    return ok_result(
        "artel_fabric_get_report_definition",
        status="PASS",
        data={"workspace_id": workspace_id, "report_id": report_id, "definition": definition},
    )


@mcp.tool(
    name="artel_fabric_get_semantic_model_definition",
    annotations={"title": "Obtener definición TMDL Fabric", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def artel_fabric_get_semantic_model_definition(
    workspace_id: str,
    semantic_model_id: str,
    definition_format: Literal["TMDL", "TMSL"] = "TMDL",
    include_content: bool = False,
    max_content_chars: int = 20_000,
    max_polls: int = 20,
) -> ToolResult:
    """Recupera la definición pública de un Semantic Model. Por defecto devuelve manifiesto sin payload."""
    response = await _fabric_client().get_semantic_model_definition(
        workspace_id,
        semantic_model_id,
        definition_format=definition_format,
        max_polls=max_polls,
    )
    definition = summarize_definition(
        response,
        include_content=include_content,
        max_content_chars=max_content_chars,
    )
    return ok_result(
        "artel_fabric_get_semantic_model_definition",
        status="PASS",
        data={"workspace_id": workspace_id, "semantic_model_id": semantic_model_id, "definition": definition},
    )


@mcp.tool(
    name="artel_powerplatform_request",
    annotations={"title": "Solicitud Power Platform controlada", "readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
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
    decision = evaluate_mutation(method, dry_run=dry_run, confirm=confirm, allow_writes=settings.allow_writes)
    if not decision.allowed:
        return ToolResult(
            ok=True,
            status="DRY_RUN" if decision.reason == "DRY_RUN_ENABLED" else "BLOCKED",
            operation="artel_powerplatform_request",
            data={"would_call": method, "path": path, "reason": decision.reason, "writes_enabled": settings.allow_writes},
        )

    result = await PowerPlatformClient(
        settings.powerplatform_api_base_url,
        AUTH_BROKER.get_token("powerplatform"),
    ).request(method, path, json=payload)
    return ok_result("artel_powerplatform_request", status="PASS", data={"response": result})


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
