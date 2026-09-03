from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .certification import certify_local_bi, run_self_test


def main() -> None:
    parser = argparse.ArgumentParser(description="ARTEL MCP end-to-end certification")
    parser.add_argument("--project", required=True, help="Ruta al directorio PBIP")
    parser.add_argument("--flow", help="Ruta opcional a export JSON de Power Automate")
    parser.add_argument("--expect-rls", action="store_true", help="Exigir RLS como política")
    parser.add_argument("--max-findings", type=int, default=100)
    parser.add_argument("--full-json", action="store_true", help="Emitir detalle JSON completo")
    args = parser.parse_args()

    self_test = run_self_test()
    project = certify_local_bi(
        Path(args.project).expanduser(),
        flow_path=Path(args.flow).expanduser() if args.flow else None,
        expect_rls=args.expect_rls,
        max_findings=args.max_findings,
    )

    result = {
        "certification_version": "1.7-e2e",
        "self_test": self_test,
        "project": project,
        "overall": "FAIL" if self_test.get("status") == "FAIL" or project.get("status") == "FAIL" else ("REVIEW" if project.get("status") == "REVIEW" else "PASS"),
    }
    if args.full_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(_compact(result))


def _compact(result: dict[str, Any]) -> str:
    self_test = result["self_test"]
    project = result["project"]
    canvas = project.get("canvas", {})
    model = project.get("model", {})
    planner = project.get("planner", {})
    flow = project.get("power_automate")
    security = project.get("security_policy") or {}
    runtime = project.get("runtime") or {}
    lines = [
        "ARTEL_E2E_CERTIFICATION",
        f"OVERALL={result.get('overall')}",
        f"SELF_TEST={self_test.get('status')} ({self_test.get('passed')}/{self_test.get('check_count')})",
        f"ENGINE={project.get('engine_status')}",
        f"PROJECT={project.get('project_status')}",
        f"PAGES={canvas.get('pages')}",
        f"VISUALS={canvas.get('visuals')}",
        f"CANVAS_REVIEW={canvas.get('review_findings')}",
        f"TABLES={model.get('tables')}",
        f"MEASURES={model.get('measures')}",
        f"MEASURES_HASHED={model.get('measures_hashed')}",
        f"RELATIONSHIPS={model.get('relationships')}",
        f"RLS_PRESENT={model.get('rls_present')}",
        f"RLS_EXPECTATION={security.get('rls_expectation')}",
        f"PLANNER_ACTIONS={planner.get('actions')}",
        f"PLANNER_WRITE_READY={planner.get('write_ready')}",
        f"SECRETS={project.get('secret_scan', {}).get('count')}",
        f"FLOW={'NOT_PROVIDED' if flow is None else flow.get('status')}",
        f"FLOW_ACTIONS={'-' if flow is None else flow.get('action_count')}",
        f"RUNTIME_POWER_BI={runtime.get('power_bi_semantic')}",
        f"RUNTIME_SELLER_ISOLATION={runtime.get('seller_isolation')}",
        f"RUNTIME_POWER_AUTOMATE={runtime.get('power_automate')}",
        f"RUNTIME_FABRIC={runtime.get('fabric')}",
        "WRITES=0",
        "CLOUD_CALLS=0",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
