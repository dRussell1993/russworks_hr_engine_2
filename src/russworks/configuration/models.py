from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date
from enum import Enum
import json
from typing import Any, Mapping

from russworks.config.weights import ScoringWeights


VALID_RISK_PROFILES = {"conservative", "balanced", "aggressive", "chaos"}


@dataclass(frozen=True)
class ModuleToggleConfig:
    use_ypi: bool = True
    use_veteran_bounce: bool = True
    use_catcher_power: bool = True
    use_pitch_mix: bool = True
    use_bullpen_exposure: bool = True
    use_park_factor: bool = True
    use_weak_spot_collision: bool = True


@dataclass(frozen=True)
class WeightOverrideConfig:
    overrides: dict[str, float | dict[str, float]] = field(default_factory=dict)

    def normalized(self) -> dict[str, float | dict[str, float]]:
        return {str(key): value for key, value in self.overrides.items()}


@dataclass(frozen=True)
class SlipPreferences:
    allow_core_slips: bool = True
    allow_non_superstar_core: bool = True
    allow_balanced_slips: bool = True
    allow_chaos_slips: bool = True
    allow_contrarian_slips: bool = True
    max_slips: int = 999
    legs_per_slip: int = 4


@dataclass(frozen=True)
class RiskProfileConfig:
    profile: str = "balanced"


@dataclass(frozen=True)
class RussWorksUserConfig:
    module_toggles: ModuleToggleConfig = field(default_factory=ModuleToggleConfig)
    weight_overrides: WeightOverrideConfig = field(default_factory=WeightOverrideConfig)
    slip_preferences: SlipPreferences = field(default_factory=SlipPreferences)
    risk_profile: RiskProfileConfig = field(default_factory=RiskProfileConfig)
    source_path: str = "defaults"

    def validate(self) -> "RussWorksUserConfig":
        errors: list[str] = []
        if self.risk_profile.profile not in VALID_RISK_PROFILES:
            errors.append(
                f"risk_profile.profile must be one of {', '.join(sorted(VALID_RISK_PROFILES))}; got {self.risk_profile.profile!r}"
            )
        if self.slip_preferences.max_slips < 0:
            errors.append("slip_preferences.max_slips must be 0 or greater.")
        if self.slip_preferences.legs_per_slip < 1:
            errors.append("slip_preferences.legs_per_slip must be at least 1.")
        for module, value in self.weight_overrides.normalized().items():
            if isinstance(value, Mapping):
                for key, item in value.items():
                    if not _is_number(item):
                        errors.append(f"weight_overrides.{module}.{key} must be numeric.")
            elif not _is_number(value):
                errors.append(f"weight_overrides.{module} must be numeric or a mapping of numeric values.")
        if errors:
            raise ConfigValidationError("; ".join(errors))
        return self

    def to_scoring_weights(self) -> ScoringWeights:
        weights = ScoringWeights.defaults()
        data = {
            "tag": dict(weights.tag),
            "cps": dict(weights.cps),
            "lstm": dict(weights.lstm),
            "environment": dict(weights.environment),
            "umpire": dict(weights.umpire),
            "pvs": dict(weights.pvs),
        }
        section_aliases = {
            "TAG": "tag",
            "CPS": "cps",
            "LSTM": "lstm",
            "PVS": "pvs",
            "Environment": "environment",
            "Umpire": "umpire",
        }
        for module, override in self.weight_overrides.normalized().items():
            section = section_aliases.get(module)
            if section is None:
                continue
            if isinstance(override, Mapping):
                data[section].update({str(key): float(value) for key, value in override.items()})
            else:
                data[section]["base"] = float(override)
        return ScoringWeights.from_mapping(data)

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


class ConfigValidationError(ValueError):
    pass


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value
