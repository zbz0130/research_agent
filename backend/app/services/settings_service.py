from collections.abc import Iterable

from app.config import Settings
from app.schemas import ApiKeySlot, ApiKeyStatusResponse, ApiKeyUpdate
from pydantic import SecretStr


def mask_secret(secret: str | None) -> str | None:
    """Return a short identifier without exposing the credential."""

    if not secret:
        return None
    if len(secret) <= 4:
        return "••••"
    return f"••••••••{secret[-4:]}"


def api_key_slots(settings: Settings) -> Iterable[ApiKeySlot]:
    definitions = (
        (
            "paper_search",
            "论文检索",
            settings.paper_provider,
            settings.paper_api_key,
            "WISHFORGE_PAPER_API_KEY",
        ),
        (
            "explanation_model",
            "解释模型",
            settings.explanation_provider,
            settings.explanation_api_key,
            "WISHFORGE_EXPLANATION_API_KEY",
        ),
        (
            "experiment_runner",
            "实验执行",
            settings.experiment_provider,
            settings.experiment_api_key,
            "WISHFORGE_EXPERIMENT_API_KEY",
        ),
    )

    for slot_id, label, provider, secret, environment_variable in definitions:
        raw_secret = secret.get_secret_value() if secret is not None else None
        yield ApiKeySlot(
            id=slot_id,
            label=label,
            provider=provider,
            configured=bool(raw_secret),
            masked=mask_secret(raw_secret),
            environment_variable=environment_variable,
        )


def api_key_status(settings: Settings) -> ApiKeyStatusResponse:
    """Build the public status view without ever serializing a secret."""

    runtime_slots = getattr(settings, "_runtime_api_key_slots", set())
    storage = "runtime_memory" if runtime_slots else "environment"
    return ApiKeyStatusResponse(slots=list(api_key_slots(settings)), storage=storage)


def update_api_keys(settings: Settings, payload: ApiKeyUpdate) -> ApiKeyStatusResponse:
    """Apply a local, process-memory credential overlay.

    The provider services construct their clients for each job, so changing a
    setting here takes effect for subsequent requests without restarting the
    API.  We deliberately do not persist these values to SQLite or echo them
    in the response.
    """

    slot_to_attribute = {
        "paper_search": "paper_api_key",
        "explanation_model": "explanation_api_key",
        "experiment_runner": "experiment_api_key",
    }
    values = payload.model_dump(exclude_unset=True)
    runtime_slots = getattr(settings, "_runtime_api_key_slots", None)
    if runtime_slots is None:
        runtime_slots = set()
        setattr(settings, "_runtime_api_key_slots", runtime_slots)
    for slot_id, raw_value in values.items():
        attribute = slot_to_attribute[slot_id]
        # An empty value is an explicit clear operation.  Never log or retain
        # a second plain-string copy of a credential.
        setattr(settings, attribute, SecretStr(raw_value) if raw_value else None)
        runtime_slots.add(slot_id)
    return api_key_status(settings)
