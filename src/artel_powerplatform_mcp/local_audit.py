from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SECRET_PATTERNS = (
    re.compile(r'(?i)(password|client_secret|access_token|api[_-]?key)\s*[=:]\s*["\'][^"\']+["\']'),
    re.compile(r'(?i)Bearer\s+[A-Za-z0-9._-]{20,}'),
)


def inspect_project(project_path: Path) -> dict[str, Any]:
    if not project_path.is_dir():
        raise ValueError(f"No existe el directorio del proyecto: {project_path}")
    pbip = sorted(project_path.glob("*.pbip"))
    semantic = sorted(project_path.glob("*.SemanticModel"))
    report = sorted(project_path.glob("*.Report"))
    docs = sorted(project_path.glob("Docs/**/*.md"))
    dax = sorted(project_path.glob("**/*.dax"))
    return {
        "project_path": str(project_path),
        "pbip_files": [p.name for p in pbip],
        "semantic_models": [p.name for p in semantic],
        "reports": [p.name for p in report],
        "documentation_count": len(docs),
        "dax_query_count": len(dax),
        "dax_queries": [str(p.relative_to(project_path)) for p in dax[:100]],
        "has_blueprint": (project_path / "s510" / "automate" / "FLOW_BLUEPRINT.json").is_file(),
        "has_playbook": (project_path / "s510" / "automate" / "coordination" / "AUTONOMOUS_POWER_AUTOMATE_PLAYBOOK.md").is_file(),
    }


def validate_blueprint(project_path: Path) -> dict[str, Any]:
    blueprint_path = project_path / "s510" / "automate" / "FLOW_BLUEPRINT.json"
    if not blueprint_path.is_file():
        raise ValueError("No se encontró s510/automate/FLOW_BLUEPRINT.json.")
    blueprint = json.loads(blueprint_path.read_text(encoding="utf-8"))
    checks = {
        "production_disabled": blueprint.get("production", {}).get("enabled") is False,
        "pilot_mode_defined": any(v.get("name") == "MODO_PILOTO" for v in blueprint.get("variables", [])),
        "cutoff_defined": blueprint.get("source", {}).get("cutoff_source") == "[Fecha Corte S510]",
        "email_trigger_forbidden": any("OnNewEmailV3" in x for x in blueprint.get("trigger_strategy", {}).get("forbidden", [])),
    }
    return {"path": str(blueprint_path), "name": blueprint.get("name"), "version": blueprint.get("version"), "checks": checks, "valid": all(checks.values())}


def scan_for_embedded_secrets(project_path: Path, limit: int = 100) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    for path in project_path.rglob("*"):
        if not path.is_file() or path.suffix.lower() in {".zip", ".png", ".jpg", ".parquet", ".gz", ".exe"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append({"file": str(path.relative_to(project_path)), "pattern": pattern.pattern})
                break
        if len(findings) >= limit:
            break
    return {"count": len(findings), "findings": findings, "warning": "Revisar y rotar credenciales; no se modificaron archivos." if findings else None}
