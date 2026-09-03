from __future__ import annotations

from copy import deepcopy
from typing import Any


def assess_model_policy(
    model: dict[str, Any],
    *,
    expect_rls: bool = False,
) -> dict[str, Any]:
    """Aplica una política de riesgo sobre un resultado TMDL sin inventar semántica runtime.

    `expect_rls` expresa una expectativa del consumidor (por ejemplo, aislamiento por
    vendedor). La ausencia de RLS solo se convierte en hallazgo crítico cuando esa
    expectativa fue declarada explícitamente.
    """
    result = deepcopy(model)
    findings = list(result.get("findings", []))
    relationships = list(result.get("relationships", []))

    rls_present = bool(result.get("rls_present"))
    secured_tables = list(result.get("rls_secured_tables", []))
    bidirectional = [
        relationship
        for relationship in relationships
        if str(relationship.get("cross_filtering_behavior") or "").casefold() == "bothdirections"
    ]
    cardinality_not_explicit = [
        relationship
        for relationship in relationships
        if not bool(relationship.get("cardinality_explicit"))
    ]

    if expect_rls and not rls_present:
        findings.append(
            {
                "kind": "RLS_REQUIRED_BUT_NOT_DECLARED",
                "severity": "HIGH",
                "requires_review": True,
                "reason": "El consumidor declaró que requiere aislamiento RLS, pero TMDL no contiene roles/tablePermission.",
            }
        )

    result["security_policy"] = {
        "rls_expectation": "REQUIRED" if expect_rls else "NOT_REQUIRED_BY_POLICY",
        "rls_posture": "RLS_DECLARED" if rls_present else "NO_RLS_DECLARED",
        "rls_secured_tables": secured_tables,
        "runtime_certification_required": True,
        "runtime_certification_reason": (
            "La inspección TMDL no demuestra identidad efectiva, propagación de filtros ni aislamiento de filas."
        ),
    }
    result["relationship_policy"] = {
        "bidirectional_count": len(bidirectional),
        "bidirectional_relationships": [item.get("name") for item in bidirectional],
        "cardinality_not_explicit_count": len(cardinality_not_explicit),
        "cardinality_not_explicit_relationships": [item.get("name") for item in cardinality_not_explicit],
        "effective_cardinality_inferred": False,
    }
    result["findings"] = findings
    result["finding_count"] = len(findings)
    result["status"] = "REVIEW" if any(item.get("requires_review") for item in findings) else "PASS"
    result["semantic_runtime_validated"] = False
    return result
