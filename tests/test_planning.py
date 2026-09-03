from artel_powerplatform_mcp.planning import build_canvas_plan, build_combined_plan, build_model_plan


def test_model_plan_requires_rls_design_when_isolation_expected():
    model = {
        "scope": "ACTIVE_SEMANTIC_MODEL_DEFINITION",
        "rls_present": False,
        "rls_secured_tables": [],
        "relationships": [],
        "findings": [],
        "status": "PASS",
    }
    plan = build_model_plan(model, expect_rls=True)
    assert plan["mode"] == "DRY_RUN"
    assert plan["apply"] is False
    assert plan["action_count"] == 1
    assert plan["actions"][0]["action"] == "DESIGN_RLS_POLICY"
    assert plan["actions"][0]["write_ready"] is False


def test_model_plan_never_auto_changes_bidirectional_relationship():
    model = {
        "scope": "ACTIVE_SEMANTIC_MODEL_DEFINITION",
        "rls_present": False,
        "rls_secured_tables": [],
        "relationships": [
            {"name": "rel", "cross_filtering_behavior": "bothDirections", "cardinality_explicit": False}
        ],
        "findings": [
            {
                "kind": "BIDIRECTIONAL_RELATIONSHIP",
                "severity": "MEDIUM",
                "requires_review": True,
                "relationship": "rel",
            }
        ],
        "status": "REVIEW",
    }
    plan = build_model_plan(model)
    action = plan["actions"][0]
    assert action["action"] == "REVIEW_CROSS_FILTER_DIRECTION"
    assert action["write_ready"] is False
    assert plan["checkpoint_required_before_apply"] is True


def test_canvas_plan_ignores_expected_layering_but_keeps_occlusion():
    canvas = {
        "scope": "ACTIVE_REPORT_DEFINITION",
        "pages": [
            {
                "display_name": "Page",
                "findings": [
                    {
                        "kind": "OVERLAP",
                        "overlap_class": "EXPECTED_LAYERING",
                        "severity": "INFO",
                        "visual_a": "background",
                        "visual_b": "button",
                    },
                    {
                        "kind": "OVERLAP",
                        "overlap_class": "POTENTIAL_OCCLUSION",
                        "severity": "HIGH",
                        "visual_a": "shape",
                        "visual_b": "textbox",
                    },
                ],
            }
        ],
    }
    plan = build_canvas_plan(canvas)
    assert plan["action_count"] == 1
    assert plan["actions"][0]["action"] == "REVIEW_Z_ORDER"
    assert plan["actions"][0]["priority"] == "HIGH"


def test_combined_plan_is_dry_run_and_aggregates_domains():
    model = {
        "scope": "ACTIVE_SEMANTIC_MODEL_DEFINITION",
        "rls_present": False,
        "rls_secured_tables": [],
        "relationships": [],
        "findings": [],
        "status": "PASS",
    }
    canvas = {"scope": "ACTIVE_REPORT_DEFINITION", "pages": []}
    plan = build_combined_plan(model=model, canvas=canvas)
    assert plan["apply"] is False
    assert plan["domains"] == ["TMDL_MODEL", "PBIR_CANVAS"]
    assert plan["action_count"] == 0
    assert plan["status"] == "PASS"
