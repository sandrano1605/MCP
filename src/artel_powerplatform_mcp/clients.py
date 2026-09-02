from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import httpx

RETRYABLE_STATUS = {429, 502, 503, 504}


class ApiConfigurationError(RuntimeError):
    """La configuración requerida para una API no está disponible."""


class ApiRequestError(RuntimeError):
    """Error remoto sanitizado para no filtrar trazas ni secretos."""


def _validate_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    parsed = urlparse(normalized)
    is_local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if not parsed.hostname or (parsed.scheme != "https" and not (is_local and parsed.scheme == "http")):
        raise ApiConfigurationError("La URL base debe usar HTTPS; HTTP solo se admite para localhost.")
    return normalized


def _validate_uuid(value: str, field_name: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise ValueError(f"{field_name} debe ser un GUID válido.") from exc


def _validate_dataset_id(dataset_id: str) -> str:
    return _validate_uuid(dataset_id, "dataset_id")


class PowerBIClient:
    def __init__(
        self,
        base_url: str,
        token: str | None,
        dataset_id: str | None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = _validate_base_url(base_url)
        self.token = token
        self.dataset_id = dataset_id
        self.client = client

    async def execute_dax(self, query: str, dataset_id: str | None = None) -> Any:
        if not self.token:
            raise ApiConfigurationError(
                "Falta autenticación Power BI; configura el broker o POWERBI_ACCESS_TOKEN."
            )
        target_dataset = dataset_id or self.dataset_id
        if not target_dataset:
            raise ApiConfigurationError("Falta POWERBI_DATASET_ID o dataset_id en la solicitud.")
        if not query.strip():
            raise ValueError("La consulta DAX no puede estar vacía.")

        target_dataset = _validate_dataset_id(target_dataset)
        url = f"{self.base_url}/datasets/{target_dataset}/executeQueries"
        payload = {
            "queries": [{"query": query}],
            "serializerSettings": {"includeNulls": True},
        }
        return await _request_json("POST", url, self.token, json=payload, client=self.client)


class FabricClient:
    """Cliente read-only para descubrimiento de Microsoft Fabric."""

    def __init__(
        self,
        base_url: str,
        token: str | None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = _validate_base_url(base_url)
        self.token = token
        self.client = client

    def _require_token(self) -> str:
        if not self.token:
            raise ApiConfigurationError(
                "Falta autenticación Fabric; configura FABRIC_ACCESS_TOKEN o usa el Auth Broker."
            )
        return self.token

    async def list_workspaces(
        self,
        *,
        roles: str | None = None,
        max_pages: int = 20,
    ) -> dict[str, Any]:
        token = self._require_token()
        if max_pages < 1 or max_pages > 100:
            raise ValueError("max_pages debe estar entre 1 y 100.")

        values: list[dict[str, Any]] = []
        continuation: str | None = None
        pages = 0
        while pages < max_pages:
            params: dict[str, Any] = {}
            if roles:
                params["roles"] = roles
            if continuation:
                params["continuationToken"] = continuation

            response = await _request_json(
                "GET",
                f"{self.base_url}/workspaces",
                token,
                params=params,
                client=self.client,
            )
            if not isinstance(response, dict):
                raise ApiRequestError("Fabric devolvió una respuesta inesperada al listar workspaces.")
            page_values = response.get("value") or []
            if not isinstance(page_values, list):
                raise ApiRequestError("Fabric devolvió 'value' con un formato inesperado.")
            values.extend(item for item in page_values if isinstance(item, dict))
            pages += 1
            continuation = response.get("continuationToken")
            if not continuation:
                break

        return {
            "value": values,
            "count": len(values),
            "pages": pages,
            "truncated": bool(continuation),
        }

    async def list_items(
        self,
        workspace_id: str,
        *,
        item_type: str | None = None,
        max_pages: int = 20,
    ) -> dict[str, Any]:
        token = self._require_token()
        workspace_id = _validate_uuid(workspace_id, "workspace_id")
        if max_pages < 1 or max_pages > 100:
            raise ValueError("max_pages debe estar entre 1 y 100.")

        values: list[dict[str, Any]] = []
        continuation: str | None = None
        pages = 0
        while pages < max_pages:
            params: dict[str, Any] = {}
            if item_type:
                params["type"] = item_type
            if continuation:
                params["continuationToken"] = continuation

            response = await _request_json(
                "GET",
                f"{self.base_url}/workspaces/{workspace_id}/items",
                token,
                params=params,
                client=self.client,
            )
            if not isinstance(response, dict):
                raise ApiRequestError("Fabric devolvió una respuesta inesperada al listar items.")
            page_values = response.get("value") or []
            if not isinstance(page_values, list):
                raise ApiRequestError("Fabric devolvió 'value' con un formato inesperado.")
            values.extend(item for item in page_values if isinstance(item, dict))
            pages += 1
            continuation = response.get("continuationToken")
            if not continuation:
                break

        return {
            "workspace_id": workspace_id,
            "item_type": item_type,
            "value": values,
            "count": len(values),
            "pages": pages,
            "truncated": bool(continuation),
        }

    async def get_item(self, workspace_id: str, item_id: str) -> Any:
        token = self._require_token()
        workspace_id = _validate_uuid(workspace_id, "workspace_id")
        item_id = _validate_uuid(item_id, "item_id")
        return await _request_json(
            "GET",
            f"{self.base_url}/workspaces/{workspace_id}/items/{item_id}",
            token,
            client=self.client,
        )


class PowerPlatformClient:
    def __init__(
        self,
        base_url: str | None,
        token: str | None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = _validate_base_url(base_url) if base_url else None
        self.token = token
        self.client = client

    async def request(self, method: str, path: str, *, json: Any = None) -> Any:
        if not self.base_url or not self.token:
            raise ApiConfigurationError(
                "Configura POWERPLATFORM_API_BASE_URL y autenticación Power Platform con una API aprobada por TI."
            )
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("path debe comenzar con un único '/'.")
        return await _request_json(
            method,
            f"{self.base_url}{path}",
            self.token,
            json=json,
            client=self.client,
        )


async def _request_json(
    method: str,
    url: str,
    token: str,
    *,
    json: Any = None,
    params: dict[str, Any] | None = None,
    client: httpx.AsyncClient | None = None,
    max_attempts: int = 3,
) -> Any:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if json is not None:
        headers["Content-Type"] = "application/json"

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=30.0)

    try:
        for attempt in range(1, max_attempts + 1):
            try:
                response = await active_client.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    params=params,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt >= max_attempts:
                    raise ApiRequestError("No fue posible contactar la API dentro del tiempo límite.") from exc
                await asyncio.sleep(0.25 * (2 ** (attempt - 1)))
                continue

            if response.status_code in RETRYABLE_STATUS and attempt < max_attempts:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 0.25 * (2 ** (attempt - 1))
                except ValueError:
                    delay = 0.25 * (2 ** (attempt - 1))
                await asyncio.sleep(min(delay, 5.0))
                continue

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status == 401:
                    raise ApiRequestError("Autenticación rechazada por la API; renueva el token delegado.") from None
                if status == 403:
                    raise ApiRequestError("Permiso insuficiente para esta operación.") from None
                if status == 404:
                    raise ApiRequestError(
                        "Recurso no encontrado; verifica entorno, workspace, dataset, item o flow ID."
                    ) from None
                if status == 429:
                    raise ApiRequestError("Límite de solicitudes alcanzado después de reintentos.") from None
                raise ApiRequestError(f"La API devolvió HTTP {status}.") from None

            if not response.content:
                return {"status_code": response.status_code}
            try:
                return response.json()
            except ValueError as exc:
                raise ApiRequestError("La API respondió contenido que no es JSON válido.") from exc

        raise ApiRequestError("La solicitud agotó los reintentos configurados.")
    finally:
        if owns_client:
            await active_client.aclose()
