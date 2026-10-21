"""Friction label engine (brief sections 5.2, 13.3).

Loads the versioned YAML rule file (configs/rules/friction_v1.yaml), applies
it to per-scheme component observations, and returns the raw components plus
the composite level. Raw components are always retained so the composite can
change without re-extraction. `unknown` is never treated as `absent`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .. import settings

LEVELS = ("high", "moderate", "low", "unknown")


def load_rules(path: Path | None = None) -> dict[str, Any]:
    path = Path(path) if path else settings.FRICTION_RULES_YAML
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    version = next(key for key in data.keys() if key != "schema_version")
    return {"version": version, "rules": data[version]}


def apply_friction(components: dict[str, Any], rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """components: {component_name: observed_value}. Unknown components absent.

    Returns {"level": ..., "high_hits": [...], "moderate_hits": [...],
             "components": {...}} so raw components stay visible.
    """
    rules = rules or load_rules()
    spec = rules["rules"]
    high_any = spec.get("high_if_any", [])
    moderate_any = spec.get("moderate_if_any", [])

    high_hits = [name for name in high_any if _truthy(components.get(name))]
    moderate_hits = [name for name in moderate_any if _truthy(components.get(name))]

    if high_hits:
        level = "high"
    elif moderate_hits:
        level = "moderate"
    elif _all_absent(components, high_any + moderate_any):
        level = "low"
    else:
        level = "unknown"

    return {
        "level": level,
        "rule_version": rules["version"],
        "high_hits": high_hits,
        "moderate_hits": moderate_hits,
        "components": components,
    }


def _truthy(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    return str(value).strip().lower() in {"true", "yes", "y", "1", "present"}


def _all_absent(components: dict[str, Any], names: list[str]) -> bool:
    known = {name: components.get(name) for name in names if name in components}
    return bool(known) and not any(_truthy(value) for value in known.values())
