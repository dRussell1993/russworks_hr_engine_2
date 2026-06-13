from dataclasses import is_dataclass
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from russworks.automation import AutoPostMortemRunner, DailyPostMortemRun, PostMortemRunResult, run_postmortem
from russworks.postmortem.run import main as postmortem_cli


DATE = "2026-06-13"


def test_phase23_models_are_dataclasses():
    assert is_dataclass(DailyPostMortemRun)
    assert is_dataclass(PostMortemRunResult)


def test_auto_postmortem_skips_safely_when_actual_hr_file_is_missing():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        request = DailyPostMortemRun(
            date=DATE,
            postmortem_output_dir=str(root / "postmortem"),
            dashboard_output_dir=str(root / "dashboard"),
            recommendations_output_dir=str(root / "recommendations"),
            trends_output_dir=str(root / "trends"),
            optimizer_output_dir=str(root / "optimizer"),
        )

        result = AutoPostMortemRunner().run_postmortem(DATE, request)

        assert result.success
        assert result.skipped
        assert "missing" in result.messages[0].lower()


def test_auto_postmortem_exports_reports_and_detects_duplicate_processing():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_actual_hr_file(root / "postmortem" / f"actual_home_runs_{DATE}.csv")
        report_path = root / "outputs" / DATE / "russworks_full_report.json"
        _write_report_file(report_path)
        request = DailyPostMortemRun(
            date=DATE,
            report_path=str(report_path),
            postmortem_output_dir=str(root / "postmortem"),
            dashboard_output_dir=str(root / "dashboard"),
            recommendations_output_dir=str(root / "recommendations"),
            trends_output_dir=str(root / "trends"),
            optimizer_output_dir=str(root / "optimizer"),
        )

        result = run_postmortem(DATE, request)

        assert result.success
        assert not result.skipped
        assert result.actual_home_runs_loaded == 2
        assert Path(result.postmortem_report_path).exists()
        assert Path(result.calibration_report_path).exists()
        assert Path(result.dashboard_path).name == "dashboard.json"
        assert Path(result.recommendations_path).name == "recommendations.json"
        assert Path(result.trends_path).name == "trends.json"
        assert Path(result.optimizer_path).name == "optimizer_report.json"
        assert Path(result.metadata_path).exists()
        assert result.trends is not None
        assert result.optimizer is not None

        postmortem_payload = json.loads(Path(result.postmortem_report_path).read_text(encoding="utf-8"))
        assert len(postmortem_payload["actual_home_runs"]) == 2
        assert sum(1 for entry in postmortem_payload["winner_log"] if entry["batter"] == "TEX YPI Bat") == 1

        duplicate = AutoPostMortemRunner().run_postmortem(DATE, request)

        assert duplicate.success
        assert duplicate.skipped
        assert duplicate.duplicate
        assert duplicate.metadata_path == result.metadata_path


def test_auto_postmortem_force_preserves_historical_date_folder_and_reruns():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_actual_hr_file(root / "postmortem" / f"actual_home_runs_{DATE}.csv")
        report_path = root / "outputs" / DATE / "russworks_full_report.json"
        _write_report_file(report_path)
        request = DailyPostMortemRun(
            date=DATE,
            report_path=str(report_path),
            postmortem_output_dir=str(root / "postmortem"),
            dashboard_output_dir=str(root / "dashboard"),
            recommendations_output_dir=str(root / "recommendations"),
            trends_output_dir=str(root / "trends"),
            optimizer_output_dir=str(root / "optimizer"),
        )
        first = AutoPostMortemRunner().run_postmortem(DATE, request)
        forced = AutoPostMortemRunner().run_postmortem(DATE, DailyPostMortemRun(**{**request.__dict__, "force": True}))

        assert first.success
        assert forced.success
        assert not forced.skipped
        assert Path(forced.postmortem_report_path).parent == root / "postmortem" / DATE


