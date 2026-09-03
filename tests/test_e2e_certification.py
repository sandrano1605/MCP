import json
from pathlib import Path

from artel_powerplatform_mcp.certification import _write_lab_project, certify_local_bi, run_self_test
from artel_powerplatform_mcp.flow_audit import audit_flow_definition, load_flow_export


def test_self_test_passes_all_offline_contracts():
    result = run_self_test()

    assert result["status"] == "PASS"
    assert result["failed"] == 0
    assert result["passed"] == result["check_count"]
    assert result["cloud_calls"] == 0
    assert result["writes"] == 0
    assert result["fixture_summary"]["pages"] == 2
    assert result["fixture_summary"]["measures"] >= 4
    assert result["fixture_summary"]["roles"] == 1


def test_full_local_certification_separates_engine_pass_from_project_review(tmp_path: Path):
    root = tmp_path / "lab"
    _write_lab_project(root)

    result = certify_local_bi(
        root,
        flow_path=root / "automate" / "flow.json",
        expect_rls=True,
    )

    assert result["engine_status"] == "PASS"
    assert result["project_status"] == "REVIEW"
    assert result["status"] == "REVIEW"
    assert result["canvas"]["potential_occlusion"] >= 1
    assert result["canvas"]["expected_layering"] >= 1
    assert result["canvas"]["bounds"] >= 1
    assert result["model"]["measures"] >= 4
    assert result["model"]["measures_without_hash"] == 0
    assert result["model"]["rls_present"] is True
    assert result["planner"]["apply"] is False
    assert result["planner"]["write_ready"] == 0
    assert result["power_automate"]["status"] == "PASS"
    assert result["runtime"]["seller_isolation"] == "NOT_RUN"


def test_flow_audit_detects_missing_steps_and_secret_without_exposing_value():
    flow = {
        "definition": {
            "actions": {
                "Payload_LLM": {"type": "Compose", "runAfter": {}},
                "Send_Email": {
                    "type": "OpenApiConnection",
                    "runAfter": {},
                    "inputs": {"client_secret": "do-not-return-this-value"},
                },
            }
        }
    }

    result = audit_flow_definition(flow)

    assert result["status"] == "REVIEW"
    assert result["secret_indicator_count"] == 1
    assert result["missing_required_steps"]
    serialized = json.dumps(result)
    assert "do-not-return-this-value" not in serialized
    assert any(item["kind"] == "EMBEDDED_SECRET_INDICATOR" for item in result["findings"])


def test_flow_loader_rejects_invalid_json(tmp_path: Path):
    path = tmp_path / "flow.json"
    path.write_text("not-json", encoding="utf-8")

    try:
        load_flow_export(path)
    except Exception as exc:
        assert "JSON" in str(exc)
    else:
        raise AssertionError("Expected invalid flow export to fail")
