from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

FABRIC_DEFAULT_SCOPES = (
    "https://api.fabric.microsoft.com/Workspace.Read.All",
    "https://api.fabric.microsoft.com/Item.Read.All",
    "https://api.fabric.microsoft.com/Report.ReadWrite.All",
    "https://api.fabric.microsoft.com/SemanticModel.ReadWrite.All",
)
POWERBI_DEFAULT_SCOPES = (
    "https://analysis.windows.net/powerbi/api/Dataset.Read.All",
)
POWERPLATFORM_DEFAULT_SCOPES = (
    "https://api.powerplatform.com/.default",
)


@dataclass(frozen=True)
class Settings:
    bi_project_path: Path | None
    allow_writes: bool
    entra_client_id: str | None
    entra_tenant: str | None
    fabric_access_token: str | None
    fabric_api_base_url: str
    fabric_scopes: tuple[str, ...]
    powerbi_access_token: str | None
    powerbi_api_base_url: str
    powerbi_dataset_id: str | None
    powerbi_scopes: tuple[str, ...]
    powerplatform_access_token: str | None
    powerplatform_api_base_url: str | None
    powerplatform_scopes: tuple[str, ...]


def _split_scopes(value: str | None, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if not value or not value.strip():
        return default
    normalized = value.replace(",", " ")
    return tuple(part.strip() for part in normalized.split() if part.strip())


def load_settings() -> Settings:
    raw_path = os.getenv("ARTEL_BI_PROJECT_PATH", "").strip()
    return Settings(
        bi_project_path=Path(raw_path).expanduser() if raw_path else None,
        allow_writes=os.getenv("ARTEL_ALLOW_WRITES", "false").lower() == "true",
        entra_client_id=(os.getenv("ENTRA_CLIENT_ID") or "").strip() or None,
        entra_tenant=(os.getenv("ENTRA_TENANT_ID") or "").strip() or None,
        fabric_access_token=os.getenv("FABRIC_ACCESS_TOKEN") or None,
        fabric_api_base_url=os.getenv("FABRIC_API_BASE_URL", "https://api.fabric.microsoft.com/v1").rstrip("/"),
        fabric_scopes=_split_scopes(os.getenv("FABRIC_SCOPES"), FABRIC_DEFAULT_SCOPES),
        powerbi_access_token=os.getenv("POWERBI_ACCESS_TOKEN") or None,
        powerbi_api_base_url=os.getenv("POWERBI_API_BASE_URL", "https://api.powerbi.com/v1.0/myorg").rstrip("/"),
        powerbi_dataset_id=os.getenv("POWERBI_DATASET_ID") or None,
        powerbi_scopes=_split_scopes(os.getenv("POWERBI_SCOPES"), POWERBI_DEFAULT_SCOPES),
        powerplatform_access_token=os.getenv("POWERPLATFORM_ACCESS_TOKEN") or None,
        powerplatform_api_base_url=os.getenv("POWERPLATFORM_API_BASE_URL", "https://api.powerplatform.com").rstrip("/"),
        powerplatform_scopes=_split_scopes(os.getenv("POWERPLATFORM_SCOPES"), POWERPLATFORM_DEFAULT_SCOPES),
    )
