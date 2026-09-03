from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .definitions import decode_definition_parts

_DECL_NAME = r"(?P<name>'(?:''|[^'])*'|[^\s=]+)"
_TABLE_RE = re.compile(rf"^(?P<indent>\s*)table\s+{_DECL_NAME}\s*$", re.IGNORECASE)
_MEASURE_RE = re.compile(rf"^(?P<indent>\s*)measure\s+{_DECL_NAME}\s*=\s*(?P<expr>.*)$", re.IGNORECASE)
_COLUMN_RE = re.compile(rf"^(?P<indent>\s*)column\s+{_DECL_NAME}(?:\s*=\s*(?P<expr>.*))?\s*$", re.IGNORECASE)
_PARTITION_RE = re.compile(rf"^(?P<indent>\s*)partition\s+{_DECL_NAME}\s*=\s*(?P<source_type>\S+).*$", re.IGNORECASE)
_REL_RE = re.compile(rf"^(?P<indent>\s*)relationship\s+{_DECL_NAME}\s*$", re.IGNORECASE)
_ROLE_RE = re.compile(rf"^(?P<indent>\s*)role\s+{_DECL_NAME}\s*$", re.IGNORECASE)
_PERMISSION_RE = re.compile(rf"^(?P<indent>\s*)tablePermission\s+{_DECL_NAME}\s*=\s*(?P<expr>.*)$", re.IGNORECASE)
_PROPERTY_RE = re.compile(r"^\s*(?P<key>[A-Za-z][A-Za-z0-9_]*)\s*:\s*(?P<value>.*)$")
_FLAG_RE = re.compile(r"^\s*(?P<key>isHidden|isKey|isNullable|isActive)\s*$", re.IGNORECASE)

_TABLE_REF_RE = re.compile(r"(?:'((?:''|[^'])+)'|([A-Za-z_][\w ]*))\s*\[([^\]]+)\]")
_MEASURE_REF_RE = re.compile(r"(?<![\w'])\[([^\]]+)\]")

_MEASURE_PROPERTY_KEYS = {
    "formatstring",
    "displayfolder",
    "lineagetag",
    "ishidden",
    "description",
    "dataCategory".casefold(),
    "detailrowsdefinition",
}
_PERMISSION_PROPERTY_KEYS = {"lineagetag", "description"}


class TmdlInspectionError(RuntimeError):
    """El modelo TMDL no pudo analizarse de forma determinística."""


def load_local_tmdl_parts(
    project_path: Path,
    *,
    semantic_model_name: str | None = None,
    max_total_bytes: int = 25_000_000,
) -> tuple[str, dict[str, bytes]]:
    """Carga únicamente la definición TMDL del semantic model activo de un PBIP."""
    if not project_path.is_dir():
        raise ValueError(f"No existe el directorio del proyecto: {project_path}")

    model_dirs = sorted(path for path in project_path.glob("*.SemanticModel") if path.is_dir())
    if semantic_model_name:
        model_dirs = [
            path
            for path in model_dirs
            if path.name == semantic_model_name or path.stem == semantic_model_name
        ]
    if not model_dirs:
        raise TmdlInspectionError("No se encontró un directorio *.SemanticModel compatible.")
    if len(model_dirs) > 1:
        raise TmdlInspectionError("Hay múltiples semantic models; especifica semantic_model_name.")

    model_dir = model_dirs[0]
    definition_dir = model_dir / "definition"
    if not definition_dir.is_dir():
        raise TmdlInspectionError("El semantic model no contiene directorio definition TMDL.")

    parts: dict[str, bytes] = {}
    total_bytes = 0
    for path in sorted(definition_dir.rglob("*.tmdl")):
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise TmdlInspectionError(f"No fue posible leer TMDL: {path.name}.") from exc
        total_bytes += len(payload)
        if total_bytes > max_total_bytes:
            raise TmdlInspectionError("La definición TMDL local excede el límite seguro de 25 MB.")
        parts[path.relative_to(model_dir).as_posix()] = payload

    if not parts:
        raise TmdlInspectionError("No se encontraron archivos *.tmdl en la definición activa.")
    return model_dir.name, parts


