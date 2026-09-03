from pathlib import Path

from artel_powerplatform_mcp.auth import AuthBroker
from artel_powerplatform_mcp.config import (
    FABRIC_DEFAULT_SCOPES,
    POWERBI_DEFAULT_SCOPES,
    POWERPLATFORM_DEFAULT_SCOPES,
    Settings,
)


def make_settings(**overrides):
    values = {
        "bi_project_path": Path("C:/tmp/bi"),
        "allow_writes": False,
        "entra_client_id": "11111111-2222-3333-4444-555555555555",
        "entra_tenant": "organizations",
        "fabric_access_token": None,
        "fabric_api_base_url": "https://api.fabric.microsoft.com/v1",
        "fabric_scopes": FABRIC_DEFAULT_SCOPES,
        "powerbi_access_token": None,
        "powerbi_api_base_url": "https://api.powerbi.com/v1.0/myorg",
        "powerbi_dataset_id": None,
        "powerbi_scopes": POWERBI_DEFAULT_SCOPES,
        "powerplatform_access_token": None,
        "powerplatform_api_base_url": "https://api.powerplatform.com",
        "powerplatform_scopes": POWERPLATFORM_DEFAULT_SCOPES,
    }
    values.update(overrides)
    return Settings(**values)


def test_auth_status_never_returns_environment_token_value():
    secret = "super-secret-token-value"
    broker = AuthBroker(settings_loader=lambda: make_settings(fabric_access_token=secret))
    result = broker.status("fabric")
    assert result["authenticated"] is True
    assert result["token_source"] == "environment"
    assert secret not in str(result)


def test_device_code_flow_stores_token_only_in_memory():
    captured = {}

    class FakeApplication:
        def initiate_device_flow(self, scopes):
            captured["scopes"] = scopes
            return {
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://microsoft.com/devicelogin",
                "message": "Sign in",
                "expires_in": 900,
                "device_code": "internal-device-code",
            }

        def acquire_token_by_device_flow(self, flow):
            assert flow["device_code"] == "internal-device-code"
            return {"access_token": "memory-only-access-token", "expires_in": 3600}

    def factory(**kwargs):
        captured["factory"] = kwargs
        return FakeApplication()

    broker = AuthBroker(settings_loader=make_settings, application_factory=factory)
    begin = broker.begin_device_flow("fabric")
    assert begin["token_returned"] is False
    assert "device_code" not in begin
    assert "internal-device-code" not in str(begin)
    assert captured["scopes"] == list(FABRIC_DEFAULT_SCOPES)

    completed = broker.complete_device_flow(begin["flow_id"])
    assert completed["authenticated"] is True
    assert completed["token_returned"] is False
    assert completed["token_persisted_to_disk"] is False
    assert "memory-only-access-token" not in str(completed)
    assert broker.get_token("fabric") == "memory-only-access-token"

    status = broker.status("fabric")
    assert status["token_source"] == "memory"
    assert "memory-only-access-token" not in str(status)


def test_powerplatform_device_code_uses_official_default_scope():
    captured = {}

    class FakeApplication:
        def initiate_device_flow(self, scopes):
            captured["scopes"] = scopes
            return {
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://microsoft.com/devicelogin",
                "message": "Sign in",
                "expires_in": 900,
                "device_code": "internal-device-code",
            }

    broker = AuthBroker(settings_loader=make_settings, application_factory=lambda **kwargs: FakeApplication())
    begin = broker.begin_device_flow("powerplatform")
    assert begin["token_returned"] is False
    assert captured["scopes"] == list(POWERPLATFORM_DEFAULT_SCOPES)


def test_environment_token_has_priority_over_memory_token():
    settings = {"value": make_settings(fabric_access_token=None)}
    broker = AuthBroker(settings_loader=lambda: settings["value"])
    broker._memory_tokens["fabric"] = "memory-token"
    settings["value"] = make_settings(fabric_access_token="environment-token")
    assert broker.get_token("fabric") == "environment-token"
