from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    ".deps",
    ".uv-cache",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
}

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("credential_assignment", re.compile(r"(?i)\b(password|passwd|pwd|client_secret|access_token|refresh_token|api[_-]?key)\b\s*[=:]\s*[^\s,;]+")),
    ("bearer_token", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{20,}")),
    ("connection_string_password", re.compile(r"(?i)\b(?:Password|Pwd)\s*=\s*[^;\r\n]+")),
)

TEXT_SUFFIXES = {
    ".py",
    ".json",
    ".md",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
    ".xml",
    ".ps1",
    ".sh",
    ".sql",
    ".dax",
    ".tmdl",
    ".pbip",
    ".pbir",
    ".ini",
    ".cfg",
    ".conf",
    ".properties",
}


def _iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            yield path


def _is_text_candidate(path: Path) -> bool:
    name = path.name.lower()
    return path.suffix.lower() in TEXT_SUFFIXES or name == ".env" or name.startswith(".env.")


def inspect_project(project_path: Path) -> dict[str, Any]:
    """Inventaría activos PBIP/TMDL/PBIR sin modificar el proyecto."""

    if not project_path.is_dir():
        raise ValueError(f"No existe el directorio del proyecto: {project_path}")

    pbip = sorted(project_path.glob("*.pbip"))
    semantic = sorted(project_path.glob("*.SemanticModel"))
    report = sorted(project_path.glob("*.Report"))
    docs = sorted(project_path.glob("Docs/**/*.md"))
    dax = sorted(project_path.glob("**/*.dax"))
    tmdl = sorted(project_path.glob("**/*.tmdl"))
    visual_json = sorted(project_path.glob("**/visual.json"))
    page_json = sorted(project_path.glob("**/page.json"))
    pbir = sorted(project_path.glob("**/*.pbir"))

    return {
        "project_name": project_path.name,
        "pbip_files": [p.name for p in pbip],
        "semantic_models": [p.name for p in semantic],
        "reports": [p.name for p in report],
        "documentation_count": len(docs),
        "dax_query_count": len(dax),
        "dax_queries": [str(p.relative_to(project_path)) for p in dax[:100]],
        "tmdl_file_count": len(tmdl),
        "tmdl_files": [str(p.relative_to(project_path)) for p in tmdl[:200]],
        "pbir_file_count": len(pbir),
        "report_page_count": len(page_json),
        "report_visual_count": len(visual_json),
        "report_pages": [str(p.parent.relative_to(project_path)) for p in page_json[:100]],
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
        "email_trigger_forbidden": any(
            "OnNewEmailV3" in x for x in blueprint.get("trigger_strategy", {}).get("forbidden", [])
        ),
    }
    return {
        "name": blueprint.get("name"),
        "version": blueprint.get("version"),
        "checks": checks,
        "valid": all(checks.values()),
    }


def scan_for_embedded_secrets(
    project_path: Path,
    limit: int = 100,
    max_file_bytes: int = 2_000_000,
) -> dict[str, Any]:
    """Busca indicadores de secretos sin devolver el valor coincidente."""

    if not project_path.is_dir():
        raise ValueError(f"No existe el directorio del proyecto: {project_path}")
    if limit < 1 or limit > 1000:
        raise ValueError("limit debe estar entre 1 y 1000.")

    findings: list[dict[str, Any]] = []
    skipped_large_files = 0

    for path in _iter_files(project_path):
        if not _is_text_candidate(path):
            continue
        try:
            if path.stat().st_size > max_file_bytes:
                skipped_large_files += 1
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        relative_path = str(path.relative_to(project_path))
        for line_number, line in enumerate(text.splitlines(), start=1):
            for secret_type, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        {
                            "file": relative_path,
                            "line": line_number,
                            "secret_type": secret_type,
                        }
                    )
                    break
            if len(findings) >= limit:
                break
        if len(findings) >= limit:
            break

    return {
        "count": len(findings),
        "findings": findings,
        "truncated": len(findings) >= limit,
        "skipped_large_files": skipped_large_files,
        "warning": "Revisar y rotar credenciales; el scanner no modifica archivos ni devuelve valores." if findings else None,
    }
