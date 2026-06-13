from dataclasses import is_dataclass
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from russworks.cluster import ClusterRanking, TeamClusterReport
from russworks.configuration import (
    ConfigLoader,
    ConfigValidationError,
    ModuleToggleConfig,
    RiskProfileConfig,
    RussWorksUserConfig,
    SlipPreferences,
    WeightOverrideConfig,
    config_from_mapping,
    default_user_config,
)
from russworks.pipeline import DailyRunRequest, RussWorksPipeline
from russworks.review import Step3ReviewEngine
from russworks.slips import Step5SlipEngine

sys.path.append(str(Path(__file__).parent))
from test_daily_pipeline import _slate


def test_phase28_configuration_models_are_dataclasses():
    assert is_dataclass(RussWorksUserConfig)
    assert is_dataclass(SlipPreferences)
    assert is_dataclass(ModuleToggleConfig)
    assert is_dataclass(WeightOverrideConfig)
    assert is_dataclass(RiskProfileConfig)


def test_default_config_preserves_current_behavior_shape():
    config = default_user_config()

    assert config.module_toggles.use_ypi
    assert config.module_toggles.use_veteran_bounce
    assert config.module_toggles.use_catcher_power
    assert config.slip_preferences.allow_core_slips
    assert config.slip_preferences.max_slips == 999
    assert config.risk_profile.profile == "balanced"
    assert config.to_scoring_weights().tag["base"] == 45.0


def test_config_loader_reads_yaml_and_applies_weight_overrides():
    with TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "russworks_config.yaml"
        path.write_text(
            "\n".join(
                [
                    "module_toggles:",
                    "  use_ypi: false",
                    "slip_preferences:",
                    "  allow_chaos_slips: false",
                    "  max_slips: 2",
                    "  legs_per_slip: 2",
                    "risk_profile:",
                    "  profile: conservative",
                    "weight_overrides:",
                    "  TAG:",
                    "    base: 50",
                    "  PVS: 9",
                ]
            ),
            encoding="utf-8",
        )

        config = ConfigLoader(path).load()

    assert not config.module_toggles.use_ypi
    assert not config.slip_preferences.allow_chaos_slips
    assert config.slip_preferences.max_slips == 2
    assert config.slip_preferences.legs_per_slip == 2
    assert config.risk_profile.profile == "conservative"
    assert config.to_scoring_weights().tag["base"] == 50.0
    assert config.to_scoring_weights().pvs["base"] == 9.0


def test_invalid_config_fails_clearly():
    try:
        config_from_mapping({"risk_profile": {"profile": "reckless"}}).validate()
    except ConfigValidationError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected ConfigValidationError")

    assert "risk_profile.profile" in message


def test_step3_respects_module_toggles():
    config = config_from_mapping(
        {
            "module_toggles": {
                "use_ypi": False,
                "use_catcher_power": False,
                "use_veteran_bounce": False,
                "use_pitch_mix": False,
                "use_bullpen_exposure": False,
                "use_park_factor": False,
                "use_weak_spot_collision": False,
            }
        }
    )

    result = Step3ReviewEngine(user_config=config).review_all_batters(_slate().games[0])
    review = next(item for item in result.reviews if item.batter_name == "TEX Batter 1")

    assert result.success
    assert not review.ypi_flag
    assert review.ypi_score == 0.0
    assert not review.weak_spot_collision_flag
    assert review.weak_spot_collision_score == 0.0
    assert review.pitch_mix_matchup_score == 0.0
    assert review.bullpen_exposure_score == 0.0
    assert review.park_factor_score == 0.0


def test_step5_respects_slip_preferences():
    config = config_from_mapping(
        {
            "slip_preferences": {
                "allow_core_slips": True,
                "allow_non_superstar_core": False,
                "allow_balanced_slips": False,
                "allow_chaos_slips": False,
                "allow_contrarian_slips": False,
                "max_slips": 1,
                "legs_per_slip": 2,
            }
        }
    )
    report = ClusterRanking(
        total_teams=1,
        total_batters=9,
        ranked_teams=[
            TeamClusterReport(
                team="TEX",
                opponent="KC Starter",
                tag_grade="A+",
                cps_grade="A",
                total_cluster_score=94.0,
                cluster_strength_label="elite",
                cluster_captain="TEX Captain",
                hidden_cluster_beneficiary="TEX Hidden",
                core_bats=["TEX Captain", "TEX Hidden", "TEX Power"],
                non_superstar_cluster_bats=["TEX Hidden"],
                ypi_bats=["TEX Hidden"],
                batter_count=9,
            )
        ],
    )

    portfolio = Step5SlipEngine(user_config=config).generate_slip_portfolio(report)

    assert portfolio.success
    assert len(portfolio.all_slips) == 1
    assert portfolio.core_slips
    assert len(portfolio.core_slips[0].legs) == 2
    assert portfolio.non_superstar_core_slips == []
    assert portfolio.chaos_slips == []


def test_daily_pipeline_exports_active_config_in_report_metadata():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        config_path = root / "russworks_config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "risk_profile:",
                    "  profile: aggressive",
                    "module_toggles:",
                    "  use_ypi: false",
                ]
            ),
            encoding="utf-8",
        )
        request = DailyRunRequest(
            date="2026-06-13",
            output_root=str(root / "outputs"),
            config_path=str(config_path),
        )
        result = RussWorksPipeline(slate_loader=lambda date, request: _slate(date)).run_daily_pipeline("2026-06-13", request)

        payload = json.loads(Path(result.report_json_path).read_text(encoding="utf-8"))

    assert result.success
    assert payload["context"]["active_config"]["risk_profile"]["profile"] == "aggressive"
    assert payload["context"]["active_config"]["module_toggles"]["use_ypi"] is False
    assert "risk_profile=aggressive" in payload["context"]["notes"]
