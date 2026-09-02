import base64

import pytest

from artel_powerplatform_mcp.definitions import DefinitionDecodeError, summarize_definition


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def test_definition_manifest_hides_payload_by_default():
    source = {
        "definition": {
            "format": "PBIR",
            "parts": [
                {
                    "path": "definition/pages/page1/page.json",
                    "payload": _b64('{"displayName":"Resumen"}'),
                    "payloadType": "InlineBase64",
                }
            ],
        }
    }

    result = summarize_definition(source)

    assert result["format"] == "PBIR"
    assert result["part_count"] == 1
    assert result["parts"][0]["json_valid"] if "json_valid" in result["parts"][0] else True
    assert "content" not in result["parts"][0]
    assert "payload" not in str(result)


def test_definition_content_uses_shared_budget():
    source = {
        "definition": {
            "format": "TMDL",
            "parts": [
                {"path": "definition/model.tmdl", "payload": _b64("abcdefghij"), "payloadType": "InlineBase64"},
                {"path": "definition/tables/a.tmdl", "payload": _b64("klmnopqrst"), "payloadType": "InlineBase64"},
            ],
        }
    }

    result = summarize_definition(source, include_content=True, max_content_chars=12)

    assert result["parts"][0]["content"] == "abcdefghij"
    assert result["parts"][1]["content"] == "kl"
    assert result["parts"][1]["content_truncated"] is True
    assert result["content_budget_remaining"] == 0


def test_definition_rejects_invalid_base64():
    source = {
        "definition": {
            "parts": [
                {"path": "definition/model.tmdl", "payload": "not-base64!", "payloadType": "InlineBase64"}
            ]
        }
    }

    with pytest.raises(DefinitionDecodeError, match="Base64 inválido"):
        summarize_definition(source)
