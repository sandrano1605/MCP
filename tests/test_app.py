def test_app_import_registers_extension_capabilities():
    from artel_powerplatform_mcp.app import CAPABILITIES, mcp

    assert mcp is not None
    tools = {item["tool"] for item in CAPABILITIES}
    assert "artel_extension_info" in tools
    assert "artel_tmdl_assess_local_security" in tools
    assert "artel_plan_local_bi" in tools


def test_extension_info_is_read_only_contract():
    import asyncio

    from artel_powerplatform_mcp.app import artel_extension_info

    result = asyncio.run(artel_extension_info())
    assert result.ok is True
    assert result.status == "PASS"
    assert result.data["extension_contract_version"] == "1.6-dry-run"
    assert result.data["writes_exposed"] is False
    assert result.data["apply_supported"] is False
