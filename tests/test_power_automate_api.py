import asyncio

import httpx
import pytest

from artel_powerplatform_mcp.power_automate_api import (
    PowerAutomateApiClient,
    parse_make_power_automate_url,
    summarize_flow_actions,
    summarize_flow_runs,
)


ENVIRONMENT = "Default-87b645f5-cc1a-40c9-ad5b-f5c733a210de"
FLOW = "de5884a2-3c30-49c8-858f-a6cb624420c0"


def test_parse_make_power_automate_url_extracts_target():
    env, flow = parse_make_power_automate_url(
        f"https://make.powerautomate.com/environments/{ENVIRONMENT}/flows/{FLOW}?v3=true"
    )
    assert env == ENVIRONMENT
    assert flow == FLOW


def test_parse_make_power_automate_url_rejects_other_hosts():
    with pytest.raises(ValueError):
        parse_make_power_automate_url(
            f"https://example.com/environments/{ENVIRONMENT}/flows/{FLOW}"
        )


def test_power_automate_client_calls_only_documented_read_endpoints():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, dict(request.url.params), request.headers.get("Authorization")))
        if request.url.path.endswith("/cloudFlows"):
            return httpx.Response(200, json={"value": [{"workflowId": FLOW}]})
        if request.url.path.endswith("/flowActions"):
            return httpx.Response(200, json={"value": [{"actionName": "Payload_LLM"}]})
        if request.url.path.endswith("/flowRuns"):
            return httpx.Response(200, json={"value": [{"runId": "r1", "status": "Succeeded"}]})
        return httpx.Response(404, json={})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            api = PowerAutomateApiClient("secret-token", client=client)
            await api.list_cloud_flows(ENVIRONMENT, FLOW)
            await api.list_flow_actions(ENVIRONMENT, FLOW)
            await api.list_flow_runs(ENVIRONMENT, FLOW)

    asyncio.run(run())
    assert len(seen) == 3
    assert {path.rsplit("/", 1)[-1] for path, _, _ in seen} == {"cloudFlows", "flowActions", "flowRuns"}
    assert all(params["api-version"] == "2024-10-01" for _, params, _ in seen)
    assert all(params["workflowId"] == FLOW for _, params, _ in seen)
    assert all(auth == "Bearer secret-token" for _, _, auth in seen)


def test_action_summary_detects_required_structure_without_raw_parameters():
    names = [
        "Payload_LLM",
        "LLM_Adapter",
        "Parse_JSON_LLM",
        "G8_Percentage_Gate",
        "Semantic_Grounding_Gate",
        "Insight_Final",
        "Audit_Contract",
        "HTML_Email_Final",
        "Send_Email_V2",
    ]
    result = summarize_flow_actions(
        {"value": [{"actionName": name, "parameterValue": "do-not-return-this"} for name in names]}
    )
    assert result["signal_count"] == result["required_signal_count"] == 9
    assert result["raw_parameters_returned"] is False
    assert "do-not-return-this" not in str(result)


def test_run_summary_reports_status_without_action_outputs():
    result = summarize_flow_runs(
        {
            "value": [
                {
                    "runId": "run-2",
                    "status": "Failed",
                    "startTime": "2026-09-03T11:00:00Z",
                    "outputs": {"sensitive": "not-returned"},
                },
                {
                    "runId": "run-1",
                    "status": "Succeeded",
                    "startTime": "2026-09-03T10:00:00Z",
                },
            ]
        }
    )
    assert result["run_count"] == 2
    assert result["success_count"] == 1
    assert result["failed_count"] == 1
    assert result["latest_run"]["run_id"] == "run-2"
    assert result["action_inputs_outputs_returned"] is False
    assert "not-returned" not in str(result)
