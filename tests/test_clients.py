import asyncio

import httpx
import pytest

from artel_powerplatform_mcp.clients import ApiRequestError, PowerBIClient

DATASET_ID = "11111111-2222-3333-4444-555555555555"


def test_powerbi_execute_dax_uses_expected_endpoint_and_auth():
    async def run():
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert request.url.path.endswith(f"/datasets/{DATASET_ID}/executeQueries")
            assert request.headers["Authorization"] == "Bearer test-token"
            return httpx.Response(200, json={"results": [{"tables": []}]})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            api = PowerBIClient(
                "https://api.powerbi.com/v1.0/myorg",
                "test-token",
                DATASET_ID,
                client=client,
            )
            return await api.execute_dax("EVALUATE ROW(\"x\", 1)")

    result = asyncio.run(run())
    assert result["results"][0]["tables"] == []


def test_powerbi_rejects_invalid_dataset_id_before_network_call():
    async def run():
        api = PowerBIClient(
            "https://api.powerbi.com/v1.0/myorg",
            "test-token",
            "not-a-guid",
        )
        await api.execute_dax("EVALUATE ROW(\"x\", 1)")

    with pytest.raises(ValueError, match="GUID válido"):
        asyncio.run(run())


def test_http_401_error_is_sanitized():
    async def run():
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"server_detail": "do-not-leak-this"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            api = PowerBIClient(
                "https://api.powerbi.com/v1.0/myorg",
                "test-token",
                DATASET_ID,
                client=client,
            )
            await api.execute_dax("EVALUATE ROW(\"x\", 1)")

    with pytest.raises(ApiRequestError) as exc_info:
        asyncio.run(run())
    assert "do-not-leak-this" not in str(exc_info.value)
    assert "Autenticación rechazada" in str(exc_info.value)


def test_http_429_is_retried_then_succeeds():
    async def run():
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            if calls["count"] == 1:
                return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "throttled"})
            return httpx.Response(200, json={"results": []})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            api = PowerBIClient(
                "https://api.powerbi.com/v1.0/myorg",
                "test-token",
                DATASET_ID,
                client=client,
            )
            result = await api.execute_dax("EVALUATE ROW(\"x\", 1)")
        return calls["count"], result

    count, result = asyncio.run(run())
    assert count == 2
    assert result == {"results": []}
