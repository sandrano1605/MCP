from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from .clients import PowerBIClient, PowerPlatformClient
from .config import load_settings
from .local_audit import inspect_project, scan_for_embedded_secrets, validate_blueprint

mcp = FastMCP("artel_powerplatform_mcp")


class ProjectInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    project_path: str | None = Field(default=None, description="Ruta absoluta del proyecto BI; usa ARTEL_BI_PROJECT_PATH si se omite.")


class DaxInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=100_000, description="Consulta DAX EVALUATE para ExecuteQueries.")
    dataset_id: str | None = Field(default=None, description="Dataset/semantic model ID; usa POWERBI_DATASET_ID si se omite.")


class PowerPlatformRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    method: str = Field(pattern=r"^(GET|POST|PATCH|PUT|DELETE)$")
    path: str = Field(pattern=r"^/", max_length=500)
    payload: dict[str, Any] | None = None
    dry_run: bool = True
    confirm: bool = False


def _project_path(value: str | None) -> Path:
    path = Path(value) if value else load_settings().bi_project_path
    if not path:
        raise ValueError("Indica project_path o configura ARTEL_BI_PROJECT_PATH.")
    return path


@mcp.tool(name="artel_inspect_bi_project", annotations={"title": "Inspeccionar proyecto PBIP ARTEL", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def artel_inspect_bi_project(params: ProjectInput) -> str:
    """Inspeccionar estructura local del proyecto Power BI sin modificar archivos."""
    return json.dumps(inspect_project(_project_path(params.project_path)), ensure_ascii=False, indent=2)


@mcp.tool(name="artel_validate_s510_blueprint", annotations={"title": "Validar blueprint S510", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def artel_validate_s510_blueprint(params: ProjectInput) -> str:
    """Validar guardas críticas del blueprint S510 antes de operar Power Automate."""
    return json.dumps(validate_blueprint(_project_path(params.project_path)), ensure_ascii=False, indent=2)


@mcp.tool(name="artel_scan_embedded_secrets", annotations={"title": "Buscar secretos incrustados", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def artel_scan_embedded_secrets(params: ProjectInput) -> str:
    """Detectar patrones de credenciales en archivos legibles; nunca devuelve valores encontrados."""
    return json.dumps(scan_for_embedded_secrets(_project_path(params.project_path)), ensure_ascii=False, indent=2)


@mcp.tool(name="artel_powerbi_execute_dax", annotations={"title": "Ejecutar consulta DAX", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def artel_powerbi_execute_dax(params: DaxInput) -> str:
    """Ejecutar DAX contra un semantic model mediante Power BI ExecuteQueries."""
    settings = load_settings()
    result = await PowerBIClient(settings.powerbi_api_base_url, settings.powerbi_access_token, settings.powerbi_dataset_id).execute_dax(params.query, params.dataset_id)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool(name="artel_powerplatform_request", annotations={"title": "Solicitud Power Platform controlada", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
async def artel_powerplatform_request(params: PowerPlatformRequest) -> str:
    """Enviar una solicitud a una API Power Platform configurada por TI.

    Las operaciones mutantes requieren ARTEL_ALLOW_WRITES=true, dry_run=false y confirm=true.
    DELETE nunca se habilita en esta primera versión.
    """
    if params.method == "DELETE":
        raise ValueError("DELETE está bloqueado en la primera versión; usa una herramienta específica con doble confirmación.")
    is_mutation = params.method in {"POST", "PATCH", "PUT"}
    if is_mutation and (params.dry_run or not params.confirm or not load_settings().allow_writes):
        return json.dumps({"dry_run": True, "would_call": params.method, "path": params.path, "message": "Solicitud no ejecutada. Requiere dry_run=false, confirm=true y ARTEL_ALLOW_WRITES=true."}, ensure_ascii=False, indent=2)
    settings = load_settings()
    result = await PowerPlatformClient(settings.powerplatform_api_base_url, settings.powerplatform_access_token).request(params.method, params.path, json=params.payload)
    return json.dumps(result, ensure_ascii=False, indent=2)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
