import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from artel_powerplatform_mcp import runtime_certification as runtime


def test_build_seller_isolation_query_is_scoped_and_safe():
    query = runtime.build_seller_isolation_query("S150_MASTER_CUADRADA[Solicitante]", 'A"1')
    assert "VISIBLE_SELLERS" in query
    assert "EXPECTED_VISIBLE" in query
    assert "OTHER_SELLERS" in query
    assert "'S150_MASTER_CUADRADA'[Solicitante]" in query
    assert 'A""1' in query


def test_pre_g8_file_cannot_be_runtime_pass(tmp_path: Path):
    path = tmp_path / "S510_PRE_G8_CERTIFIED.json"
    path.write_text(
        json.dumps(
            {
                "run_id": "abc",
                "status": "Succeeded",
                "timestamp": "2026-09-02T12:00:00Z",
                "Payload_LLM": True,
                "LLM_Adapter": True,
                "Parse_JSON_LLM": True,
                "G8_Percentage_Gate": True,
                "Semantic_Grounding_Gate": True,
                "Insight_Final": True,
                "Audit_Contract": True,
                "HTML_Email_Final": True,
                "Send_Email_V2": True,
            }
        ),
        encoding="utf-8",
    )
    result = runtime.audit_power_automate_runtime_evidence(path)
    assert result["status"] == "NOT_RUNTIME_EVIDENCE"
    assert result["precert_filename"] is True


def test_runtime_flow_evidence_passes_only_with_full_signals(tmp_path: Path):
    path = tmp_path / "S510_RUN_20260902.json"
    path.write_text(
        json.dumps(
            {
                "run_id": "abc",
                "status": "Succeeded",
                "start_time": "2026-09-02T12:00:00Z",
                "Payload_LLM": "PASS",
                "LLM_Adapter": "PASS",
                "Parse_JSON_LLM": "PASS",
                "G8_Percentage_Gate": "PASS",
                "Semantic_Grounding_Gate": "PASS",
                "Insight_Final": "PASS",
                "Audit_Contract": "PASS",
                "HTML_Email_Final": "PASS",
                "Send_Email_V2": "PASS",
            }
        ),
        encoding="utf-8",
    )
    result = runtime.audit_power_automate_runtime_evidence(path)
    assert result["status"] == "PASS"
    assert result["runtime_evidence"] is True
    assert result["signal_count"] == result["required_signal_count"]


def test_runtime_certification_separates_dax_fabric_identity_and_flow_api(monkeypatch, tmp_path: Path):
    class FakePBI:
        def __init__(self, base_url, token, dataset_id):
            self.token = token

        async def execute_dax(self, query, dataset_id=None):
            if "ARTEL_RUNTIME_PROBE" in query:
                return {"results": [{"tables": [{"rows": [{"[ARTEL_RUNTIME_PROBE]": 1}]}]}]}
            expected = "A" if self.token == "token-a" else "B"
            return {
                "results": [
                    {
                        "tables": [
                            {
                                "rows": [
                                    {
                                        "[VISIBLE_SELLERS]": 1,
                                        "[EXPECTED_VISIBLE]": 1,
                                        "[OTHER_SELLERS]": 0,
                                        "expected": expected,
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }

    class FakeFabric:
        def __init__(self, base_url, token):
            pass

        async def list_workspaces(self, max_pages=20):
            return {"count": 2, "pages": 1, "value": []}

        async def get_report_definition(self, *args, **kwargs):
            return {"definition": {"parts": []}}

        async def get_semantic_model_definition(self, *args, **kwargs):
            return {"definition": {"parts": []}}

    class FakeFlowApi:
        def __init__(self, token, base_url):
            assert token == "powerplatform-token"

        async def list_cloud_flows(self, environment_id, workflow_id):
            return {"value": [{"workflowId": workflow_id}]}

        async def list_flow_actions(self, environment_id, workflow_id):
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
            return {"value": [{"actionName": name} for name in names]}

        async def list_flow_runs(self, environment_id, workflow_id):
            return {"value": [{"runId": "run-1", "status": "Succeeded", "startTime": "2026-09-03T10:00:00Z"}]}

    monkeypatch.setattr(runtime, "PowerBIClient", FakePBI)
    monkeypatch.setattr(runtime, "FabricClient", FakeFabric)
    monkeypatch.setattr(runtime, "PowerAutomateApiClient", FakeFlowApi)
    monkeypatch.setattr(
        runtime,
        "load_settings",
        lambda: SimpleNamespace(
            powerbi_access_token="main-token",
            powerbi_api_base_url="https://api.powerbi.com/v1.0/myorg",
            powerbi_dataset_id="11111111-1111-1111-1111-111111111111",
            fabric_access_token="fabric-token",
            fabric_api_base_url="https://api.fabric.microsoft.com/v1",
            powerplatform_access_token="powerplatform-token",
            powerplatform_api_base_url="https://api.powerplatform.com",
        ),
    )
    monkeypatch.setenv("ARTEL_POWERBI_SELLER_A_TOKEN", "token-a")
    monkeypatch.setenv("ARTEL_POWERBI_SELLER_B_TOKEN", "token-b")

    result = asyncio.run(
        runtime.run_runtime_certification(
            tmp_path,
            seller_column="S150_MASTER_CUADRADA[Solicitante]",
            seller_a="A",
            seller_b="B",
            power_automate_environment_id="Default-87b645f5-cc1a-40c9-ad5b-f5c733a210de",
            power_automate_flow_id="de5884a2-3c30-49c8-858f-a6cb624420c0",
        )
    )
    assert result["probes"]["power_bi_dax"]["status"] == "PASS"
    assert result["probes"]["seller_identity_isolation"]["status"] == "PASS"
    assert result["probes"]["fabric"]["status"] == "PASS"
    assert result["probes"]["power_automate_api"]["status"] == "PASS"
    assert result["probes"]["power_automate_api"]["structural_signal_count"] == 9
    assert result["probes"]["power_automate_api"]["runtime_action_outputs_validated"] is False
    assert result["probes"]["power_automate"]["status"] == "NOT_CONFIGURED"
    assert result["status"] == "BLOCKED"
    assert result["writes"] == 0
    assert result["secrets_returned"] is False


def test_identical_seller_tokens_fail_identity_certification(monkeypatch):
    monkeypatch.setenv("ARTEL_POWERBI_SELLER_A_TOKEN", "same")
    monkeypatch.setenv("ARTEL_POWERBI_SELLER_B_TOKEN", "same")
    result, calls = asyncio.run(
        runtime._seller_probe(
            base_url="https://api.powerbi.com/v1.0/myorg",
            dataset_id="11111111-1111-1111-1111-111111111111",
            seller_column="Sales[Seller]",
            seller_a="A",
            seller_b="B",
        )
    )
    assert calls == 0
    assert result["status"] == "FAIL"
    assert result["reason"] == "SELLER_TOKENS_IDENTICAL"
