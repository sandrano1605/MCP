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


def _parse_retry_after(value: str | None, default: float = 0.25) -> float:
    try:
        return max(0.0, float(value)) if value is not None else default
    except ValueError:
        return default


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
    """Cliente Fabric read-only para discovery y recuperación de definiciones públicas."""

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

    async def get_report_definition(
        self,
        workspace_id: str,
        report_id: str,
        *,
        definition_format: str = "PBIR",
        max_polls: int = 20,
    ) -> dict[str, Any]:
        workspace_id = _validate_uuid(workspace_id, "workspace_id")
        report_id = _validate_uuid(report_id, "report_id")
        if definition_format not in {"PBIR", "PBIR-Legacy"}:
            raise ValueError("definition_format debe ser PBIR o PBIR-Legacy.")
        return await self._get_definition(
            f"/workspaces/{workspace_id}/reports/{report_id}/getDefinition",
            definition_format=definition_format,
            max_polls=max_polls,
        )

    async def get_semantic_model_definition(
        self,
        workspace_id: str,
        semantic_model_id: str,
        *,
        definition_format: str = "TMDL",
        max_polls: int = 20,
    ) -> dict[str, Any]:
        workspace_id = _validate_uuid(workspace_id, "workspace_id")
        semantic_model_id = _validate_uuid(semantic_model_id, "semantic_model_id")
        if definition_format not in {"TMDL", "TMSL"}:
            raise ValueError("definition_format debe ser TMDL o TMSL.")
        return await self._get_definition(
            f"/workspaces/{workspace_id}/semanticModels/{semantic_model_id}/getDefinition",
            definition_format=definition_format,
            max_polls=max_polls,
        )

    async def _get_definition(
        self,
        path: str,
        *,
        definition_format: str,
        max_polls: int,
    ) -> dict[str, Any]:
        token = self._require_token()
        if max_polls < 1 or max_polls > 60:
            raise ValueError("max_polls debe estar entre 1 y 60.")

        response = await _request_response(
            "POST",
            f"{self.base_url}{path}",
            token,
            params={"format": definition_format},
            client=self.client,
        )
        if response.status_code == 200:
            result = _response_json(response)
            if not isinstance(result, dict):
                raise ApiRequestError("Fabric devolvió una definición con formato inesperado.")
            return result

        if response.status_code != 202:
            raise ApiRequestError(f"Fabric devolvió HTTP {response.status_code} al solicitar la definición.")

        operation_id = response.headers.get("x-ms-operation-id")
        if not operation_id:
            raise ApiRequestError("Fabric inició una operación larga sin x-ms-operation-id.")
        operation_id = _validate_uuid(operation_id, "operation_id")
        retry_after = _parse_retry_after(response.headers.get("Retry-After"), 1.0)

        for _ in range(max_polls):
            await asyncio.sleep(min(retry_after, 10.0))
            state_response = await _request_response(
                "GET",
                f"{self.base_url}/operations/{operation_id}",
                token,
                client=self.client,
            )
            state = _response_json(state_response)
            if not isinstance(state, dict):
                raise ApiRequestError("Fabric devolvió un estado LRO inesperado.")
            status = str(state.get("status") or "")
            if status == "Succeeded":
                result_response = await _request_response(
                    "GET",
                    f"{self.base_url}/operations/{operation_id}/result",
                    token,
                    client=self.client,
                )
                result = _response_json(result_response)
                if not isinstance(result, dict):
                    raise ApiRequestError("Fabric devolvió un resultado LRO inesperado.")
                return result
            if status in {"Failed", "Cancelled"}:
                raise ApiRequestError(f"Fabric informó que la operación de definición terminó en estado {status}.")
            retry_after = _parse_retry_after(state_response.headers.get("Retry-After"), retry_after or 1.0)

        raise ApiRequestError("La operación Fabric no finalizó dentro del máximo de sondeos permitido.")


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


async def _request_response(
    method: str,
    url: str,
    token: str,
    *,
    json: Any = None,
    params: dict[str, Any] | None = None,
    client: httpx.AsyncClient | None = None,
    max_attempts: int = 3,
) -> httpx.Response:
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
                delay = _parse_retry_after(
                    response.headers.get("Retry-After"),
                    0.25 * (2 ** (attempt - 1)),
                )
                await asyncio.sleep(min(delay, 5.0))
                continue

            _raise_api_error(response)
            return response

        raise ApiRequestError("La solicitud agotó los reintentos configurados.")
    finally:
        if owns_client:
            await active_client.aclose()


def _raise_api_error(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    status = response.status_code
    if status == 401:
        raise ApiRequestError("Autenticación rechazada por la API; renueva el token delegado.")
    if status == 403:
        raise ApiRequestError("Permiso insuficiente para esta operación.")
    if status == 404:
        raise ApiRequestError("Recurso no encontrado; verifica entorno, workspace, dataset, item o flow ID.")
    if status == 429:
        raise ApiRequestError("Límite de solicitudes alcanzado después de reintentos.")
    raise ApiRequestError(f"La API devolvió HTTP {status}.")


def _response_json(response: httpx.Response) -> Any:
    if not response.content:
        return {"status_code": response.status_code}
    try:
        return response.json()
    except ValueError as exc:
        raise ApiRequestError("La API respondió contenido que no es JSON válido.") from exc


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
    response = await _request_response(
        method,
        url,
        token,
        json=json,
        params=params,
        client=client,
        max_attempts=max_attempts,
    )
    return _response_json(response)
