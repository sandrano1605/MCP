import base64
from pathlib import Path

from artel_powerplatform_mcp.tmdl import (
    inspect_tmdl_definition,
    inspect_tmdl_parts,
    load_local_tmdl_parts,
)


SALES = """table Sales
    measure 'Sales Amount' = SUMX(Sales, Sales[Quantity] * Sales[NetPrice])
        formatString: $ #,##0
        displayFolder: KPIs

    measure 'Total Quantity' =
            SUM(Sales[Quantity])
        isHidden

    column ProductKey
        dataType: int64
        sourceColumn: ProductKey
        summarizeBy: none

    column Quantity
        dataType: int64
        sourceColumn: Quantity
        summarizeBy: sum

    column NetPrice
        dataType: double
        sourceColumn: NetPrice
        summarizeBy: sum

    partition Sales-Part = m
        mode: import
        source =
            let
                Source = 1
            in
                Source
"""

PRODUCT = """table Product
    column ProductKey
        dataType: int64
        isKey
        sourceColumn: ProductKey
        summarizeBy: none

    column Category
        dataType: string
        sourceColumn: Category
        summarizeBy: none
"""

RELATIONSHIPS = """relationship rel-sales-product
    fromColumn: Sales.ProductKey
    toColumn: Product.ProductKey
    crossFilteringBehavior: bothDirections
"""

ROLE = """role Seller
    modelPermission: read

    tablePermission Sales = Sales[SellerId] = USERPRINCIPALNAME()
"""


def _parts() -> dict[str, bytes]:
    return {
        "definition/tables/Sales.tmdl": SALES.encode(),
        "definition/tables/Product.tmdl": PRODUCT.encode(),
        "definition/relationships.tmdl": RELATIONSHIPS.encode(),
        "definition/roles/Seller.tmdl": ROLE.encode(),
        "definition/model.tmdl": b"model Model\nref table Sales\nref table Product\nref role Seller\n",
    }


def test_compact_model_summary_counts_tables_relationships_and_rls():
    result = inspect_tmdl_parts(_parts())

    assert result["format"] == "TMDL"
    assert result["scope"] == "ACTIVE_SEMANTIC_MODEL_DEFINITION"
    assert result["analysis_mode"] == "STATIC_TMDL"
    assert result["semantic_runtime_validated"] is False
    assert result["table_count"] == 2
    assert result["column_count"] == 5
    assert result["measure_count"] == 2
    assert result["partition_count"] == 1
    assert result["relationship_count"] == 1
    assert result["role_count"] == 1
    assert result["table_permission_count"] == 1
    assert result["rls_present"] is True
    assert result["rls_secured_tables"] == ["Sales"]
    assert result["status"] == "REVIEW"
    assert any(item["kind"] == "BIDIRECTIONAL_RELATIONSHIP" for item in result["findings"])

    sales = next(table for table in result["tables"] if table["name"] == "Sales")
    assert sales["measure_count"] == 2
    assert sales["column_count"] == 3
    assert "measures" not in sales
    assert "columns" not in sales


def test_details_include_measure_metadata_columns_hashes_and_lexical_dependencies():
    result = inspect_tmdl_parts(
        _parts(),
        include_measures=True,
        include_columns=True,
        include_expressions=True,
        max_expression_chars=200,
    )
    sales = next(table for table in result["tables"] if table["name"] == "Sales")
    amount = next(measure for measure in sales["measures"] if measure["name"] == "Sales Amount")
    total_qty = next(measure for measure in sales["measures"] if measure["name"] == "Total Quantity")

    assert amount["format_string"] == "$ #,##0"
    assert amount["display_folder"] == "KPIs"
    assert amount["expression_sha256"]
    assert amount["dependency_mode"] == "STATIC_LEXICAL"
    assert {ref["object"] for ref in amount["references"]} >= {"Quantity", "NetPrice"}
    assert total_qty["is_hidden"] is True
    assert "SUM(Sales[Quantity])" in total_qty["expression"]

    product = next(table for table in result["tables"] if table["name"] == "Product")
    key = next(column for column in product["columns"] if column["name"] == "ProductKey")
    assert key["is_key"] is True
    assert key["data_type"] == "int64"


def test_relationship_does_not_invent_cardinality_when_not_declared():
    result = inspect_tmdl_parts(_parts())
    relationship = result["relationships"][0]

    assert relationship["from_table"] == "Sales"
    assert relationship["from_column_name"] == "ProductKey"
    assert relationship["to_table"] == "Product"
    assert relationship["to_column_name"] == "ProductKey"
    assert relationship["from_cardinality"] is None
    assert relationship["to_cardinality"] is None
    assert relationship["cardinality_explicit"] is False
    assert relationship["cross_filtering_behavior"] == "bothDirections"


def test_role_filter_is_redacted_by_default_but_hash_and_references_remain():
    result = inspect_tmdl_parts(_parts())
    permission = result["roles"][0]["table_permissions"][0]

    assert permission["table"] == "Sales"
    assert permission["filter_present"] is True
    assert permission["filter_sha256"]
    assert permission["dependency_mode"] == "STATIC_LEXICAL"
    assert "filter_expression" not in permission

    expanded = inspect_tmdl_parts(_parts(), include_expressions=True)
    expanded_permission = expanded["roles"][0]["table_permissions"][0]
    assert "USERPRINCIPALNAME" in expanded_permission["filter_expression"]


def test_unknown_relationship_table_is_flagged():
    parts = _parts()
    parts["definition/relationships.tmdl"] = b"""relationship broken\n    fromColumn: Missing.Id\n    toColumn: Product.ProductKey\n"""
    result = inspect_tmdl_parts(parts)

    finding = next(item for item in result["findings"] if item["kind"] == "RELATIONSHIP_TABLE_NOT_FOUND")
    assert finding["table"] == "Missing"
    assert result["status"] == "REVIEW"


def test_fabric_definition_is_decoded_and_inspected():
    parts = _parts()
    response = {
        "definition": {
            "format": "TMDL",
            "parts": [
                {
                    "path": path,
                    "payloadType": "InlineBase64",
                    "payload": base64.b64encode(content).decode("ascii").rstrip("="),
                }
                for path, content in parts.items()
            ],
        }
    }

    result = inspect_tmdl_definition(response)
    assert result["table_count"] == 2
    assert result["role_count"] == 1


def test_local_loader_reads_only_active_semantic_model_definition(tmp_path: Path):
    project = tmp_path / "project"
    model = project / "Demo.SemanticModel"
    tables = model / "definition" / "tables"
    roles = model / "definition" / "roles"
    tables.mkdir(parents=True)
    roles.mkdir(parents=True)
    (tables / "Sales.tmdl").write_text(SALES, encoding="utf-8")
    (roles / "Seller.tmdl").write_text(ROLE, encoding="utf-8")
    (model / "definition" / "relationships.tmdl").write_text(RELATIONSHIPS, encoding="utf-8")
    backup = project / "backup" / "Old.SemanticModel" / "definition" / "tables"
    backup.mkdir(parents=True)
    (backup / "Old.tmdl").write_text("table Old\n", encoding="utf-8")

    model_name, parts = load_local_tmdl_parts(project)

    assert model_name == "Demo.SemanticModel"
    assert "definition/tables/Sales.tmdl" in parts
    assert all("Old.tmdl" not in path for path in parts)
