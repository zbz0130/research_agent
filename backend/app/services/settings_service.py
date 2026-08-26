"""Safe, purpose-separated runtime configuration for external providers.

Credentials deliberately travel through a different endpoint and are never
stored in the runtime-settings response.  This keeps the ordinary web UI
useful in development while allowing the Tauri host to persist only the
non-secret values in its application-data directory.
"""

from __future__ import annotations

from collections.abc import Iterable
from time import monotonic
from typing import Literal
from urllib.parse import urlparse

import httpx
from pydantic import SecretStr

from app.config import Settings
from app.schemas import (
    ApiKeySlot,
    ApiKeyStatusResponse,
    ApiKeyUpdate,
    ProviderConnectionTestResponse,
    ProviderRuntimeSlot,
    ProviderRuntimeSlotUpdate,
    ProviderSlotId,
    RuntimeProviderSettings,
    RuntimeProviderSettingsUpdate,
)


_SLOT_CONFIG: dict[ProviderSlotId, dict[str, object]] = {
    "paper_search": {
        "label": "论文检索",
        "provider_attr": "paper_provider",
        "base_url_attr": "paper_base_url",
        "model_attr": "paper_model",
        "enabled_attr": "paper_enabled",
        "credential_attr": "paper_api_key",
        "environment_variable": "WISHFORGE_PAPER_API_KEY",
    },
    "community_search": {
        "label": "社区检索（探索性信号）",
        "provider_attr": "community_provider",
        "base_url_attr": "community_base_url",
        "model_attr": "community_model",
        "enabled_attr": "community_enabled",
        "credential_attr": "community_api_key",
        "environment_variable": "WISHFORGE_COMMUNITY_API_KEY",
    },
    "explanation_model": {
        "label": "解释模型",
        "provider_attr": "explanation_provider",
        "base_url_attr": "explanation_base_url",
        "model_attr": "explanation_model",
        "enabled_attr": "explanation_enabled",
        "credential_attr": "explanation_api_key",
        "environment_variable": "WISHFORGE_EXPLANATION_API_KEY",
    },
    "experiment_runner": {
        "label": "实验执行",
        "provider_attr": "experiment_provider",
        "base_url_attr": "experiment_base_url",
        "model_attr": "experiment_model",
        "enabled_attr": "experiment_enabled",
        "credential_attr": "experiment_api_key",
        "environment_variable": "WISHFORGE_EXPERIMENT_API_KEY",
    },
}

_SLOT_IDS: tuple[ProviderSlotId, ...] = (
    "paper_search",
    "community_search",
    "explanation_model",
    "experiment_runner",
)


def _config(slot_id: ProviderSlotId) -> dict[str, object]:
    return _SLOT_CONFIG[slot_id]


def _secret_value(settings: Settings, slot_id: ProviderSlotId) -> str | None:
    secret = getattr(settings, str(_config(slot_id)["credential_attr"]), None)
    return secret.get_secret_value() if secret is not None else None


def _credential_required(slot_id: ProviderSlotId, provider: str) -> bool:
    # Public arXiv, the explicit demo fixtures, the local draft-only
    # experiment service and rule fallback do not need credentials.
    if slot_id == "paper_search" and provider in {"arxiv", "demo"}:
        return False
    if slot_id == "community_search" and provider == "demo":
        return False
    if slot_id == "explanation_model" and provider == "rule_based":
        return False
    if slot_id == "experiment_runner" and provider == "local":
        return False
    return True


