from __future__ import annotations

from dataclasses import dataclass, asdict
from shutil import which
from typing import Any


MICROSOFT_SKILLS_REPO = "https://github.com/microsoft/skills-for-fabric"
REMOTE_POWERBI_MCP_URL = "https://api.fabric.microsoft.com/v1/mcp/powerbi"


@dataclass(frozen=True)
class Component:
    key: str
    owner: str
    purpose: str
    integration_mode: str
    evidence_grade: int
    write_capable: bool


COMPONENTS: tuple[Component, ...] = (
    Component(
        key="powerbi-modeling-mcp",
        owner="microsoft",
        purpose="Semantic model inspection/authoring, DAX, relationships and RLS operations.",
        integration_mode="external_mcp",
        evidence_grade=5,
        write_capable=True,
    ),
    Component(
        key="powerbi-remote-mcp",
        owner="microsoft",
        purpose="Remote schema/query access to published Power BI semantic models using user context.",
        integration_mode="remote_mcp",
        evidence_grade=5,
        write_capable=False,
    ),
    Component(
        key="powerbi-report-authoring",
        owner="microsoft",
        purpose="PBIR/PBIP mechanics, metadata lookup, validation, Desktop reload and screenshot verification.",
        integration_mode="skill_cli",
        evidence_grade=4,
        write_capable=True,
    ),
    Component(
        key="powerbi-report-design",
        owner="microsoft",
        purpose="Design brief, page archetypes, chart selection, layout, accessibility and visual consistency.",
        integration_mode="skill_contract",
        evidence_grade=2,
        write_capable=False,
    ),
    Component(
        key="powerbi-report-planning",
        owner="microsoft",
        purpose="Requirements-to-build workflow: inspect, spec, approve, build, validate and publish.",
        integration_mode="skill_contract",
        evidence_grade=2,
        write_capable=False,
    ),
    Component(
        key="semantic-model-authoring",
        owner="microsoft",
        purpose="Tool-selection policy and semantic-model workflows with Modeling MCP as Tier 1.",
        integration_mode="skill_contract",
        evidence_grade=3,
        write_capable=True,
    ),
    Component(
        key="artel-power-automate-engine",
        owner="artel",
        purpose="Flow definition/run inspection, LLM grounding gates, write planning and runtime evidence.",
        integration_mode="native",
        evidence_grade=5,
        write_capable=True,
    ),
    Component(
        key="artel-evidence-governance",
        owner="artel",
        purpose="Dry-run, confirmation, write guard, checkpoint, rollback, evidence grading and certification.",
        integration_mode="native",
        evidence_grade=5,
        write_capable=True,
    ),
)


ROUTES: dict[str, tuple[str, ...]] = {
    "plan": ("powerbi-report-planning", "powerbi-report-design", "artel-evidence-governance"),
    "design": ("powerbi-report-design", "powerbi-report-authoring", "artel-evidence-governance"),
    "author_report": ("powerbi-report-authoring", "powerbi-modeling-mcp", "artel-evidence-governance"),
    "semantic_model": ("powerbi-modeling-mcp", "semantic-model-authoring", "artel-evidence-governance"),
    "runtime_query": ("powerbi-remote-mcp", "powerbi-modeling-mcp", "artel-evidence-governance"),
    "power_automate": ("artel-power-automate-engine", "artel-evidence-governance"),
    "certify": (
        "powerbi-modeling-mcp",
        "powerbi-remote-mcp",
        "powerbi-report-authoring",
        "artel-power-automate-engine",
        "artel-evidence-governance",
    ),
}


EVIDENCE_PRIORITY = (
    "runtime_modeling_mcp",
    "runtime_remote_powerbi_mcp",
    "runtime_power_automate",
    "fabric_definition",
    "deterministic_cli_validation",
    "local_pbip_tmdl",
    "static_review",
    "hypothesis",
)


def dependency_status() -> dict[str, Any]:
    """Detect local executable dependencies without launching external processes."""
    node = which("node")
    npx = which("npx")
    report_author = which("powerbi-report-author")
    desktop_bridge = which("powerbi-desktop")
    return {
        "node": {"available": bool(node)},
        "npx": {"available": bool(npx)},
        "powerbi_report_author": {"available": bool(report_author)},
        "powerbi_desktop_bridge": {"available": bool(desktop_bridge)},
        "modeling_mcp_command": [
            "npx",
            "-y",
            "@microsoft/powerbi-modeling-mcp@latest",
            "--start",
            "--readonly",
        ],
        "remote_powerbi_mcp_url": REMOTE_POWERBI_MCP_URL,
        "report_authoring_cli_install": [
            "npm",
            "install",
            "-g",
            "@microsoft/powerbi-report-authoring-cli@latest",
            "@microsoft/powerbi-desktop-bridge-cli@latest",
        ],
        "secrets_returned": False,
    }


