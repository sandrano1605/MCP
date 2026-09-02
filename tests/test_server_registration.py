def test_server_import_registers_tools_without_type_errors():
    """Importar server ejecuta los decoradores @mcp.tool y detecta incompatibilidades de tipos."""

    from artel_powerplatform_mcp.server import CAPABILITIES, mcp

    assert mcp is not None
    assert len(CAPABILITIES) == 7
    assert {item["tool"] for item in CAPABILITIES} == {
        "artel_list_capabilities",
        "artel_health",
        "artel_inspect_bi_project",
        "artel_validate_s510_blueprint",
        "artel_scan_embedded_secrets",
        "artel_powerbi_execute_dax",
        "artel_powerplatform_request",
    }
