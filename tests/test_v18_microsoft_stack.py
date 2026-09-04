from artel_powerplatform_mcp.microsoft_stack import (
    choose_evidence_source,
    route_work,
    stack_manifest,
    validate_layout_contract,
)


def test_power_automate_remains_independent_artel_engine():
    result = route_work("power_automate")
    keys = [item["key"] for item in result["components"]]
    assert keys == ["artel-power-automate-engine", "artel-evidence-governance"]
    assert result["power_automate_is_independent_engine"] is True


def test_certification_route_combines_microsoft_and_artel_components():
    result = route_work("certify")
    keys = [item["key"] for item in result["components"]]
    assert "powerbi-modeling-mcp" in keys
    assert "powerbi-remote-mcp" in keys
    assert "powerbi-report-authoring" in keys
    assert "artel-power-automate-engine" in keys
    assert "artel-evidence-governance" in keys


def test_writes_default_to_disabled():
    result = route_work("semantic_model")
    assert result["write_policy"]["effective"] is False
    assert all(item["writes_allowed"] is False for item in result["components"])


def test_evidence_prefers_runtime_over_static():
    result = choose_evidence_source(
        {
            "local_pbip_tmdl": True,
            "runtime_remote_powerbi_mcp": True,
            "static_review": True,
        }
    )
    assert result["source"] == "runtime_remote_powerbi_mcp"


def test_layout_contract_passes_non_overlapping_placements():
    result = validate_layout_contract(
        {
            "canvas": {"width": 1920, "height": 1080},
            "placements": [
                {"id": "title", "position": {"x": 32, "y": 24, "width": 800, "height": 64}},
                {"id": "chart", "position": {"x": 32, "y": 120, "width": 1200, "height": 600}},
            ],
        }
    )
    assert result["status"] == "PASS"
    assert result["finding_count"] == 0


def test_layout_contract_detects_overlap_and_bounds():
    result = validate_layout_contract(
        {
            "canvas": {"width": 100, "height": 100},
            "placements": [
                {"id": "a", "position": {"x": 10, "y": 10, "width": 70, "height": 70}},
                {"id": "b", "position": {"x": 50, "y": 50, "width": 70, "height": 70}},
            ],
        }
    )
    codes = {item["code"] for item in result["findings"]}
    assert result["status"] == "REVIEW"
    assert "UNDECLARED_OVERLAP" in codes
    assert "OUT_OF_BOUNDS" in codes


def test_stack_manifest_keeps_microsoft_as_upstream_dependency():
    manifest = stack_manifest()
    assert manifest["contract_version"] == "1.8-microsoft-skills"
    assert manifest["architecture"]["artel_role"] == "orchestrator_governor_evidence"
    assert manifest["architecture"]["power_automate_role"] == "independent_artel_engine"
    assert manifest["writes_default"] is False