def _normalize_base_url(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().rstrip("/")
    return normalized or None


def mask_secret(secret: str | None) -> str | None:
    """Return a short identifier without exposing the credential."""

    if not secret:
        return None
    if len(secret) <= 4:
        return "••••"
    return f"••••••••{secret[-4:]}"


def api_key_slots(settings: Settings) -> Iterable[ApiKeySlot]:
    for slot_id in _SLOT_IDS:
        config = _config(slot_id)
        provider = str(getattr(settings, str(config["provider_attr"])))
        raw_secret = _secret_value(settings, slot_id)
        yield ApiKeySlot(
            id=slot_id,
            label=str(config["label"]),
            provider=provider,
            configured=bool(raw_secret),
            credential_required=_credential_required(slot_id, provider),
            masked=mask_secret(raw_secret),
            environment_variable=str(config["environment_variable"]),
        )


def api_key_status(settings: Settings) -> ApiKeyStatusResponse:
    """Build the public status view without ever serializing a secret."""

    runtime_slots = getattr(settings, "_runtime_api_key_slots", set())
    storage = "runtime_memory" if runtime_slots else "environment"
    return ApiKeyStatusResponse(slots=list(api_key_slots(settings)), storage=storage)


def update_api_keys(settings: Settings, payload: ApiKeyUpdate) -> ApiKeyStatusResponse:
    """Apply a local, process-memory credential overlay.

    The desktop host additionally keeps its own copy in Windows Credential
    Manager.  The API endpoint still updates this process so a newly entered
    key takes effect without an App restart.
    """

    values = payload.model_dump(exclude_unset=True)
    runtime_slots = getattr(settings, "_runtime_api_key_slots", None)
    if runtime_slots is None:
        runtime_slots = set()
        setattr(settings, "_runtime_api_key_slots", runtime_slots)
    for slot_id, raw_value in values.items():
        config = _config(slot_id)
        attribute = str(config["credential_attr"])
        # An empty value is an explicit clear operation. Never log or retain
        # a second plain-string copy of a credential.
        setattr(settings, attribute, SecretStr(raw_value) if raw_value else None)
        runtime_slots.add(slot_id)
    return api_key_status(settings)


def runtime_provider_slots(settings: Settings) -> list[ProviderRuntimeSlot]:
    runtime_fields = getattr(settings, "_runtime_provider_slots", set())
    runtime_slot_ids = {
        entry.split(".", 1)[0] if isinstance(entry, str) else str(entry)
        for entry in runtime_fields
    }
    slots: list[ProviderRuntimeSlot] = []
    for slot_id in _SLOT_IDS:
        config = _config(slot_id)
        provider = str(getattr(settings, str(config["provider_attr"])))
        enabled = bool(getattr(settings, str(config["enabled_attr"])))
        slots.append(
            ProviderRuntimeSlot(
                id=slot_id,
                label=str(config["label"]),
                provider=provider,
                base_url=_normalize_base_url(getattr(settings, str(config["base_url_attr"]))),
                model=getattr(settings, str(config["model_attr"])),
                enabled=enabled,
                credential_required=_credential_required(slot_id, provider),
                credential_configured=bool(_secret_value(settings, slot_id)),
                storage="runtime_memory" if slot_id in runtime_slot_ids else "environment",
            )
        )
    return slots


def runtime_provider_status(settings: Settings) -> RuntimeProviderSettings:
    """Return non-secret, four-slot provider settings for the settings UI."""

    runtime_slots = getattr(settings, "_runtime_provider_slots", set())
    return RuntimeProviderSettings(
        # Compatibility fields for existing callers. New callers should use
        # the structurally separated ``slots`` list.
        explanation_provider=settings.explanation_provider,
        explanation_model=settings.explanation_model,
        explanation_base_url=settings.explanation_base_url,
        demo_mode=settings.demo_mode,
        storage="runtime_memory" if runtime_slots else "environment",
        slots=runtime_provider_slots(settings),
    )


def _record_runtime_field(settings: Settings, slot_id: ProviderSlotId, field: str) -> None:
    runtime_slots = getattr(settings, "_runtime_provider_slots", None)
    if runtime_slots is None:
        runtime_slots = set()
        setattr(settings, "_runtime_provider_slots", runtime_slots)
    runtime_slots.add(f"{slot_id}.{field}")


def update_provider_slot(
    settings: Settings,
    slot_id: ProviderSlotId,
    payload: ProviderRuntimeSlotUpdate,
) -> ProviderRuntimeSettings:
    """Update one non-secret provider slot in memory.

    Provider availability is enforced where work actually starts.  Keeping
    this endpoint configuration-only means it never starts an experiment or
    accidentally makes a broad network request while the user is editing a
    form.
    """

    values = payload.model_dump(exclude_unset=True)
    config = _config(slot_id)
    mapping = {
        "provider": str(config["provider_attr"]),
        "base_url": str(config["base_url_attr"]),
        "model": str(config["model_attr"]),
        "enabled": str(config["enabled_attr"]),
    }
    for field, value in values.items():
        attribute = mapping[field]
        if field == "base_url":
            value = _normalize_base_url(value)
        setattr(settings, attribute, value)
        _record_runtime_field(settings, slot_id, field)
    return runtime_provider_status(settings)


def update_runtime_provider_settings(
    settings: Settings,
    payload: RuntimeProviderSettingsUpdate,
) -> RuntimeProviderSettings:
    """Compatibility wrapper for the original explanation-only endpoint."""

    values = payload.model_dump(exclude_unset=True)
    mapped: dict[str, object] = {}
    if "explanation_provider" in values:
        mapped["provider"] = values["explanation_provider"]
    if "explanation_model" in values:
        mapped["model"] = values["explanation_model"]
    if "explanation_base_url" in values:
        mapped["base_url"] = values["explanation_base_url"]
    if mapped:
        update_provider_slot(
            settings,
            "explanation_model",
            ProviderRuntimeSlotUpdate.model_validate(mapped),
        )
    if "demo_mode" in values:
        settings.demo_mode = bool(values["demo_mode"])
        _record_runtime_field(settings, "explanation_model", "demo_mode")
    return runtime_provider_status(settings)


def _url_is_safe(base_url: str | None) -> bool:
    if not base_url:
        return False
    parsed = urlparse(base_url)
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and not parsed.query
        and not parsed.fragment
    )


