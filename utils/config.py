import os
import re
from pathlib import Path
from functools import lru_cache
from typing import Any

import yaml


def _resolve_env_vars(value: Any) -> Any:
    """Recursively resolve ${ENV_VAR} references in config values."""
    if isinstance(value, str):
        pattern = re.compile(r"\$\{(\w+)\}")
        def replacer(match):
            env_key = match.group(1)
            return os.environ.get(env_key, match.group(0))
        return pattern.sub(replacer, value)
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value


def load_yaml(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return _resolve_env_vars(raw)


@lru_cache(maxsize=1)
def get_settings() -> dict:
    config_path = Path(__file__).parent.parent / "config" / "settings.yaml"
    return load_yaml(config_path)


def get_rss_config() -> dict:
    config_path = Path(__file__).parent.parent / "config" / "topics_rss.yaml"
    return load_yaml(config_path)
