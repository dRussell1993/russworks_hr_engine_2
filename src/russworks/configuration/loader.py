from __future__ import annotations

from pathlib import Path
import json
from typing import Any, Mapping

from .defaults import default_user_config
from .models import (
    ConfigValidationError,
    ModuleToggleConfig,
    RiskProfileConfig,
    RussWorksUserConfig,
    SlipPreferences,
    WeightOverrideConfig,
)


DEFAULT_CONFIG_PATH = "config/russworks_config.yaml"


class ConfigLoader:
    def __init__(self, path: str | Path = DEFAULT_CONFIG_PATH) -> None:
        self.path = Path(path)

    def load(self) -> RussWorksUserConfig:
        if not self.path.exists():
            return default_user_config()
        try:
            data = self._load_mapping(self.path)
            return config_from_mapping(data, source_path=str(self.path)).validate()
        except ConfigValidationError:
            raise
        except Exception as exc:
            raise ConfigValidationError(f"Invalid Russ-Works config {self.path}: {exc}") from exc

    def _load_mapping(self, path: Path) -> dict[str, Any]:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            payload = json.loads(text)
        else:
            payload = _parse_simple_yaml(text)
        if not isinstance(payload, dict):
            raise ConfigValidationError("config root must be a mapping.")
        return payload


def load_user_config(path: str | Path = DEFAULT_CONFIG_PATH) -> RussWorksUserConfig:
    return ConfigLoader(path).load()


def config_from_mapping(data: Mapping[str, Any], *, source_path: str = "mapping") -> RussWorksUserConfig:
    defaults = default_user_config()
    toggles = _section(data, "module_toggles")
    weights = _section(data, "weight_overrides")
    slips = _section(data, "slip_preferences")
    risk = _section(data, "risk_profile")

    return RussWorksUserConfig(
        module_toggles=ModuleToggleConfig(
            use_ypi=_bool(toggles.get("use_ypi", defaults.module_toggles.use_ypi), "module_toggles.use_ypi"),
            use_veteran_bounce=_bool(toggles.get("use_veteran_bounce", defaults.module_toggles.use_veteran_bounce), "module_toggles.use_veteran_bounce"),
            use_catcher_power=_bool(toggles.get("use_catcher_power", defaults.module_toggles.use_catcher_power), "module_toggles.use_catcher_power"),
            use_pitch_mix=_bool(toggles.get("use_pitch_mix", defaults.module_toggles.use_pitch_mix), "module_toggles.use_pitch_mix"),
            use_bullpen_exposure=_bool(toggles.get("use_bullpen_exposure", defaults.module_toggles.use_bullpen_exposure), "module_toggles.use_bullpen_exposure"),
            use_park_factor=_bool(toggles.get("use_park_factor", defaults.module_toggles.use_park_factor), "module_toggles.use_park_factor"),
            use_weak_spot_collision=_bool(toggles.get("use_weak_spot_collision", defaults.module_toggles.use_weak_spot_collision), "module_toggles.use_weak_spot_collision"),
        ),
        weight_overrides=WeightOverrideConfig(overrides=_merge_weight_overrides(defaults.weight_overrides.overrides, weights)),
        slip_preferences=SlipPreferences(
            allow_core_slips=_bool(slips.get("allow_core_slips", defaults.slip_preferences.allow_core_slips), "slip_preferences.allow_core_slips"),
            allow_non_superstar_core=_bool(slips.get("allow_non_superstar_core", defaults.slip_preferences.allow_non_superstar_core), "slip_preferences.allow_non_superstar_core"),
            allow_balanced_slips=_bool(slips.get("allow_balanced_slips", defaults.slip_preferences.allow_balanced_slips), "slip_preferences.allow_balanced_slips"),
            allow_chaos_slips=_bool(slips.get("allow_chaos_slips", defaults.slip_preferences.allow_chaos_slips), "slip_preferences.allow_chaos_slips"),
            allow_contrarian_slips=_bool(slips.get("allow_contrarian_slips", defaults.slip_preferences.allow_contrarian_slips), "slip_preferences.allow_contrarian_slips"),
            max_slips=_int(slips.get("max_slips", defaults.slip_preferences.max_slips), "slip_preferences.max_slips"),
            legs_per_slip=_int(slips.get("legs_per_slip", defaults.slip_preferences.legs_per_slip), "slip_preferences.legs_per_slip"),
        ),
        risk_profile=RiskProfileConfig(profile=str(risk.get("profile", defaults.risk_profile.profile)).strip()),
        source_path=source_path,
    )


def _section(data: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigValidationError(f"{key} must be a mapping.")
    return dict(value)


def _merge_weight_overrides(
    defaults: Mapping[str, float | dict[str, float]],
    overrides: Mapping[str, Any],
) -> dict[str, float | dict[str, float]]:
    merged: dict[str, float | dict[str, float]] = {
        str(key): dict(value) if isinstance(value, Mapping) else float(value)
        for key, value in defaults.items()
    }
    for key, value in overrides.items():
        name = str(key)
        if isinstance(value, Mapping):
            merged[name] = {str(item_key): _float(item_value, f"weight_overrides.{name}.{item_key}") for item_key, item_value in value.items()}
        else:
            merged[name] = _float(value, f"weight_overrides.{name}")
    return merged


def _bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "on"}:
            return True
        if lowered in {"false", "no", "0", "off"}:
            return False
    raise ConfigValidationError(f"{field} must be true or false.")


def _int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ConfigValidationError(f"{field} must be an integer.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigValidationError(f"{field} must be an integer.") from exc


def _float(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ConfigValidationError(f"{field} must be numeric.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigValidationError(f"{field} must be numeric.") from exc


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if ":" not in stripped:
            raise ConfigValidationError(f"line {line_number}: expected key: value")
        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise ConfigValidationError(f"line {line_number}: invalid indentation")
        parent = stack[-1][1]
        if raw_value == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(raw_value)
    return root


def _parse_scalar(value: str) -> Any:
    stripped = value.strip().strip('"').strip("'")
    lowered = stripped.lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    if lowered in {"null", "none"}:
        return None
    try:
        if "." in stripped:
            return float(stripped)
        return int(stripped)
    except ValueError:
        return stripped
