from collections.abc import Iterable

from app.config import Settings
from app.schemas import ApiKeySlot


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
