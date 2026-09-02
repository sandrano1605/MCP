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
    tab_order: int | None = None,
) -> dict:
    result = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/1.1.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "width": width, "height": height},
    }
    if tab_order is not None:
        result["position"]["tabOrder"] = tab_order
    if is_group:
        result["visualGroup"] = {}
    else:
        result["visual"] = {"visualType": visual_type}
    if parent_group:
        result["parentGroupName"] = parent_group
    return result


def _parts(*visuals: tuple[str, dict], width: int = 300, height: int = 200) -> dict[str, bytes]:
    parts = {
        "definition/pages/page1/page.json": _json_bytes(
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/1.0.0/schema.json",
                "name": "page1",
                "displayName": "Resumen",
                "displayOption": "FitToPage",
                "width": width,
                "height": height,
            }
        )
    }
    for folder, visual in visuals:
        parts[f"definition/pages/page1/visuals/{folder}/visual.json"] = _json_bytes(visual)
    return parts


def test_clean_canvas_passes_and_summarizes_spacing():
    parts = _parts(
        ("a", _visual("a", 10, 10, 100, 80, tab_order=1)),
        ("b", _visual("b", 120, 10, 100, 80, tab_order=2)),
    )

    result = inspect_pbir_parts(parts)

    assert result["status"] == "PASS"
    assert result["page_count"] == 1
    assert result["visual_count"] == 2
    page = result["pages"][0]
    assert page["overlap_count"] == 0
    assert page["bounds_issue_count"] == 0
    assert page["spacing"]["common_horizontal_gaps"] == [{"gap": 10.0, "count": 1}]
    assert "visuals" not in page


def test_canvas_detects_overlap_out_of_bounds_and_duplicate_tab_order():
    parts = _parts(
        ("a", _visual("a", 10, 10, 100, 80, tab_order=1)),
        ("b", _visual("b", 90, 10, 100, 80, tab_order=1)),
        ("c", _visual("c", 250, 110, 100, 80, tab_order=3)),
    )

    result = inspect_pbir_parts(parts, include_visuals=True)

    assert result["status"] == "REVIEW"
    page = result["pages"][0]
    assert page["overlap_count"] >= 1
    assert page["bounds_issue_count"] == 1
    assert page["duplicate_tab_order_count"] == 1
    assert len(page["visuals"]) == 3
    kinds = {finding["kind"] for finding in page["findings"]}
    assert {"OVERLAP", "BOUNDS", "DUPLICATE_TAB_ORDER"} <= kinds


def test_group_container_overlap_is_not_reported_as_problem():
    parts = _parts(
        ("group", _visual("group1", 0, 0, 220, 180, is_group=True)),
        ("child", _visual("child1", 10, 10, 100, 80, parent_group="group1")),
    )

    result = inspect_pbir_parts(parts)

    assert result["pages"][0]["overlap_count"] == 0


def test_near_alignment_drift_is_reported_without_overlap():
    parts = _parts(
        ("a", _visual("a", 10, 10, 80, 50)),
        ("b", _visual("b", 12, 100, 80, 50)),
    )

    result = inspect_pbir_parts(parts, alignment_tolerance=3)

    page = result["pages"][0]
    assert page["overlap_count"] == 0
    assert page["alignment_drift_count"] >= 1
    assert any(
        finding["kind"] == "ALIGNMENT_DRIFT" and finding["edge"] == "left"
        for finding in page["findings"]
    )


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
