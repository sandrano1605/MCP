from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    bi_project_path: Path | None
    allow_writes: bool
    powerbi_access_token: str | None
    powerbi_api_base_url: str
    powerbi_dataset_id: str | None
    powerplatform_access_token: str | None
    powerplatform_api_base_url: str | None


def load_settings() -> Settings:
    raw_path = os.getenv("ARTEL_BI_PROJECT_PATH", "").strip()
    return Settings(
        bi_project_path=Path(raw_path).expanduser() if raw_path else None,
        allow_writes=os.getenv("ARTEL_ALLOW_WRITES", "false").lower() == "true",
        powerbi_access_token=os.getenv("POWERBI_ACCESS_TOKEN") or None,
        powerbi_api_base_url=os.getenv("POWERBI_API_BASE_URL", "https://api.powerbi.com/v1.0/myorg").rstrip("/"),
        powerbi_dataset_id=os.getenv("POWERBI_DATASET_ID") or None,
        powerplatform_access_token=os.getenv("POWERPLATFORM_ACCESS_TOKEN") or None,
        powerplatform_api_base_url=(os.getenv("POWERPLATFORM_API_BASE_URL") or "").rstrip("/") or None,
    )
