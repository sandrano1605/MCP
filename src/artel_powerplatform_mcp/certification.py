from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from .flow_audit import DEFAULT_REQUIRED_STEPS, audit_flow_definition, load_flow_export
from .guards import evaluate_mutation
from .local_audit import inspect_project, scan_for_embedded_secrets
from .model_policy import assess_model_policy
from .pbir import inspect_pbir_parts, load_local_pbir_parts
from .planning import build_combined_plan
from .tmdl import inspect_tmdl_parts, load_local_tmdl_parts


def run_self_test() -> dict[str, Any]:
    """Ejecuta una certificación offline determinística usando un PBIP/flow temporal de laboratorio."""
    with tempfile.TemporaryDirectory(prefix="artel_mcp_cert_") as temp_dir:
        root = Path(temp_dir) / "ARTEL_Certification_Lab"
        _write_lab_project(root)

        inventory = inspect_project(root)
        _report, pbir_parts = load_local_pbir_parts(root)
        canvas = inspect_pbir_parts(pbir_parts, include_visuals=True, max_findings=100)
        _model, tmdl_parts = load_local_tmdl_parts(root)
        model = inspect_tmdl_parts(tmdl_parts, include_measures=True, include_columns=True, max_items=500)
        security = assess_model_policy(model, expect_rls=True)
        plan = build_combined_plan(model=model, canvas=canvas, expect_rls=True)
        flow = load_flow_export(root / "automate" / "flow.json")
        flow_audit = audit_flow_definition(flow)
        secret_scan = scan_for_embedded_secrets(root)

        no_rls_parts = {path: payload for path, payload in tmdl_parts.items() if "/roles/" not in f"/{path}"}
        no_rls_model = inspect_tmdl_parts(no_rls_parts, max_items=500)
        no_rls_security = assess_model_policy(no_rls_model, expect_rls=True)

        measures = [
            measure
            for table in model.get("tables", [])
            for measure in table.get("measures", [])
        ]
        checks = [
            _check("PROJECT_FIXTURE", inventory["pbip_files"] == ["Lab.pbip"] and len(inventory["reports"]) == 1 and len(inventory["semantic_models"]) == 1),
            _check("PBIR_PAGES", canvas.get("page_count") == 2),
            _check("PBIR_EXPECTED_LAYERING", int(canvas.get("expected_layering_count", 0)) >= 1),
            _check("PBIR_POTENTIAL_OCCLUSION", int(canvas.get("potential_occlusion_count", 0)) >= 1),
            _check("PBIR_BOUNDS_NEGATIVE_CASE", int(canvas.get("bounds_issue_count", 0)) >= 1),
            _check("PBIR_DUPLICATE_TAB_ORDER_NEGATIVE_CASE", int(canvas.get("duplicate_tab_order_count", 0)) >= 1),
            _check("TMDL_TABLES", int(model.get("table_count", 0)) == 2),
            _check("TMDL_TEST_MEASURES", int(model.get("measure_count", 0)) >= 4 and len(measures) >= 4),
            _check("DAX_MEASURE_HASHES", all(bool(item.get("expression_sha256")) for item in measures)),
            _check("RLS_POSITIVE_CASE", bool(model.get("rls_present")) and security.get("security_policy", {}).get("rls_posture") == "RLS_DECLARED"),
            _check("RLS_NEGATIVE_CASE_DETECTED", any(item.get("kind") == "RLS_REQUIRED_BUT_NOT_DECLARED" for item in no_rls_security.get("findings", []))),
            _check("BIDIRECTIONAL_RELATIONSHIP_DETECTED", any(item.get("kind") == "BIDIRECTIONAL_RELATIONSHIP" for item in model.get("findings", []))),
            _check("PLANNER_IS_DRY_RUN", plan.get("mode") == "DRY_RUN" and plan.get("apply") is False),
            _check("PLANNER_NO_WRITE_READY", int(plan.get("write_ready_count", -1)) == 0),
            _check("POWER_AUTOMATE_CONTRACT", flow_audit.get("status") == "PASS" and flow_audit.get("required_steps_present") == len(DEFAULT_REQUIRED_STEPS)),
            _check("POWER_AUTOMATE_NO_SECRET_LITERAL", int(flow_audit.get("secret_indicator_count", -1)) == 0),
            _check("SECRET_SCANNER_CLEAN_FIXTURE", int(secret_scan.get("count", -1)) == 0),
            _check("WRITE_GUARDS", _guard_contract_passes()),
        ]

        failed = [item for item in checks if item["status"] != "PASS"]
        return {
            "certification_version": "1.7-e2e",
            "mode": "OFFLINE_SELF_TEST",
            "temporary_fixture": True,
            "cloud_calls": 0,
            "writes": 0,
            "check_count": len(checks),
            "passed": len(checks) - len(failed),
            "failed": len(failed),
            "checks": checks,
            "fixture_summary": {
                "pages": canvas.get("page_count"),
                "visuals": canvas.get("visual_count"),
                "tables": model.get("table_count"),
                "columns": model.get("column_count"),
                "measures": model.get("measure_count"),
                "relationships": model.get("relationship_count"),
                "roles": model.get("role_count"),
                "flow_actions": flow_audit.get("action_count"),
            },
            "status": "PASS" if not failed else "FAIL",
        }


