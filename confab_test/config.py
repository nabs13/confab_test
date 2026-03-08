"""Configuration loading from config.yaml."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_CONFIG: dict[str, Any] = {
    "ollama": {
        "base_url": "http://127.0.0.1:11434",
        "default_model": "qwen3.5",
        "timeout": 120,
    },
    "tests": {
        "categories": [
            "tool_fabrication",
            "link_verification",
            "temporal_consistency",
            "citation_fabrication",
            "self_knowledge",
            "correction_persistence",
            "number_fabrication",
        ],
        "repetitions": 1,
        "delay_between": 5,
    },
    "verifiers": {
        "url_timeout": 10,
        "rate_limit": 1.0,
    },
    "reporting": {
        "output_dir": "~/confab_test/reports",
        "format": "markdown",
    },
    "logging": {
        "db_path": "~/confab_test/confab_results.db",
        "verbose": False,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load and merge config from YAML file with defaults."""
    config = dict(_DEFAULT_CONFIG)

    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.yaml"

    config_path = Path(config_path).expanduser()
    if config_path.exists():
        with open(config_path) as f:
            user_config = yaml.safe_load(f) or {}
        config = _deep_merge(config, user_config)

    # Expand ~ in paths
    config["reporting"]["output_dir"] = str(
        Path(config["reporting"]["output_dir"]).expanduser()
    )
    config["logging"]["db_path"] = str(
        Path(config["logging"]["db_path"]).expanduser()
    )

    return config
