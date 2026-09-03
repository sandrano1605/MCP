import base64
import json
from pathlib import Path

from artel_powerplatform_mcp.pbir import (
    inspect_pbir_definition,
    inspect_pbir_parts,
    load_local_pbir_parts,
)


def _json_bytes(data: dict) -> bytes:
    return json.dumps(data).encode("utf-8")


def _visual(
    name: str,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    visual_type: str = "card",
    parent_group: str | None = None,
    is_group: bool = False,
    is_hidden: bool = False,
    tab_order: int | None = None,
    z: int | None = None,
) -> dict:
    result = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/1.1.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "width": width, "height": height},
    }
    if tab_order is not None:
        result["position"]["tabOrder"] = tab_order
    if z is not None:
        result["position"]["z"] = z
    if is_group:
        result["visualGroup"] = {}
    else:
        result["visual"] = {"visualType": visual_type}
    if parent_group:
        result["parentGroupName"] = parent_group
    if is_hidden:
        result["isHidden"] = True
    return result


def _parts(*visuals: tuple[str, dict], width: int = 300, height: int = 200, page: str = "page1") -> dict[str, bytes]:
    parts = {
        f"definition/pages/{page}/page.json": _json_bytes(
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/1.0.0/schema.json",
                "name": page,
                "displayName": "Resumen" if page == "page1" else page,
                "displayOption": "FitToPage",
                "width": width,
                "height": height,
            }
        )
    }
    for folder, visual in visuals:
        parts[f"definition/pages/{page}/visuals/{folder}/visual.json"] = _json_bytes(visual)
    return parts


def test_clean_canvas_passes_and_summarizes_spacing():
    parts = _parts(
        ("a", _visual("a", 10, 10, 100, 80, tab_order=1)),
        ("b", _visual("b", 120, 10, 100, 80, tab_order=2)),
    )
    result = inspect_pbir_parts(parts)
    assert result["status"] == "PASS"
    assert result["scope"] == "ACTIVE_REPORT_DEFINITION"
    assert result["page_count"] == 1
    assert result["visual_count"] == 2
    assert result["analyzed_visual_count"] == 2
    page = result["pages"][0]
    assert page["overlap_count"] == 0
    assert page["bounds_issue_count"] == 0
    assert page["spacing"]["common_horizontal_gaps"] == [{"gap": 10.0, "count": 1}]
    assert "visuals" not in page


def test_canvas_detects_partial_overlap_out_of_bounds_and_duplicate_tab_order():
    parts = _parts(
        ("a", _visual("a", 10, 10, 100, 80, tab_order=1, z=1)),
        ("b", _visual("b", 90, 10, 100, 80, tab_order=1, z=2)),
        ("c", _visual("c", 250, 110, 100, 80, tab_order=3, z=3)),
    )
    result = inspect_pbir_parts(parts, include_visuals=True)
    assert result["status"] == "REVIEW"
    page = result["pages"][0]
    assert page["overlap_count"] >= 1
    assert page["review_overlap_count"] >= 1
    assert page["bounds_issue_count"] == 1
    assert page["duplicate_tab_order_count"] == 1
    assert len(page["visuals"]) == 3
    overlap = next(f for f in page["findings"] if f["kind"] == "OVERLAP")
    assert overlap["classification"] == "GENERIC_OVERLAP"
    assert overlap["requires_review"] is True
    kinds = {finding["kind"] for finding in page["findings"]}
    assert {"OVERLAP", "BOUNDS", "DUPLICATE_TAB_ORDER"} <= kinds


def test_group_container_overlap_is_not_reported_as_problem():
    parts = _parts(
        ("group", _visual("group1", 0, 0, 220, 180, is_group=True)),
        ("child", _visual("child1", 10, 10, 100, 80, parent_group="group1")),
    )
    result = inspect_pbir_parts(parts)
    assert result["pages"][0]["overlap_count"] == 0


def test_hidden_visuals_are_counted_but_excluded_from_analysis_by_default():
    parts = _parts(
        ("visible", _visual("visible", 10, 10, 100, 80)),
        ("hidden", _visual("hidden", 10, 10, 100, 80, is_hidden=True)),
    )
    result = inspect_pbir_parts(parts)
    assert result["visual_count"] == 2
    assert result["analyzed_visual_count"] == 1
    assert result["hidden_visual_count"] == 1
    assert result["overlap_count"] == 0
    assert result["hidden_visuals_included_in_analysis"] is False

    with_hidden = inspect_pbir_parts(parts, include_hidden=True)
    assert with_hidden["analyzed_visual_count"] == 2
    assert with_hidden["overlap_count"] == 1


def test_shape_below_content_is_expected_layering_and_does_not_fail_canvas():
    parts = _parts(
        ("background", _visual("background", 10, 10, 120, 100, visual_type="shape", z=1)),
        ("card", _visual("card", 20, 20, 60, 40, visual_type="card", z=2)),
    )
    result = inspect_pbir_parts(parts)
    overlap = next(f for f in result["pages"][0]["findings"] if f["kind"] == "OVERLAP")
    assert overlap["coverage_pattern"] == "FULL_COVERAGE"
    assert overlap["classification"] == "EXPECTED_LAYERING"
    assert overlap["severity"] == "INFO"
    assert overlap["requires_review"] is False
    assert overlap["layering_candidate"] is True
    assert overlap["lower_z_visual"] == "background"
    assert overlap["upper_z_visual"] == "card"
    assert overlap["lower_z_visual_type"] == "shape"
    assert result["expected_layering_count"] == 1
    assert result["review_overlap_count"] == 0
    assert result["status"] == "PASS"