def certify_local_bi(
    project_path: Path,
    *,
    flow_path: Path | None = None,
    expect_rls: bool = False,
    max_findings: int = 100,
    report_name: str | None = None,
    semantic_model_name: str | None = None,
) -> dict[str, Any]:
    """Audita un PBIP real de punta a punta sin modificar archivos ni ejecutar cloud."""
    inventory = inspect_project(project_path)
    report_name, pbir_parts = load_local_pbir_parts(project_path, report_name=report_name)
    canvas = inspect_pbir_parts(pbir_parts, include_visuals=False, max_findings=max_findings)
    model_name, tmdl_parts = load_local_tmdl_parts(project_path, semantic_model_name=semantic_model_name)
    model = inspect_tmdl_parts(tmdl_parts, include_measures=True, include_columns=False, max_items=5000)
    security = assess_model_policy(model, expect_rls=expect_rls)
    plan = build_combined_plan(model=model, canvas=canvas, expect_rls=expect_rls)
    secret_scan = scan_for_embedded_secrets(project_path, limit=200)
    flow_audit = audit_flow_definition(load_flow_export(flow_path)) if flow_path else None

    measures = [
        measure
        for table in model.get("tables", [])
        for measure in table.get("measures", [])
    ]
    measures_with_hash = sum(1 for item in measures if item.get("expression_sha256"))
    measures_without_hash = len(measures) - measures_with_hash

    engine_checks = [
        _check("PROJECT_STRUCTURE", bool(inventory.get("pbip_files")) and bool(inventory.get("reports")) and bool(inventory.get("semantic_models"))),
        _check("PBIR_PARSE", int(canvas.get("page_count", 0)) > 0),
        _check("TMDL_PARSE", int(model.get("table_count", 0)) > 0),
        _check("MEASURE_EXTRACTION", int(model.get("measure_count", 0)) == len(measures)),
        _check("MEASURE_HASHING", measures_without_hash == 0),
        _check("PLANNER_SAFETY", plan.get("apply") is False and int(plan.get("write_ready_count", -1)) == 0),
        _check("WRITE_GUARDS", _guard_contract_passes()),
    ]
    if flow_audit is not None:
        engine_checks.append(_check("POWER_AUTOMATE_EXPORT_PARSE", int(flow_audit.get("action_count", 0)) > 0))

    engine_failed = [item for item in engine_checks if item["status"] != "PASS"]
    project_findings: list[dict[str, Any]] = []
    project_findings.extend(security.get("findings", []))
    for page in canvas.get("pages", []):
        page_name = page.get("display_name") or page.get("name") or page.get("page_key")
        for finding in page.get("findings", []):
            if finding.get("requires_review", True):
                project_findings.append({"domain": "CANVAS", "page": page_name, **finding})
    if secret_scan.get("count"):
        project_findings.append(
            {
                "domain": "SECURITY",
                "kind": "EMBEDDED_SECRET_INDICATORS",
                "severity": "HIGH",
                "count": secret_scan.get("count"),
            }
        )
    if flow_audit:
        project_findings.extend({"domain": "POWER_AUTOMATE", **item} for item in flow_audit.get("findings", []))

    engine_status = "PASS" if not engine_failed else "FAIL"
    project_status = "REVIEW" if project_findings else "PASS"
    overall = "FAIL" if engine_status == "FAIL" else ("REVIEW" if project_status == "REVIEW" else "PASS")

    return {
        "certification_version": "1.7-e2e",
        "mode": "LOCAL_READ_ONLY_CERTIFICATION",
        "cloud_calls": 0,
        "writes": 0,
        "engine_status": engine_status,
        "project_status": project_status,
        "status": overall,
        "engine_checks": engine_checks,
        "inventory": {
            "project_name": inventory.get("project_name"),
            "pbip_files": inventory.get("pbip_files"),
            "report": report_name,
            "semantic_model": model_name,
            "tmdl_files": inventory.get("tmdl_file_count"),
            "pages_inventory": inventory.get("report_page_count"),
            "visuals_inventory": inventory.get("report_visual_count"),
        },
        "canvas": {
            "pages": canvas.get("page_count"),
            "visuals": canvas.get("visual_count"),
            "review_findings": canvas.get("review_finding_count"),
            "bounds": canvas.get("bounds_issue_count"),
            "review_overlaps": canvas.get("review_overlap_count"),
            "expected_layering": canvas.get("expected_layering_count"),
            "potential_occlusion": canvas.get("potential_occlusion_count"),
            "content_overlay": canvas.get("content_overlay_count"),
            "alignment": canvas.get("alignment_drift_count"),
            "duplicate_tab_order": canvas.get("duplicate_tab_order_count"),
        },
        "model": {
            "tables": model.get("table_count"),
            "columns": model.get("column_count"),
            "measures": model.get("measure_count"),
            "measures_hashed": measures_with_hash,
            "measures_without_hash": measures_without_hash,
            "partitions": model.get("partition_count"),
            "relationships": model.get("relationship_count"),
            "roles": model.get("role_count"),
            "table_permissions": model.get("table_permission_count"),
            "rls_present": model.get("rls_present"),
            "semantic_runtime_validated": model.get("semantic_runtime_validated"),
        },
        "security_policy": security.get("security_policy"),
        "relationship_policy": security.get("relationship_policy"),
        "planner": {
            "mode": plan.get("mode"),
            "apply": plan.get("apply"),
            "actions": plan.get("action_count"),
            "write_ready": plan.get("write_ready_count"),
            "blocked": plan.get("blocked_action_count"),
            "runtime_validation_required": plan.get("runtime_validation_required"),
        },
        "secret_scan": {
            "count": secret_scan.get("count"),
            "truncated": secret_scan.get("truncated"),
            "findings": secret_scan.get("findings", []),
        },
        "power_automate": flow_audit,
        "project_findings": project_findings[:max_findings],
        "project_findings_truncated": len(project_findings) > max_findings,
        "runtime": {
            "power_bi_semantic": "NOT_RUN",
            "seller_isolation": "NOT_RUN",
            "power_automate": "NOT_RUN",
            "fabric": "NOT_RUN",
        },
    }