def test_cli_runs_auto_postmortem_when_no_csv_is_supplied():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        postmortem_root = root / "postmortem"
        dashboard_root = root / "dashboard"
        recommendations_root = root / "recommendations"
        trends_root = root / "trends"
        optimizer_root = root / "optimizer"
        actual_path = postmortem_root / f"actual_home_runs_{DATE}.csv"
        report_path = root / "outputs" / DATE / "russworks_full_report.json"
        _write_actual_hr_file(actual_path)
        _write_report_file(report_path)

        code = postmortem_cli(
            [
                "--date",
                DATE,
                "--output-dir",
                str(postmortem_root),
                "--report-path",
                str(report_path),
                "--dashboard-dir",
                str(dashboard_root),
                "--recommendations-dir",
                str(recommendations_root),
                "--trends-dir",
                str(trends_root),
                "--optimizer-dir",
                str(optimizer_root),
            ]
        )

        assert code == 0
        assert (postmortem_root / DATE / "postmortem_report.json").exists()
        assert (dashboard_root / "dashboard.json").exists()
        assert (recommendations_root / "recommendations.json").exists()
        assert (trends_root / "trends.json").exists()
        assert (optimizer_root / "optimizer_report.json").exists()


def _write_actual_hr_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "team,batter,pitch,pitcher,inning,exit_velocity,distance,angle",
                "TEX,TEX YPI Bat,slider,KC Starter,2,106.2,411,28",
                "KC,KC Hidden Value,changeup,TEX Starter,7,101.4,389,31",
            ]
        ),
        encoding="utf-8",
    )


def _write_report_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "context": {
            "report_date": DATE,
            "games_reviewed": 1,
            "validation_status": "valid",
            "game_ids": ["tex-kc-1"],
        },
        "step3": {
            "total_batters_reviewed": 3,
            "batter_reviews": [
                _review("TEX YPI Bat", "TEX", "KC Starter", 1, ypi=True, non_superstar=True, tag=82, cps=78),
                _review("KC Hidden Value", "KC", "TEX Starter", 5, non_superstar=True, tag=72, cps=75),
                _review("TEX Miss", "TEX", "KC Starter", 4, veteran=True, catcher=True, tag=90, cps=88),
            ],
            "errors": [],
        },
        "step4": {"team_rankings": [], "cluster_rankings": [], "errors": []},
        "step5": {
            "core_slips": [
                _slip("TEX Core Cluster", "core", [_leg("TEX YPI Bat", "TEX", "A", "A"), _leg("TEX Miss", "TEX", "A+", "A")])
            ],
            "non_superstar_core_slips": [
                _slip("KC Non-Superstar Core", "non_superstar_core", [_leg("KC Hidden Value", "KC", "B", "A"), _leg("TEX YPI Bat", "TEX", "A", "A")])
            ],
            "balanced_slips": [],
            "chaos_slips": [],
            "contrarian_slips": [],
            "errors": [],
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _review(name, team, opponent, slot, *, ypi=False, veteran=False, catcher=False, non_superstar=False, tag=70, cps=70):
    return {
        "batter": name,
        "team": team,
        "opponent": opponent,
        "lineup_slot": slot,
        "hr_pct": 12.0,
        "russ_score": 86.0,
        "tier": "Gold",
        "tag": tag,
        "cps": cps,
        "lstm": 8.0,
        "pvs": 6.0,
        "environment": 4.0,
        "umpire": 1.0,
        "weak_spot_collision": {"flag": True, "score": 45.0, "confidence": 0.7, "grade": "A"},
        "ypi": {"flag": ypi, "score": 70.0 if ypi else 0.0, "confidence": 0.7 if ypi else 0.0, "grade": "Strong" if ypi else "Weak"},
        "veteran_bounce": {"flag": veteran, "score": 65.0 if veteran else 0.0, "confidence": 0.6 if veteran else 0.0, "grade": "Strong" if veteran else "Weak"},
        "catcher_power": {"flag": catcher, "score": 64.0 if catcher else 0.0, "confidence": 0.6 if catcher else 0.0, "grade": "Strong" if catcher else "Weak"},
        "pitch_mix": {"score": 66.0, "confidence": 0.7, "grade": "Strong"},
        "bullpen": {"score": 62.0, "confidence": 0.6, "grade": "Strong"},
        "park_factor": {"score": 60.0, "confidence": 0.6, "grade": "Strong"},
        "non_superstar_core": non_superstar,
        "notes": [],
    }


def _slip(name, slip_type, legs):
    return {
        "name": name,
        "slip_type": slip_type,
        "justification": f"{name} justification with YPI, non-superstar, bullpen, and park factor context.",
        "metadata": {"cluster_score": "90.0", "team": legs[0]["team"]},
        "legs": legs,
    }


def _leg(batter, team, tag, cps):
    return {
        "batter": batter,
        "team": team,
        "tag": tag,
        "cps": cps,
        "russ_score": 90.0,
        "slip_role": "core",
        "justification": "Step 5 leg justification with non-superstar and YPI context.",
    }