def test_provider_connection(
    settings: Settings,
    slot_id: ProviderSlotId,
    *,
    probe: bool = False,
) -> ProviderConnectionTestResponse:
    """Return a bounded, secret-free connection status.

    Normal clicks validate the active configuration without consuming an API
    quota.  ``probe=true`` only makes a tiny unauthenticated health request
    to an explicitly configured HTTP(S) endpoint.  It deliberately does not
    send an API key, run searches, call a model, or invoke an experiment.
    """

    config = _config(slot_id)
    provider = str(getattr(settings, str(config["provider_attr"])))
    enabled = bool(getattr(settings, str(config["enabled_attr"])))
    base_url = _normalize_base_url(getattr(settings, str(config["base_url_attr"])))
    credential_required = _credential_required(slot_id, provider)
    credential_configured = bool(_secret_value(settings, slot_id))

    if not enabled:
        return ProviderConnectionTestResponse(
            slot=slot_id,
            provider=provider,
            enabled=False,
            ok=False,
            status="disabled",
            message="该服务已关闭；启用后才会在后续任务中使用。",
        )
    if credential_required and not credential_configured:
        return ProviderConnectionTestResponse(
            slot=slot_id,
            provider=provider,
            enabled=True,
            ok=False,
            status="missing_credential",
            message="该 Provider 需要对应用途的 API Key；密钥不会在连接测试中回显。",
        )
    if provider in {"demo", "rule_based", "local"}:
        return ProviderConnectionTestResponse(
            slot=slot_id,
            provider=provider,
            enabled=True,
            ok=True,
            status="ready",
            message="本地/规则 Provider 已就绪；没有发起外部网络请求。",
        )
    if slot_id == "paper_search" and provider == "arxiv" and not base_url:
        return ProviderConnectionTestResponse(
            slot=slot_id,
            provider=provider,
            enabled=True,
            ok=True,
            status="ready",
            message="arXiv 公共检索已配置；实际检索仍会遵守限流和 Provider 状态。",
        )
    if not base_url:
        return ProviderConnectionTestResponse(
            slot=slot_id,
            provider=provider,
            enabled=True,
            ok=False,
            status="invalid_configuration",
            message="请填写完整的 Base URL 后再测试连接。",
        )
    if not _url_is_safe(base_url):
        return ProviderConnectionTestResponse(
            slot=slot_id,
            provider=provider,
            enabled=True,
            ok=False,
            status="invalid_configuration",
            message="Base URL 必须是无 query 或 fragment 的完整 http:// 或 https:// 地址。",
        )
    if not probe:
        return ProviderConnectionTestResponse(
            slot=slot_id,
            provider=provider,
            enabled=True,
            ok=True,
            status="ready",
            message="配置格式有效。为避免消耗配额，未向远端发送请求；可使用 probe=true 执行无凭据连通性探测。",
        )

    started = monotonic()
    try:
        # GET / avoids credentials and a model/search payload. Some providers
        # return 401/404 on root despite being reachable, so any HTTP response
        # proves transport reachability; only network/timeout failures fail.
        response = httpx.get(base_url, timeout=3.0, follow_redirects=False)
        latency_ms = max(0, int((monotonic() - started) * 1000))
        return ProviderConnectionTestResponse(
            slot=slot_id,
            provider=provider,
            enabled=True,
            ok=True,
            status="reachable",
            message=f"远端可达（HTTP {response.status_code}）；未发送 API Key 或业务请求。",
            latency_ms=latency_ms,
        )
    except httpx.HTTPError:
        latency_ms = max(0, int((monotonic() - started) * 1000))
        return ProviderConnectionTestResponse(
            slot=slot_id,
            provider=provider,
            enabled=True,
            ok=False,
            status="unreachable",
            message="无法在 3 秒内连接该 Base URL；请检查地址、代理和网络。",
            latency_ms=latency_ms,
        )
