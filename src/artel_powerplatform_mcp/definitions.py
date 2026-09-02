from __future__ import annotations

import base64
import binascii
import json
from typing import Any


class DefinitionDecodeError(RuntimeError):
    """La definición Fabric no pudo decodificarse de forma segura."""


_TEXT_EXTENSIONS = (
    ".json",
    ".tmdl",
    ".pbir",
    ".pbism",
    ".txt",
    ".md",
)


def summarize_definition(
    response: dict[str, Any],
    *,
    include_content: bool = False,
    max_content_chars: int = 20_000,
    max_total_bytes: int = 25_000_000,
) -> dict[str, Any]:
    """Convierte una respuesta getDefinition en un contrato compacto y seguro.

    Por defecto no devuelve payload decodificado. Cuando include_content=True,
    max_content_chars funciona como presupuesto TOTAL compartido entre todas las partes.
    """

    if max_content_chars < 0 or max_content_chars > 200_000:
        raise ValueError("max_content_chars debe estar entre 0 y 200000.")

    definition = response.get("definition")
    if not isinstance(definition, dict):
        raise DefinitionDecodeError("Fabric no devolvió un objeto 'definition' válido.")

    raw_parts = definition.get("parts")
    if not isinstance(raw_parts, list):
        raise DefinitionDecodeError("Fabric no devolvió una lista 'parts' válida.")

    parts: list[dict[str, Any]] = []
    total_bytes = 0
    remaining_chars = max_content_chars

    for raw_part in raw_parts:
        if not isinstance(raw_part, dict):
            continue
        path = str(raw_part.get("path") or "")
        payload_type = str(raw_part.get("payloadType") or "")
        payload = raw_part.get("payload")
        if not path or payload_type != "InlineBase64" or not isinstance(payload, str):
            raise DefinitionDecodeError("La definición contiene una parte no soportada o incompleta.")

        decoded = _decode_inline_base64(payload, path)

        total_bytes += len(decoded)
        if total_bytes > max_total_bytes:
            raise DefinitionDecodeError("La definición excede el límite seguro de 25 MB decodificados.")

        item: dict[str, Any] = {
            "path": path,
            "payload_type": payload_type,
            "bytes": len(decoded),
            "textual": _is_textual_path(path),
        }

        if include_content and item["textual"] and remaining_chars > 0:
            try:
                text = decoded.decode("utf-8")
            except UnicodeDecodeError:
                item["textual"] = False
            else:
                budget = min(len(text), remaining_chars)
                item["content"] = text[:budget]
                item["content_truncated"] = len(text) > budget
                remaining_chars -= budget
                if path.lower().endswith((".json", ".pbir", ".pbism")):
                    try:
                        json.loads(text)
                    except ValueError:
                        item["json_valid"] = False
                    else:
                        item["json_valid"] = True
        elif include_content and item["textual"]:
            item["content_omitted_due_to_budget"] = True

        parts.append(item)

    paths = [part["path"] for part in parts]
    return {
        "format": definition.get("format"),
        "part_count": len(parts),
        "total_decoded_bytes": total_bytes,
        "paths": paths,
        "parts": parts,
        "content_included": include_content,
        "content_budget_chars": max_content_chars,
        "content_budget_remaining": remaining_chars,
    }


def _decode_inline_base64(payload: str, path: str) -> bytes:
    normalized = payload.strip()
    padding = "=" * ((4 - len(normalized) % 4) % 4)
    try:
        return base64.b64decode(normalized + padding, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DefinitionDecodeError(f"Payload Base64 inválido en la parte '{path}'.") from exc


def _is_textual_path(path: str) -> bool:
    lower = path.lower()
    return lower.endswith(_TEXT_EXTENSIONS) or "/definition/" in f"/{lower}" or lower.startswith("definition/")
