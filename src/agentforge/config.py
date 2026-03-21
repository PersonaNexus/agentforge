"""Configuration management for AgentForge."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

_CONFIG_DIR = Path.home() / ".agentforge"
_CONFIG_FILE = _CONFIG_DIR / "config.yaml"


class AgentForgeConfig(BaseModel):
    """AgentForge configuration model."""

    api_key: str = ""
    provider: str = Field(
        default="auto",
        description="LLM provider: 'auto' (detect from key), 'anthropic', or 'openai'",
    )
    default_model: str = "claude-sonnet-4-20250514"
    output_dir: str = "."
    default_culture: str | None = None
    batch_parallel: int = Field(default=1, ge=1)
    web_api_token: str | None = Field(
        default=None,
        description="Bearer token for web API authentication. Set to 'disabled' to opt out.",
    )


def load_config(config_path: Path | None = None) -> AgentForgeConfig:
    """Load configuration from YAML file.

    Falls back to defaults if config file doesn't exist.
    """
    path = config_path or _CONFIG_FILE
    if not path.exists():
        return AgentForgeConfig()

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not data or not isinstance(data, dict):
        return AgentForgeConfig()

    return AgentForgeConfig.model_validate(data)


def save_config(config: AgentForgeConfig, config_path: Path | None = None) -> Path:
    """Save configuration to YAML file."""
    path = config_path or _CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(exclude_none=True)
    # Note: API key is stored in plaintext; file permissions are restricted to 0o600
    yaml_str = yaml.dump(data, default_flow_style=False, sort_keys=False)
    path.write_text(yaml_str, encoding="utf-8")
    # Restrict file permissions (owner read/write only)
    path.chmod(0o600)
    return path
