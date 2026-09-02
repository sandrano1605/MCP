from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ToolStatus = Literal["OK", "PASS", "WARNING", "DRY_RUN", "BLOCKED", "FAIL"]


class ToolResult(BaseModel):
    """Contrato homogéneo para respuestas consumibles por cualquier cliente MCP/LLM."""

    ok: bool
    status: ToolStatus
    operation: str
    data: dict[str, Any] = Field(default_factory=dict)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)


def ok_result(operation: str, *, data: dict[str, Any] | None = None, status: ToolStatus = "OK", warnings: list[str] | None = None) -> ToolResult:
    return ToolResult(
        ok=True,
        status=status,
        operation=operation,
        data=data or {},
        warnings=warnings or [],
    )


def fail_result(operation: str, *, status: ToolStatus = "FAIL", message: str, data: dict[str, Any] | None = None) -> ToolResult:
    return ToolResult(
        ok=False,
        status=status,
        operation=operation,
        data=data or {},
        findings=[{"message": message}],
    )
