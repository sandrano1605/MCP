from artel_powerplatform_mcp.model_policy import assess_model_policy


def _model(*, rls_present: bool = False, cross_filter: str | None = None, cardinality_explicit: bool = False):
    return {
        "format": "TMDL",
        "scope": "ACTIVE_SEMANTIC_MODEL_DEFINITION",
        "analysis_mode": "STATIC_TMDL",
        "semantic_runtime_validated": False,
        "rls_present": rls_present,
        "rls_secured_tables": ["Sales"] if rls_present else [],
        "relationships": [
            {
                "name": "rel1",
                "cross_filtering_behavior": cross_filter,
                "cardinality_explicit": cardinality_explicit,
            }
        ],
        "findings": [],
        "finding_count": 0,
        "status": "PASS",
    }


def test_absent_rls_is_not_failure_when_not_required():
    result = assess_model_policy(_model(), expect_rls=False)
    assert result["security_policy"]["rls_posture"] == "NO_RLS_DECLARED"
    assert result["security_policy"]["rls_expectation"] == "NOT_REQUIRED_BY_POLICY"
    assert not any(item["kind"] == "RLS_REQUIRED_BUT_NOT_DECLARED" for item in result["findings"])
    assert result["status"] == "PASS"
    assert result["semantic_runtime_validated"] is False


def test_missing_rls_is_high_when_consumer_requires_isolation():
    result = assess_model_policy(_model(), expect_rls=True)
    finding = next(item for item in result["findings"] if item["kind"] == "RLS_REQUIRED_BUT_NOT_DECLARED")
    assert finding["severity"] == "HIGH"
    assert finding["requires_review"] is True
    assert result["status"] == "REVIEW"
    assert result["security_policy"]["runtime_certification_required"] is True


def test_declared_rls_still_requires_runtime_certification():
    result = assess_model_policy(_model(rls_present=True), expect_rls=True)
    assert result["security_policy"]["rls_posture"] == "RLS_DECLARED"
    assert result["security_policy"]["runtime_certification_required"] is True
    assert result["semantic_runtime_validated"] is False
    assert not any(item["kind"] == "RLS_REQUIRED_BUT_NOT_DECLARED" for item in result["findings"])


def test_relationship_policy_reports_bidirectional_and_missing_explicit_cardinality():
    result = assess_model_policy(_model(cross_filter="bothDirections", cardinality_explicit=False))
    policy = result["relationship_policy"]
    assert policy["bidirectional_count"] == 1
    assert policy["bidirectional_relationships"] == ["rel1"]
    assert policy["cardinality_not_explicit_count"] == 1
    assert policy["effective_cardinality_inferred"] is False


def test_policy_preserves_existing_findings():
    model = _model()
    model["findings"] = [{"kind": "BIDIRECTIONAL_RELATIONSHIP", "severity": "MEDIUM", "requires_review": True}]
    result = assess_model_policy(model)
    assert result["finding_count"] == 1
    assert result["status"] == "REVIEW"
