from __future__ import annotations

from typing import Any

from .model_policy import assess_model_policy


def build_model_plan(model: dict[str, Any], *, expect_rls: bool = False) -> dict[str, Any]:
    assessed = assess_model_policy(model, expect_rls=expect_rls)
    actions: list[dict[str, Any]] = []

    for finding in assessed.get("findings", []):
        kind = finding.get("kind")
        if kind == "RLS_REQUIRED_BUT_NOT_DECLARED":
            actions.append(
                _action(
                    "DESIGN_RLS_POLICY",
                    priority="HIGH",
                    target="semantic_model",
                    reason="Se requiere aislamiento RLS pero no existe una política declarada en TMDL.",
                    write_ready=False,
                    blocker="Se necesita definir identidad, tabla/columna de vendedor y expresión de aislamiento antes de escribir.",
                    source_finding=kind,
                )
            )
        elif kind == "BIDIRECTIONAL_RELATIONSHIP":
            actions.append(
                _action(
                    "REVIEW_CROSS_FILTER_DIRECTION",
                    priority="MEDIUM",
                    target=finding.get("relationship"),
                    reason="Una relación BothDirections puede ampliar propagación de filtros y debe justificarse antes de cambiarse.",
                    write_ready=False,
                    blocker="Se requiere análisis de medidas dependientes y validación runtime antes de proponer OneDirection.",
                    source_finding=kind,
                )
            )
        elif kind == "RELATIONSHIP_TABLE_NOT_FOUND":
            actions.append(
                _action(
                    "REPAIR_RELATIONSHIP_REFERENCE",
                    priority="HIGH",
                    target=finding.get("relationship"),
                    reason="La relación referencia una tabla no encontrada en la definición activa.",
                    write_ready=False,
                    blocker="Debe resolverse el objeto correcto antes de generar un patch TMDL.",
                    source_finding=kind,
                )
            )
        elif finding.get("requires_review"):
            actions.append(
                _action(
                    "REVIEW_MODEL_FINDING",
                    priority=str(finding.get("severity") or "MEDIUM"),
                    target=finding.get("table") or finding.get("relationship") or "semantic_model",
                    reason=f"Hallazgo estático: {kind}",
                    write_ready=False,
                    blocker="Requiere decisión de ingeniería antes de preparar una modificación.",
                    source_finding=kind,
                )
            )

    return {
        "mode": "DRY_RUN",
        "apply": False,
        "domain": "TMDL_MODEL",
        "source_scope": assessed.get("scope"),
        "security_policy": assessed.get("security_policy"),
        "relationship_policy": assessed.get("relationship_policy"),
        "action_count": len(actions),
        "write_ready_count": sum(1 for action in actions if action["write_ready"]),
        "blocked_action_count": sum(1 for action in actions if not action["write_ready"]),
        "actions": actions,
        "checkpoint_required_before_apply": True,
        "runtime_validation_required": True,
        "status": "REVIEW" if actions else "PASS",
    }


def build_canvas_plan(canvas: dict[str, Any]) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    for page in canvas.get("pages", []):
        page_name = page.get("display_name") or page.get("name") or page.get("page_key")
        for finding in page.get("findings", []):
            kind = finding.get("kind")
            overlap_class = finding.get("overlap_class")
            if overlap_class == "EXPECTED_LAYERING":
                continue
            if kind == "BOUNDS":
                actions.append(
                    _action(
                        "MOVE_WITHIN_CANVAS",
                        priority="HIGH",
                        target=finding.get("visual"),
                        page=page_name,
                        reason="El visual excede los límites declarados de la página.",
                        write_ready=False,
                        blocker="El planner aún debe calcular una posición objetivo preservando grid y spacing.",
                        source_finding=kind,
                    )
                )
            elif kind == "ALIGNMENT_DRIFT":
                actions.append(
                    _action(
                        "ALIGN_VISUALS",
                        priority="LOW",
                        target=[finding.get("visual_a"), finding.get("visual_b")],
                        page=page_name,
                        reason=f"Deriva de alineación detectada en {finding.get('edge')} con delta {finding.get('delta')}.",
                        write_ready=False,
                        blocker="Debe seleccionarse un visual ancla antes de generar coordenadas nuevas.",
                        source_finding=kind,
                    )
                )
            elif kind == "OVERLAP":
                actions.append(
                    _action(
                        "REVIEW_Z_ORDER",
                        priority=str(finding.get("severity") or "MEDIUM"),
                        target=[finding.get("visual_a"), finding.get("visual_b")],
                        page=page_name,
                        reason=f"Solape clasificado como {overlap_class or 'GENERIC_OVERLAP'}.",
                        write_ready=False,
                        blocker="Se requiere validar intención visual antes de mover o cambiar z-order.",
                        source_finding=kind,
                    )
                )
            elif finding.get("requires_review"):
                actions.append(
                    _action(
                        "REVIEW_CANVAS_FINDING",
                        priority=str(finding.get("severity") or "MEDIUM"),
                        target=finding.get("visual") or [finding.get("visual_a"), finding.get("visual_b")],
                        page=page_name,
                        reason=f"Hallazgo PBIR: {kind}",
                        write_ready=False,
                        blocker="Requiere decisión visual antes de escribir PBIR.",
                        source_finding=kind,
                    )
                )

    return {
        "mode": "DRY_RUN",
        "apply": False,
        "domain": "PBIR_CANVAS",
        "source_scope": canvas.get("scope"),
        "action_count": len(actions),
        "write_ready_count": sum(1 for action in actions if action["write_ready"]),
        "blocked_action_count": sum(1 for action in actions if not action["write_ready"]),
        "actions": actions,
        "checkpoint_required_before_apply": True,
        "runtime_validation_required": True,
        "status": "REVIEW" if actions else "PASS",
    }


def build_combined_plan(
    *,
    model: dict[str, Any] | None = None,
    canvas: dict[str, Any] | None = None,
    expect_rls: bool = False,
) -> dict[str, Any]:
    model_plan = build_model_plan(model, expect_rls=expect_rls) if model is not None else None
    canvas_plan = build_canvas_plan(canvas) if canvas is not None else None
    plans = [plan for plan in (model_plan, canvas_plan) if plan is not None]
    return {
        "mode": "DRY_RUN",
        "apply": False,
        "domains": [plan["domain"] for plan in plans],
        "action_count": sum(plan["action_count"] for plan in plans),
        "write_ready_count": sum(plan["write_ready_count"] for plan in plans),
        "blocked_action_count": sum(plan["blocked_action_count"] for plan in plans),
        "model_plan": model_plan,
        "canvas_plan": canvas_plan,
        "checkpoint_required_before_apply": True,
        "runtime_validation_required": True,
        "status": "REVIEW" if any(plan["status"] == "REVIEW" for plan in plans) else "PASS",
    }


def _action(
    action: str,
    *,
    priority: str,
    target: Any,
    reason: str,
    write_ready: bool,
    blocker: str | None,
    source_finding: str | None,
    page: str | None = None,
) -> dict[str, Any]:
    return {
        "action": action,
        "priority": priority,
        "target": target,
        "page": page,
        "reason": reason,
        "write_ready": write_ready,
        "blocker": blocker,
        "source_finding": source_finding,
    }
