from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal
from uuid import uuid4

import msal

from .config import Settings, load_settings

AuthResource = Literal["fabric", "powerbi", "powerplatform"]


class AuthConfigurationError(RuntimeError):
    """La autenticación solicitada no está configurada."""


class AuthFlowError(RuntimeError):
    """El flujo de autenticación no pudo completarse de forma segura."""


@dataclass
class PendingDeviceFlow:
    application: Any
    flow: dict[str, Any]
    resource: AuthResource


class AuthBroker:
    """Resuelve tokens sin exponerlos a las tools MCP.

    Prioridad:
    1. token suministrado por variable de entorno;
    2. token adquirido por MSAL y conservado únicamente en memoria.

    La V1.2 no persiste access/refresh tokens en disco.
    """

    def __init__(
        self,
        *,
        settings_loader: Callable[[], Settings] = load_settings,
        application_factory: Callable[..., Any] = msal.PublicClientApplication,
    ) -> None:
        self._settings_loader = settings_loader
        self._application_factory = application_factory
        self._memory_tokens: dict[AuthResource, str] = {}
        self._pending: dict[str, PendingDeviceFlow] = {}

    def status(self, resource: AuthResource) -> dict[str, Any]:
        settings = self._settings_loader()
        env_token = self._environment_token(settings, resource)
        source = "environment" if env_token else "memory" if resource in self._memory_tokens else "none"
        return {
            "resource": resource,
            "authenticated": source != "none",
            "token_source": source,
            "device_code_available": bool(settings.entra_client_id and settings.entra_tenant),
            "token_persisted_to_disk": False,
        }

    def get_token(self, resource: AuthResource) -> str:
        settings = self._settings_loader()
        env_token = self._environment_token(settings, resource)
        if env_token:
            return env_token
        token = self._memory_tokens.get(resource)
        if token:
            return token
        raise AuthConfigurationError(
            f"No hay autenticación disponible para {resource}; configura token de entorno o inicia Device Code Flow."
        )

    def begin_device_flow(self, resource: AuthResource) -> dict[str, Any]:
        settings = self._settings_loader()
        if not settings.entra_client_id or not settings.entra_tenant:
            raise AuthConfigurationError(
                "Configura ENTRA_CLIENT_ID y ENTRA_TENANT_ID antes de iniciar autenticación interactiva."
            )

        scopes = self._scopes(settings, resource)
        if not scopes:
            raise AuthConfigurationError(
                f"No hay scopes configurados para {resource}; define los permisos delegados mínimos requeridos."
            )

        authority = f"https://login.microsoftonline.com/{settings.entra_tenant}"
        application = self._application_factory(
            client_id=settings.entra_client_id,
            authority=authority,
        )
        flow = application.initiate_device_flow(scopes=list(scopes))
        if "user_code" not in flow:
            error = str(flow.get("error") or "DEVICE_FLOW_NOT_AVAILABLE")
            raise AuthFlowError(f"Microsoft Entra no pudo iniciar Device Code Flow: {error}.")

        flow_id = str(uuid4())
        self._pending[flow_id] = PendingDeviceFlow(application, flow, resource)

        return {
            "flow_id": flow_id,
            "resource": resource,
            "user_code": flow.get("user_code"),
            "verification_uri": flow.get("verification_uri") or flow.get("verification_url"),
            "message": flow.get("message"),
            "expires_in": flow.get("expires_in"),
            "token_returned": False,
        }

    def complete_device_flow(self, flow_id: str) -> dict[str, Any]:
        pending = self._pending.get(flow_id)
        if not pending:
            raise AuthFlowError("flow_id inexistente, expirado o ya completado.")

        result = pending.application.acquire_token_by_device_flow(pending.flow)
        access_token = result.get("access_token")
        if not access_token:
            error = str(result.get("error") or "AUTHENTICATION_FAILED")
            description = str(result.get("error_description") or "")
            safe_description = description.split("Trace ID:", 1)[0].strip()
            raise AuthFlowError(
                f"Autenticación no completada: {error}. {safe_description}".strip()
            )

        self._memory_tokens[pending.resource] = str(access_token)
        self._pending.pop(flow_id, None)
        return {
            "resource": pending.resource,
            "authenticated": True,
            "token_source": "memory",
            "token_returned": False,
            "token_persisted_to_disk": False,
        }

    def clear_memory_token(self, resource: AuthResource) -> None:
        self._memory_tokens.pop(resource, None)

    @staticmethod
    def _environment_token(settings: Settings, resource: AuthResource) -> str | None:
        if resource == "fabric":
            return settings.fabric_access_token
        if resource == "powerbi":
            return settings.powerbi_access_token
        return settings.powerplatform_access_token

    @staticmethod
    def _scopes(settings: Settings, resource: AuthResource) -> tuple[str, ...]:
        if resource == "fabric":
            return settings.fabric_scopes
        if resource == "powerbi":
            return settings.powerbi_scopes
        return settings.powerplatform_scopes