def test_shape_above_textbox_is_potential_occlusion():
    parts = _parts(
        ("text", _visual("text", 10, 10, 100, 80, visual_type="textbox", z=1)),
        ("shape", _visual("shape", 10, 10, 100, 80, visual_type="shape", z=5)),
    )
    result = inspect_pbir_parts(parts)
    overlap = next(f for f in result["pages"][0]["findings"] if f["kind"] == "OVERLAP")
    assert overlap["classification"] == "POTENTIAL_OCCLUSION"
    assert overlap["severity"] == "HIGH"
    assert overlap["requires_review"] is True
    assert overlap["upper_z_visual_type"] == "shape"
    assert result["potential_occlusion_count"] == 1
    assert result["review_overlap_count"] == 1
    assert result["status"] == "REVIEW"


def test_textbox_above_card_is_content_overlay():
    parts = _parts(
        ("card", _visual("card", 10, 10, 100, 80, visual_type="cardVisual", z=4)),
        ("text", _visual("text", 10, 10, 100, 80, visual_type="textbox", z=7)),
    )
    result = inspect_pbir_parts(parts)
    overlap = next(f for f in result["pages"][0]["findings"] if f["kind"] == "OVERLAP")
    assert overlap["classification"] == "CONTENT_OVERLAY"
    assert overlap["severity"] == "MEDIUM"
    assert overlap["requires_review"] is True
    assert result["content_overlay_count"] == 1
    assert result["status"] == "REVIEW"


def test_near_alignment_drift_is_reported_with_visual_context():
    parts = _parts(
        ("a", _visual("a", 10, 10, 80, 50, visual_type="card", z=1)),
        ("b", _visual("b", 12, 100, 80, 50, visual_type="table", z=2)),
    )
    result = inspect_pbir_parts(parts, alignment_tolerance=3)
    page = result["pages"][0]
    assert page["overlap_count"] == 0
    assert page["alignment_drift_count"] >= 1
    drift = next(f for f in page["findings"] if f["kind"] == "ALIGNMENT_DRIFT" and f["edge"] == "left")
    assert drift["visual_a_type"] == "card"
    assert drift["visual_b_type"] == "table"
    assert drift["delta"] == 2.0


def test_alignment_drift_is_not_double_counted_inside_overlap():
    parts = _parts(
        ("text", _visual("text", 10, 10, 100, 80, visual_type="textbox", z=1)),
        ("shape", _visual("shape", 13, 10, 100, 80, visual_type="shape", z=5)),
    )
    result = inspect_pbir_parts(parts, alignment_tolerance=3)
    page = result["pages"][0]
    assert page["overlap_count"] == 1
    assert page["alignment_drift_count"] == 0


def test_findings_budget_is_global_across_pages():
    parts = {}
    parts.update(_parts(
        ("a", _visual("a", 0, 0, 100, 100)),
        ("b", _visual("b", 0, 0, 100, 100)),
        page="page1",
    ))
    parts.update(_parts(
        ("c", _visual("c", 0, 0, 100, 100)),
        ("d", _visual("d", 0, 0, 100, 100)),
        page="page2",
    ))
    result = inspect_pbir_parts(parts, max_findings=1)
    emitted = sum(len(page["findings"]) for page in result["pages"])
    assert result["finding_count"] >= 2
    assert emitted == 1
    assert result["findings_emitted"] == 1
    assert result["findings_truncated"] is True


def test_fabric_definition_is_decoded_and_inspected_internally():
    parts = _parts(("a", _visual("a", 10, 10, 100, 80)))
    response = {
        "definition": {
            "format": "PBIR",
            "parts": [
                {
                    "path": path,
                    "payloadType": "InlineBase64",
                    "payload": base64.b64encode(content).decode("ascii").rstrip("="),
                }
                for path, content in parts.items()
            ],
        }
    }
    result = inspect_pbir_definition(response)
    assert result["status"] == "PASS"
    assert result["pages"][0]["display_name"] == "Resumen"


def test_local_loader_returns_relative_report_name_and_parts(tmp_path: Path):
    project = tmp_path / "project"
    report = project / "Demo.Report"
    page_dir = report / "definition" / "pages" / "page1"
    visual_dir = page_dir / "visuals" / "a"
    visual_dir.mkdir(parents=True)
    (page_dir / "page.json").write_bytes(_parts()["definition/pages/page1/page.json"])
    (visual_dir / "visual.json").write_bytes(_json_bytes(_visual("a", 10, 10, 100, 80)))
    report_name, parts = load_local_pbir_parts(project)
    assert report_name == "Demo.Report"
    assert "definition/pages/page1/page.json" in parts
    assert "definition/pages/page1/visuals/a/visual.json" in parts