def _guard_contract_passes() -> bool:
    get_read = evaluate_mutation("GET", dry_run=True, confirm=False, allow_writes=False)
    post_dry = evaluate_mutation("POST", dry_run=True, confirm=True, allow_writes=True)
    patch_no_confirm = evaluate_mutation("PATCH", dry_run=False, confirm=False, allow_writes=True)
    put_disabled = evaluate_mutation("PUT", dry_run=False, confirm=True, allow_writes=False)
    delete = evaluate_mutation("DELETE", dry_run=False, confirm=True, allow_writes=True)
    explicit_write = evaluate_mutation("POST", dry_run=False, confirm=True, allow_writes=True)
    return (
        get_read.allowed
        and not post_dry.allowed
        and not patch_no_confirm.allowed
        and not put_disabled.allowed
        and not delete.allowed
        and explicit_write.allowed
    )


def _check(name: str, condition: bool) -> dict[str, str]:
    return {"check": name, "status": "PASS" if condition else "FAIL"}


def _write_lab_project(root: Path) -> None:
    (root / "Lab.Report" / "definition" / "pages" / "Clean" / "visuals").mkdir(parents=True, exist_ok=True)
    (root / "Lab.Report" / "definition" / "pages" / "Faults" / "visuals").mkdir(parents=True, exist_ok=True)
    (root / "Lab.SemanticModel" / "definition" / "tables").mkdir(parents=True, exist_ok=True)
    (root / "Lab.SemanticModel" / "definition" / "roles").mkdir(parents=True, exist_ok=True)
    (root / "automate").mkdir(parents=True, exist_ok=True)
    (root / "Lab.pbip").write_text("{}", encoding="utf-8")

    _write_json(root / "Lab.Report" / "definition" / "pages" / "Clean" / "page.json", {
        "name": "Clean",
        "displayName": "Clean Canvas",
        "width": 1280,
        "height": 720,
    })
    _write_visual(root, "Clean", "bg", "Background", "shape", 40, 40, 240, 120, 0, 0)
    _write_visual(root, "Clean", "card", "SalesCard", "cardVisual", 40, 40, 240, 120, 1000, 1)
    _write_visual(root, "Clean", "card2", "MarginCard", "cardVisual", 320, 40, 240, 120, 1000, 2)

    _write_json(root / "Lab.Report" / "definition" / "pages" / "Faults" / "page.json", {
        "name": "Faults",
        "displayName": "Intentional Faults",
        "width": 1280,
        "height": 720,
    })
    _write_visual(root, "Faults", "text", "StatusText", "textbox", 40, 40, 220, 80, 1000, 1)
    _write_visual(root, "Faults", "cover", "CoverShape", "shape", 40, 40, 220, 80, 3000, 2)
    _write_visual(root, "Faults", "outside", "OutsideCard", "cardVisual", 1210, 650, 180, 120, 1000, 3)
    _write_visual(root, "Faults", "dup", "DuplicateTabOrder", "cardVisual", 400, 200, 180, 80, 1000, 3)

    sales_tmdl = """table Sales
    column SellerKey
        dataType: string
        sourceColumn: SellerKey
    column SellerUPN
        dataType: string
        sourceColumn: SellerUPN
    column Amount
        dataType: double
        sourceColumn: Amount
    column Cost
        dataType: double
        sourceColumn: Cost
    measure 'Total Sales' = SUM(Sales[Amount])
    measure 'Total Cost' = SUM(Sales[Cost])
    measure 'Margin' = [Total Sales] - [Total Cost]
    measure 'Margin %' = DIVIDE([Margin], [Total Sales])
    partition Sales-Part = m
        mode: import
        source = 1
"""
    seller_tmdl = """table DimSeller
    column SellerKey
        dataType: string
        isKey
        sourceColumn: SellerKey
    column SellerUPN
        dataType: string
        sourceColumn: SellerUPN
    partition Seller-Part = m
        mode: import
        source = 1
"""
    relationships = """relationship rel-sales-seller
    fromColumn: Sales.SellerKey
    toColumn: DimSeller.SellerKey
    crossFilteringBehavior: bothDirections
"""
    role = """role Seller
    modelPermission: read
    tablePermission Sales = Sales[SellerUPN] = USERPRINCIPALNAME()
"""
    (root / "Lab.SemanticModel" / "definition" / "tables" / "Sales.tmdl").write_text(sales_tmdl, encoding="utf-8")
    (root / "Lab.SemanticModel" / "definition" / "tables" / "DimSeller.tmdl").write_text(seller_tmdl, encoding="utf-8")
    (root / "Lab.SemanticModel" / "definition" / "relationships.tmdl").write_text(relationships, encoding="utf-8")
    (root / "Lab.SemanticModel" / "definition" / "roles" / "Seller.tmdl").write_text(role, encoding="utf-8")
    (root / "Lab.SemanticModel" / "definition" / "model.tmdl").write_text("model Model\nref table Sales\nref table DimSeller\nref role Seller\n", encoding="utf-8")

    flow = {
        "definition": {
            "triggers": {"manual": {"type": "Request"}},
            "actions": {
                "Payload_LLM": {"type": "Compose", "runAfter": {}},
                "LLM_Adapter": {"type": "Http", "runAfter": {"Payload_LLM": ["Succeeded"]}},
                "Parse_JSON_LLM": {"type": "ParseJson", "runAfter": {"LLM_Adapter": ["Succeeded"]}},
                "Semantic_Grounding_Gate": {"type": "If", "runAfter": {"Parse_JSON_LLM": ["Succeeded"]}},
                "InsightFinal": {"type": "Compose", "runAfter": {"Semantic_Grounding_Gate": ["Succeeded"]}},
                "HTML_Email_Final": {"type": "Compose", "runAfter": {"InsightFinal": ["Succeeded"]}},
                "Send_Email": {"type": "OpenApiConnection", "runAfter": {"HTML_Email_Final": ["Succeeded"]}},
            },
        }
    }
    _write_json(root / "automate" / "flow.json", flow)


def _write_visual(
    root: Path,
    page: str,
    folder: str,
    name: str,
    visual_type: str,
    x: float,
    y: float,
    width: float,
    height: float,
    z: float,
    tab_order: float,
) -> None:
    path = root / "Lab.Report" / "definition" / "pages" / page / "visuals" / folder
    path.mkdir(parents=True, exist_ok=True)
    _write_json(path / "visual.json", {
        "name": name,
        "position": {"x": x, "y": y, "width": width, "height": height, "z": z, "tabOrder": tab_order},
        "visual": {"visualType": visual_type},
    })


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
