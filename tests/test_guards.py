from artel_powerplatform_mcp.guards import evaluate_mutation


def test_get_is_read_only_and_allowed():
    result = evaluate_mutation("GET", dry_run=True, confirm=False, allow_writes=False)
    assert result.allowed is True
    assert result.reason == "READ_ONLY"


def test_write_defaults_to_dry_run():
    result = evaluate_mutation("PATCH", dry_run=True, confirm=False, allow_writes=False)
    assert result.allowed is False
    assert result.dry_run is True
    assert result.reason == "DRY_RUN_ENABLED"


def test_write_requires_confirmation():
    result = evaluate_mutation("POST", dry_run=False, confirm=False, allow_writes=True)
    assert result.allowed is False
    assert result.reason == "CONFIRM_REQUIRED"


def test_write_requires_global_enablement():
    result = evaluate_mutation("PUT", dry_run=False, confirm=True, allow_writes=False)
    assert result.allowed is False
    assert result.reason == "WRITES_DISABLED"


def test_write_is_allowed_only_with_all_guards():
    result = evaluate_mutation("PATCH", dry_run=False, confirm=True, allow_writes=True)
    assert result.allowed is True
    assert result.reason == "WRITE_CONFIRMED"


def test_delete_remains_blocked():
    result = evaluate_mutation("DELETE", dry_run=False, confirm=True, allow_writes=True)
    assert result.allowed is False
    assert result.reason == "DELETE_BLOCKED"