def inspect_tmdl_definition(
    response: dict[str, Any],
    *,
    include_measures: bool = False,
    include_columns: bool = False,
    include_expressions: bool = False,
    max_expression_chars: int = 2_000,
    max_items: int = 500,
) -> dict[str, Any]:
    """Inspecciona una respuesta Fabric getDefinition en formato TMDL."""
    definition_format, parts = decode_definition_parts(response)
    if definition_format not in {None, "TMDL"}:
        raise TmdlInspectionError("Model Inspector requiere una definición TMDL.")
    return inspect_tmdl_parts(
        parts,
        include_measures=include_measures,
        include_columns=include_columns,
        include_expressions=include_expressions,
        max_expression_chars=max_expression_chars,
        max_items=max_items,
    )


def inspect_tmdl_parts(
    parts: dict[str, bytes],
    *,
    include_measures: bool = False,
    include_columns: bool = False,
    include_expressions: bool = False,
    max_expression_chars: int = 2_000,
    max_items: int = 500,
) -> dict[str, Any]:
    """Resume TMDL sin ejecutar DAX ni asumir semántica no declarada."""
    if max_expression_chars < 0 or max_expression_chars > 20_000:
        raise ValueError("max_expression_chars debe estar entre 0 y 20000.")
    if max_items < 1 or max_items > 5_000:
        raise ValueError("max_items debe estar entre 1 y 5000.")

    texts = _decode_tmdl_parts(parts)
    table_docs = {path: text for path, text in texts.items() if "/tables/" in f"/{path.casefold()}"}
    relationship_docs = {path: text for path, text in texts.items() if path.casefold().endswith("relationships.tmdl")}
    role_docs = {path: text for path, text in texts.items() if "/roles/" in f"/{path.casefold()}"}

    tables: dict[str, dict[str, Any]] = {}
    duplicate_tables: list[str] = []
    for path, text in table_docs.items():
        parsed = _parse_table_document(
            text,
            path=path,
            include_measures=include_measures,
            include_columns=include_columns,
            include_expressions=include_expressions,
            max_expression_chars=max_expression_chars,
        )
        for table in parsed:
            name = table["name"]
            if name in tables:
                duplicate_tables.append(name)
                _merge_table(tables[name], table, include_measures=include_measures, include_columns=include_columns)
            else:
                tables[name] = table

    relationships: list[dict[str, Any]] = []
    for path, text in relationship_docs.items():
        relationships.extend(_parse_relationships(text, path=path))

    roles: list[dict[str, Any]] = []
    for path, text in role_docs.items():
        roles.extend(
            _parse_roles(
                text,
                path=path,
                include_expressions=include_expressions,
                max_expression_chars=max_expression_chars,
            )
        )

    findings = _model_findings(tables, relationships, duplicate_tables)
    relationship_counts = Counter(rel.get("cross_filtering_behavior") or "NOT_EXPLICIT" for rel in relationships)
    secured_tables = sorted(
        {
            permission["table"]
            for role in roles
            for permission in role.get("table_permissions", [])
        }
    )

    ordered_tables = sorted(tables.values(), key=lambda item: item["name"].casefold())
    ordered_relationships = sorted(relationships, key=lambda item: item["name"].casefold())
    ordered_roles = sorted(roles, key=lambda item: item["name"].casefold())

    total_objects = len(ordered_tables) + len(ordered_relationships) + len(ordered_roles)
    truncated = total_objects > max_items
    remaining = max_items
    emitted_tables = ordered_tables[:remaining]
    remaining -= len(emitted_tables)
    emitted_relationships = ordered_relationships[:remaining]
    remaining -= len(emitted_relationships)
    emitted_roles = ordered_roles[:remaining]

    return {
        "format": "TMDL",
        "scope": "ACTIVE_SEMANTIC_MODEL_DEFINITION",
        "analysis_mode": "STATIC_TMDL",
        "semantic_runtime_validated": False,
        "table_count": len(ordered_tables),
        "column_count": sum(table["column_count"] for table in ordered_tables),
        "measure_count": sum(table["measure_count"] for table in ordered_tables),
        "partition_count": sum(table["partition_count"] for table in ordered_tables),
        "relationship_count": len(ordered_relationships),
        "role_count": len(ordered_roles),
        "table_permission_count": sum(len(role.get("table_permissions", [])) for role in ordered_roles),
        "rls_present": bool(secured_tables),
        "rls_secured_tables": secured_tables,
        "cross_filtering_behavior_counts": dict(sorted(relationship_counts.items())),
        "tables": emitted_tables,
        "relationships": emitted_relationships,
        "roles": emitted_roles,
        "findings": findings,
        "finding_count": len(findings),
        "items_truncated": truncated,
        "status": "REVIEW" if any(item["requires_review"] for item in findings) else "PASS",
    }


