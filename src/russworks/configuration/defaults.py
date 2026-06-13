from __future__ import annotations

from .models import (
    ModuleToggleConfig,
    RiskProfileConfig,
    RussWorksUserConfig,
    SlipPreferences,
    WeightOverrideConfig,
)


DEFAULT_WEIGHT_OVERRIDES = {
    "TAG": {},
    "CPS": {},
    "LSTM": {},
    "PVS": {},
    "Environment": {},
    "Umpire": {},
    "Weak Spot": {},
    "YPI": {},
    "Veteran Bounce": {},
    "Catcher Power": {},
    "Pitch Mix": {},
    "Bullpen Exposure": {},
    "Park Factor V2": {},
}


def default_user_config() -> RussWorksUserConfig:
    return RussWorksUserConfig(
        module_toggles=ModuleToggleConfig(),
        weight_overrides=WeightOverrideConfig(overrides=dict(DEFAULT_WEIGHT_OVERRIDES)),
        slip_preferences=SlipPreferences(),
        risk_profile=RiskProfileConfig(profile="balanced"),
        source_path="defaults",
    )
