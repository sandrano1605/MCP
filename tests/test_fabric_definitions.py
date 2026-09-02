import asyncio

import httpx

from artel_powerplatform_mcp.clients import FabricClient

WORKSPACE_ID = "11111111-2222-3333-4444-555555555555"
REPORT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
MODEL_ID = "99999999-8888-7777-6666-555555555555"
OPERATION_ID = "12345678-1234-1234-1234-123456789012"


def test_report_definition_uses_pbir_endpoint_and_auth():
    async def run():
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert request.url.path.endswith(f"/workspaces/{WORKSPACE_ID}/reports/{REPORT_ID}/getDefinition")
            assert request.url.params["format"] == "PBIR"
            assert request.headers["Authorization"] == "Bearer fabric-token"
            return httpx.Response(
                200,
                json={
                    "definition": {
                        "format": "PBIR",
                        "parts": [
                            {
                                "path": "definition.pbir",
                                "payload": "e30=",
                                "payloadType": "InlineBase64",
                            }
                        ],
                    }
                },
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            api = FabricClient("https://api.fabric.microsoft.com/v1", "fabric-token", client=client)
            return await api.get_report_definition(WORKSPACE_ID, REPORT_ID)

    result = asyncio.run(run())
    assert result["definition"]["format"] == "PBIR"


def test_semantic_model_definition_follows_lro_to_result():
    async def run():
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(f"{request.method} {request.url.path}")
            if request.method == "POST":
                assert request.url.path.endswith(
                    f"/workspaces/{WORKSPACE_ID}/semanticModels/{MODEL_ID}/getDefinition"
                )
                assert request.url.params["format"] == "TMDL"
                return httpx.Response(
                    202,
                    headers={"x-ms-operation-id": OPERATION_ID, "Retry-After": "0"},
                )
            if request.url.path.endswith(f"/operations/{OPERATION_ID}/result"):
                return httpx.Response(
                    200,
                    json={
                        "definition": {
                            "format": "TMDL",
                            "parts": [
                                {
                                    "path": "definition/model.tmdl",
                                    "payload": "bW9kZWwgTW9kZWw=",
                                    "payloadType": "InlineBase64",
                                }
                            ],
                        }
                    },
                )
            if request.url.path.endswith(f"/operations/{OPERATION_ID}"):
                return httpx.Response(200, headers={"Retry-After": "0"}, json={"status": "Succeeded"})
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            api = FabricClient("https://api.fabric.microsoft.com/v1", "fabric-token", client=client)
            result = await api.get_semantic_model_definition(WORKSPACE_ID, MODEL_ID, max_polls=3)
        return calls, result

    calls, result = asyncio.run(run())
    assert len(calls) == 3
    assert result["definition"]["format"] == "TMDL"


def test_definition_rejects_bad_format_before_network():
    async def run():
        api = FabricClient("https://api.fabric.microsoft.com/v1", "fabric-token")
        await api.get_report_definition(WORKSPACE_ID, REPORT_ID, definition_format="INVALID")

    try:
        asyncio.run(run())
    except ValueError as exc:
        assert "PBIR" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
