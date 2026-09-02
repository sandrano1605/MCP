from __future__ import annotations

from typing import Any

import httpx


class ApiConfigurationError(RuntimeError):
    """La configuración requerida para una API no está disponible."""


class ApiRequestError(RuntimeError):
    """Error remoto sanitizado para no filtrar trazas ni secretos."""


class PowerBIClient:
    def __init__(self, base_url: str, token: str | None, dataset_id: str | None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.dataset_id = dataset_id

    async def execute_dax(self, query: str, dataset_id: str | None = None) -> dict[str, Any]:
        if not self.token:
            raise ApiConfigurationError("Falta POWERBI_ACCESS_TOKEN; autentica fuera del repositorio y vuelve a intentar.")
        target_dataset = dataset_id or self.dataset_id
        if not target_dataset:
            raise ApiConfigurationError("Falta POWERBI_DATASET_ID o dataset_id en la solicitud.")
        if not query.strip():
            raise ValueError("La consulta DAX no puede estar vacía.")

        url = f"{self.base_url}/datasets/{target_dataset}/executeQueries"
        payload = {"queries": [{"query": query}], "serializerSettings": {"includeNulls": True}}
        return await _request_json("POST", url, self.token, json=payload)


class PowerPlatformClient:
    def __init__(self, base_url: str | None, token: str | None) -> None:
        self.base_url = base_url
        self.token = token

    async def request(self, method: str, path: str, *, json: Any = None) -> dict[str, Any]:
        if not self.base_url or not self.token:
            raise ApiConfigurationError(
                "Configura POWERPLATFORM_API_BASE_URL y POWERPLATFORM_ACCESS_TOKEN con una API aprobada por TI."
            )
        if not path.startswith("/"):
            raise ValueError("path debe comenzar con '/'.")
        return await _request_json(method, f"{self.base_url}{path}", self.token, json=json)


async def _request_json(method: str, url: str, token: str, **kwargs: Any) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if "json" in kwargs:
        headers["Content-Type"] = "application/json"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()
        if not response.content:
            return {"status_code": response.status_code}
        return response.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 401:
            raise ApiRequestError("Autenticación rechazada por la API; renueva el token delegado.") from None
        if status == 403:
            raise ApiRequestError("Permiso insuficiente para esta operación.") from None
        if status == 404:
            raise ApiRequestError("Recurso no encontrado; verifica entorno, workspace, dataset o flow ID.") from None
        if status == 429:
            raise ApiRequestError("Límite de solicitudes alcanzado; espera y reintenta.") from None
        raise ApiRequestError(f"La API devolvió HTTP {status}.") from None
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        raise ApiRequestError("No fue posible contactar la API dentro del tiempo límite.") from exc