def _decode_tmdl_parts(parts: dict[str, bytes]) -> dict[str, str]:
    texts: dict[str, str] = {}
    for raw_path, payload in parts.items():
        path = raw_path.replace("\\", "/").lstrip("/")
        if not path.casefold().endswith(".tmdl"):
            continue
        try:
            texts[path] = payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise TmdlInspectionError(f"TMDL no UTF-8 en '{path}'.") from exc
    if not texts:
        raise TmdlInspectionError("La definición no contiene partes *.tmdl.")
    return texts


def _parse_table_document(
    text: str,
    *,
    path: str,
    include_measures: bool,
    include_columns: bool,
    include_expressions: bool,
    max_expression_chars: int,
) -> list[dict[str, Any]]:
    lines = text.splitlines()
    tables: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        match = _TABLE_RE.match(lines[index])
        if not match:
            index += 1
            continue
        table_indent = _indent_width(match.group("indent"))
        table = {
            "name": _unquote(match.group("name")),
            "source_path": path,
            "is_hidden": False,
            "column_count": 0,
            "measure_count": 0,
            "partition_count": 0,
            "key_columns": [],
            "hidden_column_count": 0,
            "hidden_measure_count": 0,
        }
        measures: list[dict[str, Any]] = []
        columns: list[dict[str, Any]] = []
        index += 1
        while index < len(lines):
            raw = lines[index]
            if not raw.strip():
                index += 1
                continue
            indent = _indent_width(raw)
            if indent <= table_indent:
                break

            stripped = raw.strip()
            if stripped.casefold() == "ishidden":
                table["is_hidden"] = True
                index += 1
                continue

            measure_match = _MEASURE_RE.match(raw)
            if measure_match:
                measure, next_index = _parse_measure(
                    lines,
                    index,
                    include_expression=include_expressions,
                    max_expression_chars=max_expression_chars,
                )
                table["measure_count"] += 1
                if measure["is_hidden"]:
                    table["hidden_measure_count"] += 1
                if include_measures:
                    measures.append(measure)
                index = next_index
                continue

            column_match = _COLUMN_RE.match(raw)
            if column_match:
                column, next_index = _parse_column(lines, index)
                table["column_count"] += 1
                if column["is_hidden"]:
                    table["hidden_column_count"] += 1
                if column["is_key"]:
                    table["key_columns"].append(column["name"])
                if include_columns:
                    columns.append(column)
                index = next_index
                continue

            partition_match = _PARTITION_RE.match(raw)
            if partition_match:
                table["partition_count"] += 1
            index += 1

        if include_measures:
            table["measures"] = measures
        if include_columns:
            table["columns"] = columns
        tables.append(table)
    return tables


def _parse_measure(
    lines: list[str],
    start: int,
    *,
    include_expression: bool,
    max_expression_chars: int,
) -> tuple[dict[str, Any], int]:
    match = _MEASURE_RE.match(lines[start])
    assert match is not None
    base_indent = _indent_width(match.group("indent"))
    same_line_expr = match.group("expr").strip()
    block_lines, properties, next_index = _collect_object_body(lines, start + 1, base_indent, _MEASURE_PROPERTY_KEYS)
    expression = same_line_expr or "\n".join(block_lines).strip()
    result = {
        "name": _unquote(match.group("name")),
        "is_hidden": properties.get("ishidden") is True,
        "format_string": properties.get("formatstring"),
        "display_folder": properties.get("displayfolder"),
        "expression_chars": len(expression),
        "expression_sha256": _sha256_text(expression) if expression else None,
        "references": _extract_dax_references(expression),
        "dependency_mode": "STATIC_LEXICAL",
    }
    if include_expression:
        result["expression"] = expression[:max_expression_chars]
        result["expression_truncated"] = len(expression) > max_expression_chars
    return result, next_index


