def test_server_import_registers_tools_without_type_errors():
    """Importar server ejecuta los decoradores @mcp.tool y valida capacidades mínimas obligatorias."""

    from artel_powerplatform_mcp.server import CAPABILITIES, mcp

    assert mcp is not None
    tools = {item["tool"] for item in CAPABILITIES}
    required = {
        "artel_list_capabilities",
        "artel_health",
        "artel_auth_status",
        "artel_auth_begin_device_code",
        "artel_auth_complete_device_code",
        "artel_inspect_bi_project",
        "artel_pbir_inspect_local_canvas",
        "artel_tmdl_inspect_local_model",
        "artel_validate_s510_blueprint",
        "artel_scan_embedded_secrets",
        "artel_powerbi_execute_dax",
        "artel_fabric_list_workspaces",
        "artel_fabric_list_items",
        "artel_fabric_get_item",
        "artel_fabric_get_report_definition",
        "artel_fabric_inspect_report_canvas",
        "artel_fabric_get_semantic_model_definition",
        "artel_fabric_inspect_semantic_model",
        "artel_powerplatform_request",
    }
    assert required <= tools
    assert len(tools) == len(CAPABILITIES)
