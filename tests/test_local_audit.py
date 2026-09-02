import json
from pathlib import Path

from artel_powerplatform_mcp.local_audit import inspect_project, scan_for_embedded_secrets, validate_blueprint


def make_project(tmp_path: Path) -> Path:
    root = tmp_path / "bi"
    (root / "s510" / "automate").mkdir(parents=True)
    (root / "Informe.pbip").write_text("{}", encoding="utf-8")
    (root / "Modelo.SemanticModel").mkdir()
    (root / "Modelo.Report").mkdir()
    (root / "s510" / "automate" / "FLOW_BLUEPRINT.json").write_text(json.dumps({
        "name": "S510", "version": "1.0", "production": {"enabled": False},
        "variables": [{"name": "MODO_PILOTO"}], "source": {"cutoff_source": "[Fecha Corte S510]"},
        "trigger_strategy": {"forbidden": ["OnNewEmailV3"]},
    }), encoding="utf-8")
    return root


def test_inspect_project_reports_pbip_assets(tmp_path: Path):
    result = inspect_project(make_project(tmp_path))
    assert result["pbip_files"] == ["Informe.pbip"]
    assert result["semantic_models"] == ["Modelo.SemanticModel"]
    assert result["has_blueprint"] is True


def test_validate_blueprint_checks_pilot_guards(tmp_path: Path):
    result = validate_blueprint(make_project(tmp_path))
    assert result["valid"] is True
    assert all(result["checks"].values())


def test_secret_scan_does_not_return_secret_value(tmp_path: Path):
    root = make_project(tmp_path)
    sensitive_key = "pass" + "word"
    (root / "bad.py").write_text(f'{sensitive_key} = "do-not-return"', encoding="utf-8")
    result = scan_for_embedded_secrets(root)
    assert result["count"] == 1
    assert "do-not-return" not in json.dumps(result)