def _parse_column(lines: list[str], start: int) -> tuple[dict[str, Any], int]:
    match = _COLUMN_RE.match(lines[start])
    assert match is not None
    base_indent = _indent_width(match.group("indent"))
    properties: dict[str, Any] = {}
    index = start + 1
    while index < len(lines):
        raw = lines[index]
        if not raw.strip():
            index += 1
            continue
        if _indent_width(raw) <= base_indent:
            break
        prop = _PROPERTY_RE.match(raw)
        flag = _FLAG_RE.match(raw)
        if prop:
            properties[prop.group("key").casefold()] = _strip_property_value(prop.group("value"))
        elif flag:
            properties[flag.group("key").casefold()] = True
        index += 1
    return {
        "name": _unquote(match.group("name")),
        "data_type": properties.get("datatype"),
        "is_hidden": properties.get("ishidden") is True,
        "is_key": properties.get("iskey") is True,
        "source_column": properties.get("sourcecolumn"),
        "summarize_by": properties.get("summarizeby"),
    }, index


def _parse_relationships(text: str, *, path: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    relationships: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        match = _REL_RE.match(lines[index])
        if not match:
            index += 1
            continue
        base_indent = _indent_width(match.group("indent"))
        props: dict[str, Any] = {}
        index += 1
        while index < len(lines):
            raw = lines[index]
            if not raw.strip():
                index += 1
                continue
            if _indent_width(raw) <= base_indent:
                break
            prop = _PROPERTY_RE.match(raw)
            flag = _FLAG_RE.match(raw)
            if prop:
                props[prop.group("key").casefold()] = _strip_property_value(prop.group("value"))
            elif flag:
                props[flag.group("key").casefold()] = True
            index += 1

        from_ref = _parse_object_reference(props.get("fromcolumn"))
        to_ref = _parse_object_reference(props.get("tocolumn"))
        relationships.append(
            {
                "name": _unquote(match.group("name")),
                "source_path": path,
                "from_column": props.get("fromcolumn"),
                "to_column": props.get("tocolumn"),
                "from_table": from_ref[0],
                "from_column_name": from_ref[1],
                "to_table": to_ref[0],
                "to_column_name": to_ref[1],
                "from_cardinality": props.get("fromcardinality"),
                "to_cardinality": props.get("tocardinality"),
                "cardinality_explicit": bool(props.get("fromcardinality") or props.get("tocardinality")),
                "cross_filtering_behavior": props.get("crossfilteringbehavior"),
                "security_filtering_behavior": props.get("securityfilteringbehavior"),
                "is_active": props.get("isactive", True),
            }
        )
    return relationships


def _parse_roles(
    text: str,
    *,
    path: str,
    include_expressions: bool,
    max_expression_chars: int,
) -> list[dict[str, Any]]:
    lines = text.splitlines()
    roles: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        match = _ROLE_RE.match(lines[index])
        if not match:
            index += 1
            continue
        role_indent = _indent_width(match.group("indent"))
        role = {
            "name": _unquote(match.group("name")),
            "source_path": path,
            "model_permission": None,
            "table_permissions": [],
        }
        index += 1
        while index < len(lines):
            raw = lines[index]
            if not raw.strip():
                index += 1
                continue
            indent = _indent_width(raw)
            if indent <= role_indent:
                break
            prop = _PROPERTY_RE.match(raw)
            if prop and prop.group("key").casefold() == "modelpermission":
                role["model_permission"] = _strip_property_value(prop.group("value"))
                index += 1
                continue
            permission_match = _PERMISSION_RE.match(raw)
            if permission_match:
                permission, next_index = _parse_permission(
                    lines,
                    index,
                    include_expression=include_expressions,
                    max_expression_chars=max_expression_chars,
                )
                role["table_permissions"].append(permission)
                index = next_index
                continue
            index += 1
        roles.append(role)
    return roles


def _parse_permission(
    lines: list[str],
    start: int,
    *,
    include_expression: bool,
    max_expression_chars: int,
) -> tuple[dict[str, Any], int]:
    match = _PERMISSION_RE.match(lines[start])
    assert match is not None
    base_indent = _indent_width(match.group("indent"))
    same_line_expr = match.group("expr").strip()
    block_lines, _properties, next_index = _collect_object_body(lines, start + 1, base_indent, _PERMISSION_PROPERTY_KEYS)
    expression = same_line_expr or "\n".join(block_lines).strip()
    result = {
        "table": _unquote(match.group("name")),
        "filter_present": bool(expression),
        "filter_chars": len(expression),
        "filter_sha256": _sha256_text(expression) if expression else None,
        "references": _extract_dax_references(expression),
        "dependency_mode": "STATIC_LEXICAL",
    }
    if include_expression:
        result["filter_expression"] = expression[:max_expression_chars]
        result["filter_expression_truncated"] = len(expression) > max_expression_chars
    return result, next_index


def _collect_object_body(
    lines: list[str],
    start: int,
    base_indent: int,
    property_keys: set[str],
) -> tuple[list[str], dict[str, Any], int]:
    expression_lines: list[str] = []
    properties: dict[str, Any] = {}
    index = start
    while index < len(lines):
        raw = lines[index]
        if not raw.strip():
            index += 1
            continue
        if _indent_width(raw) <= base_indent:
            break
        prop = _PROPERTY_RE.match(raw)
        flag = _FLAG_RE.match(raw)
        if prop and prop.group("key").casefold() in property_keys:
            properties[prop.group("key").casefold()] = _strip_property_value(prop.group("value"))
        elif flag and flag.group("key").casefold() in property_keys:
            properties[flag.group("key").casefold()] = True
        else:
            expression_lines.append(raw.strip())
        index += 1
    return expression_lines, properties, index


def _model_findings(
    tables: dict[str, dict[str, Any]],
    relationships: list[dict[str, Any]],
    duplicate_tables: list[str],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for name in sorted(set(duplicate_tables)):
        findings.append(
            {
                "kind": "DUPLICATE_TABLE_DECLARATION",
                "severity": "HIGH",
                "requires_review": True,
                "table": name,
            }
        )

    known_tables = set(tables)
    for relationship in relationships:
        behavior = str(relationship.get("cross_filtering_behavior") or "").casefold()
        if behavior == "bothdirections":
            findings.append(
                {
                    "kind": "BIDIRECTIONAL_RELATIONSHIP",
                    "severity": "MEDIUM",
                    "requires_review": True,
                    "relationship": relationship["name"],
                    "from_column": relationship.get("from_column"),
                    "to_column": relationship.get("to_column"),
                }
            )
        for side in ("from", "to"):
            table = relationship.get(f"{side}_table")
            if table and table not in known_tables:
                findings.append(
                    {
                        "kind": "RELATIONSHIP_TABLE_NOT_FOUND",
                        "severity": "HIGH",
                        "requires_review": True,
                        "relationship": relationship["name"],
                        "side": side,
                        "table": table,
                    }
                )
    return findings


def _merge_table(
    target: dict[str, Any],
    source: dict[str, Any],
    *,
    include_measures: bool,
    include_columns: bool,
) -> None:
    for key in ("column_count", "measure_count", "partition_count", "hidden_column_count", "hidden_measure_count"):
        target[key] += source[key]
    target["is_hidden"] = target["is_hidden"] or source["is_hidden"]
    target["key_columns"] = sorted(set(target["key_columns"] + source["key_columns"]))
    if include_measures:
        target.setdefault("measures", []).extend(source.get("measures", []))
    if include_columns:
        target.setdefault("columns", []).extend(source.get("columns", []))


def _extract_dax_references(expression: str) -> list[dict[str, str | None]]:
    if not expression:
        return []
    refs: set[tuple[str | None, str]] = set()
    for match in _TABLE_REF_RE.finditer(expression):
        table = (match.group(1) or match.group(2) or "").replace("''", "'").strip()
        refs.add((table, match.group(3).strip()))
    for match in _MEASURE_REF_RE.finditer(expression):
        name = match.group(1).strip()
        if not any(column == name for _table, column in refs):
            refs.add((None, name))
    return [
        {"table": table, "object": name}
        for table, name in sorted(refs, key=lambda item: ((item[0] or "").casefold(), item[1].casefold()))
    ]


def _parse_object_reference(value: Any) -> tuple[str | None, str | None]:
    if not isinstance(value, str) or not value.strip():
        return None, None
    text = value.strip()
    in_quote = False
    split_at = -1
    index = 0
    while index < len(text):
        char = text[index]
        if char == "'":
            if in_quote and index + 1 < len(text) and text[index + 1] == "'":
                index += 2
                continue
            in_quote = not in_quote
        elif char == "." and not in_quote:
            split_at = index
        index += 1
    if split_at < 0:
        return None, _unquote(text)
    return _unquote(text[:split_at].strip()), _unquote(text[split_at + 1 :].strip())


def _strip_property_value(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1].replace('""', '"')
    return text


def _unquote(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1].replace("''", "'")
    return text


def _indent_width(value: str) -> int:
    prefix = value[: len(value) - len(value.lstrip(" \t"))]
    return sum(4 if char == "\t" else 1 for char in prefix)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