def route_work(intent: str, *, allow_writes: bool = False) -> dict[str, Any]:
    """Return the deterministic component route for a Power BI/Power Automate task."""
    normalized = intent.strip().casefold().replace("-", "_").replace(" ", "_")
    aliases = {
        "planning": "plan",
        "report_planning": "plan",
        "report_design": "design",
        "author": "author_report",
        "report_authoring": "author_report",
        "model": "semantic_model",
        "dax": "runtime_query",
        "query": "runtime_query",
        "flow": "power_automate",
        "automation": "power_automate",
        "certification": "certify",
    }
    route_key = aliases.get(normalized, normalized)
    if route_key not in ROUTES:
        route_key = "certify"

    selected = []
    for key in ROUTES[route_key]:
        component = next(item for item in COMPONENTS if item.key == key)
        selected.append({
            **asdict(component),
            "writes_allowed": bool(allow_writes and component.write_capable),
        })

    return {
        "intent": intent,
        "route": route_key,
        "components": selected,
        "write_policy": {
            "requested": allow_writes,
            "effective": allow_writes,
            "dry_run_required": True,
            "confirm_required": True,
            "checkpoint_required": True,
        },
        "power_automate_is_independent_engine": True,
        "microsoft_components_are_dependencies_not_reimplemented": True,
        "secrets_returned": False,
    }


def choose_evidence_source(available: dict[str, bool]) -> dict[str, Any]:
    """Choose the highest-grade available evidence source using ARTEL evidence priority."""
    for rank, source in enumerate(EVIDENCE_PRIORITY, start=1):
        if available.get(source):
            return {
                "source": source,
                "priority_rank": rank,
                "grade": max(1, 6 - min(rank, 5)),
                "status": "SELECTED",
            }
    return {"source": None, "priority_rank": None, "grade": 0, "status": "NO_EVIDENCE"}


def validate_layout_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Validate a Microsoft-style Design Brief layout contract deterministically."""
    findings: list[dict[str, Any]] = []
    canvas = contract.get("canvas") or {}
    width = canvas.get("width")
    height = canvas.get("height")
    placements = contract.get("placements") or []

    if not isinstance(width, (int, float)) or width <= 0:
        findings.append({"code": "INVALID_CANVAS_WIDTH", "severity": "HIGH"})
    if not isinstance(height, (int, float)) or height <= 0:
        findings.append({"code": "INVALID_CANVAS_HEIGHT", "severity": "HIGH"})

    rectangles: list[tuple[str, float, float, float, float]] = []
    for index, item in enumerate(placements):
        if not isinstance(item, dict):
            findings.append({"code": "INVALID_PLACEMENT", "index": index, "severity": "HIGH"})
            continue
        pos = item.get("position") or {}
        try:
            x = float(pos["x"])
            y = float(pos["y"])
            w = float(pos["width"])
            h = float(pos["height"])
        except (KeyError, TypeError, ValueError):
            findings.append({"code": "PLACEMENT_POSITION_INCOMPLETE", "index": index, "severity": "HIGH"})
            continue
        item_id = str(item.get("id") or f"placement_{index}")
        if w <= 0 or h <= 0:
            findings.append({"code": "INVALID_PLACEMENT_SIZE", "id": item_id, "severity": "HIGH"})
            continue
        if isinstance(width, (int, float)) and isinstance(height, (int, float)):
            if x < 0 or y < 0 or x + w > width or y + h > height:
                findings.append({"code": "OUT_OF_BOUNDS", "id": item_id, "severity": "HIGH"})
        rectangles.append((item_id, x, y, w, h))

    for i, first in enumerate(rectangles):
        for second in rectangles[i + 1 :]:
            a_id, ax, ay, aw, ah = first
            b_id, bx, by, bw, bh = second
            overlap = ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by
            if overlap:
                findings.append({"code": "UNDECLARED_OVERLAP", "a": a_id, "b": b_id, "severity": "MEDIUM"})

    return {
        "status": "PASS" if not findings else "REVIEW",
        "placement_count": len(placements),
        "finding_count": len(findings),
        "findings": findings,
        "writes": 0,
    }


def stack_manifest() -> dict[str, Any]:
    return {
        "contract_version": "1.8-microsoft-skills",
        "microsoft_upstream": MICROSOFT_SKILLS_REPO,
        "remote_powerbi_mcp_url": REMOTE_POWERBI_MCP_URL,
        "components": [asdict(item) for item in COMPONENTS],
        "routes": {key: list(value) for key, value in ROUTES.items()},
        "evidence_priority": list(EVIDENCE_PRIORITY),
        "architecture": {
            "artel_role": "orchestrator_governor_evidence",
            "powerbi_role": "microsoft_mcp_and_skills",
            "power_automate_role": "independent_artel_engine",
        },
        "writes_default": False,
        "secrets_returned": False,
    }
