import base64

import pytest

from artel_powerplatform_mcp.definitions import DefinitionDecodeError, summarize_definition


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def test_definition_manifest_hides_payload_by_default():
    encoded = _b64('{"displayName":"Resumen"}')
    source = {
        "definition": {
            "format": "PBIR",
            "parts": [
                {
                    "path": "definition/pages/page1/page.json",
                    "payload": encoded,
                    "payloadType": "InlineBase64",
                }
            ],
        }
    }

    result = summarize_definition(source)

    assert result["format"] == "PBIR"
    assert result["part_count"] == 1
    assert "content" not in result["parts"][0]
    assert encoded not in str(result)
    assert result["parts"][0]["payload_type"] == "InlineBase64"


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


def test_definition_accepts_unpadded_base64():
    encoded = _b64("hello Fabric").rstrip("=")
    source = {
        "definition": {
            "format": "PBIR",
            "parts": [
                {"path": "definition.pbir", "payload": encoded, "payloadType": "InlineBase64"}
            ],
        }
    }

    result = summarize_definition(source, include_content=True)
    assert result["parts"][0]["content"] == "hello Fabric"


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
