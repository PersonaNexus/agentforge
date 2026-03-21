"""Settings API routes."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from agentforge.llm.client import _detect_provider

router = APIRouter(tags=["settings"])


class SettingsResponse(BaseModel):
    api_key: str
    provider: str
    default_model: str
    output_dir: str
    default_culture: str | None
    batch_parallel: int


class SettingsUpdate(BaseModel):
    api_key: str = ""
    provider: str = "auto"
    default_model: str = "claude-sonnet-4-20250514"
    output_dir: str = "."
    default_culture: str | None = None
    batch_parallel: int = 1


class ValidateKeyRequest(BaseModel):
    api_key: str


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "***"
    return key[:4] + "..." + key[-4:]


@router.get("/settings", response_model=SettingsResponse)
async def get_settings() -> SettingsResponse:
    from agentforge.config import load_config

    config = load_config()
    return SettingsResponse(
        api_key=_mask_key(config.api_key) if config.api_key else "",
        provider=config.provider,
        default_model=config.default_model,
        output_dir=config.output_dir,
        default_culture=config.default_culture,
        batch_parallel=config.batch_parallel,
    )


@router.post("/settings")
async def save_settings(data: SettingsUpdate) -> dict:
    from agentforge.config import AgentForgeConfig, save_config

    config = AgentForgeConfig(
        api_key=data.api_key,
        provider=data.provider,
        default_model=data.default_model,
        output_dir=data.output_dir,
        default_culture=data.default_culture,
        batch_parallel=data.batch_parallel,
    )
    save_config(config)
    return {"saved": True}


@router.post("/settings/validate-key")
async def validate_key(data: ValidateKeyRequest) -> dict:
    if not data.api_key:
        return {"valid": False, "error": "No API key provided"}

    provider = _detect_provider(data.api_key)

    try:
        if provider == "anthropic":
            import anthropic

            client = anthropic.Anthropic(api_key=data.api_key)
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}],
            )
        else:
            import openai

            client = openai.OpenAI(api_key=data.api_key)
            client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}],
            )
        return {"valid": True, "provider": provider}
    except Exception as e:
        return {"valid": False, "provider": provider, "error": "Key validation failed"}
