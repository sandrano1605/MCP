import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from .runtime_certification import run_runtime_certification


def main() -> None:
    parser = argparse.ArgumentParser(description="ARTEL MCP runtime read-only certification")
    parser.add_argument("--project", required=True, help="Ruta al directorio PBIP")
    parser.add_argument("--dataset-id", help="Semantic model / dataset GUID; si se omite usa POWERBI_DATASET_ID")
    parser.add_argument("--seller-column", help="Columna de vendedor en formato Tabla[Columna]")
    parser.add_argument("--seller-a", help="Valor esperado para identidad vendedor A")
    parser.add_argument("--seller-b", help="Valor esperado para identidad vendedor B")
    parser.add_argument("--flow-run-evidence", help="JSON de evidencia de una ejecución real Power Automate")
    parser.add_argument("--fabric-workspace-id")
    parser.add_argument("--fabric-report-id")
    parser.add_argument("--fabric-semantic-model-id")
    parser.add_argument("--full-json", action="store_true")
    args = parser.parse_args()

    result = asyncio.run(
        run_runtime_certification(
            Path(args.project).expanduser(),
            dataset_id=args.dataset_id,
            seller_column=args.seller_column,
            seller_a=args.seller_a,
            seller_b=args.seller_b,
            flow_run_evidence=Path(args.flow_run_evidence).expanduser() if args.flow_run_evidence else None,
            fabric_workspace_id=args.fabric_workspace_id,
            fabric_report_id=args.fabric_report_id,
            fabric_semantic_model_id=args.fabric_semantic_model_id,
        )
    )
    if args.full_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(_compact(result))


def _compact(result: dict[str, Any]) -> str:
    probes = result.get("probes") or {}
    pbi = probes.get("power_bi_dax") or {}
    seller = probes.get("seller_identity_isolation") or {}
    fabric = probes.get("fabric") or {}
    flow = probes.get("power_automate") or {}
    identities = seller.get("identities") or []
    identity_summary = ";".join(
        f"{item.get('identity')}:{item.get('status')}:visible={item.get('visible_sellers')}:other={item.get('other_sellers')}"
        for item in identities
    ) or "-"
    signals = flow.get("signals") or {}
    missing_signals = ",".join(name for name, present in signals.items() if not present) or "NONE"
    lines = [
        "ARTEL_RUNTIME_CERTIFICATION",
        f"OVERALL={result.get('status')}",
        f"POWER_BI_DAX={pbi.get('status')}",
        f"POWER_BI_ROWS={pbi.get('rows')}",
        f"POWER_BI_PROBE_VALUE={pbi.get('probe_value')}",
        f"SELLER_IDENTITY_ISOLATION={seller.get('status')}",
        f"SELLER_IDENTITIES={identity_summary}",
        f"FABRIC={fabric.get('status')}",
        f"FABRIC_WORKSPACES={fabric.get('workspace_count')}",
        f"FABRIC_DEFINITION_PROBE={fabric.get('definition_probe')}",
        f"POWER_AUTOMATE_RUNTIME={flow.get('status')}",
        f"POWER_AUTOMATE_RUN_ID={flow.get('run_id_present')}",
        f"POWER_AUTOMATE_SUCCESS={flow.get('successful_status')}",
        f"POWER_AUTOMATE_SIGNALS={flow.get('signal_count')}/{flow.get('required_signal_count')}",
        f"POWER_AUTOMATE_MISSING={missing_signals}",
        f"CLOUD_CALLS={result.get('cloud_calls')}",
        f"WRITES={result.get('writes')}",
        f"SECRETS_RETURNED={result.get('secrets_returned')}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
