def test_app_import_registers_extension_capabilities():
    from artel_powerplatform_mcp.app import CAPABILITIES, mcp

    assert mcp is not None
    tools = {item["tool"] for item in CAPABILITIES}
    assert "artel_extension_info" in tools
    assert "artel_tmdl_assess_local_security" in tools
    assert "artel_plan_local_bi" in tools
    assert "artel_self_test" in tools
    assert "artel_audit_power_automate_export" in tools
    assert "artel_certify_local_bi" in tools


def test_extension_info_is_read_only_contract():
    import asyncio

    from artel_powerplatform_mcp.app import artel_extension_info

    result = asyncio.run(artel_extension_info())
    assert result.ok is True
    assert result.status == "PASS"
    assert result.data["extension_contract_version"] == "1.7-e2e"
    assert result.data["offline_self_test"] is True
    assert result.data["power_automate_export_audit"] is True
    assert result.data["local_full_certification"] is True
    assert result.data["writes_exposed"] is False
    assert result.data["apply_supported"] is False


def test_self_test_tool_is_green_and_read_only():
    import asyncio

    from artel_powerplatform_mcp.app import artel_self_test

    result = asyncio.run(artel_self_test())
    assert result.ok is True
    assert result.status == "PASS"
    assert result.data["cloud_calls"] == 0
    assert result.data["writes"] == 0
    assert result.data["failed"] == 0
