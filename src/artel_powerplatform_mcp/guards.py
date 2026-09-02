from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MutationDecision:
    allowed: bool
    dry_run: bool
    reason: str


def evaluate_mutation(method: str, *, dry_run: bool, confirm: bool, allow_writes: bool) -> MutationDecision:
    """Evalúa si una operación HTTP mutante puede ejecutarse.

    DELETE permanece bloqueado en esta etapa. GET se considera lectura.
    POST/PATCH/PUT requieren las tres condiciones de escritura habilitadas.
    """

    normalized = method.upper().strip()
    if normalized == "DELETE":
        return MutationDecision(False, True, "DELETE_BLOCKED")
    if normalized == "GET":
        return MutationDecision(True, False, "READ_ONLY")
    if normalized not in {"POST", "PATCH", "PUT"}:
        return MutationDecision(False, True, "METHOD_NOT_ALLOWED")
    if dry_run:
        return MutationDecision(False, True, "DRY_RUN_ENABLED")
    if not confirm:
        return MutationDecision(False, True, "CONFIRM_REQUIRED")
    if not allow_writes:
        return MutationDecision(False, True, "WRITES_DISABLED")
    return MutationDecision(True, False, "WRITE_CONFIRMED")
