from artel_powerplatform_mcp import microsoft_cli


def test_sanitize_redacts_tokens_and_signed_urls():
    text = "Authorization: Bearer secret access_token=abc123 https://x.test?a=1&sig=topsecret"
    result = microsoft_cli._sanitize(text)
    assert "secret" not in result
    assert "abc123" not in result
    assert "topsecret" not in result
    assert "[REDACTED]" in result


def test_validate_pbir_missing_path_does_not_launch_process(tmp_path):
    result = microsoft_cli.validate_pbir(str(tmp_path / "missing.Report"))
    assert result["status"] == "FAIL"
    assert result["reason"] == "PATH_NOT_FOUND"
    assert result["secrets_returned"] is False


def test_desktop_manifest_rejects_invalid_pid_without_process():
    result = microsoft_cli.desktop_manifest(0)
    assert result["status"] == "FAIL"
    assert result["reason"] == "INVALID_PID"
    assert result["writes"] == 0


def test_missing_executable_is_blocked(monkeypatch):
    monkeypatch.setattr(microsoft_cli, "which", lambda _: None)
    result = microsoft_cli._run("powerbi-desktop", ["status"])
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "EXECUTABLE_NOT_FOUND"
    assert result["secrets_returned"] is False
