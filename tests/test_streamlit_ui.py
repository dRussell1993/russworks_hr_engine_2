import json
from pathlib import Path

from russworks.ui.loaders import available_output_dates, load_dashboard_outputs
from russworks.ui import views


def test_ui_app_imports_with_absolute_package_imports():
    import russworks.ui.app as app

    assert app.PAGES[0] == "Overview"
    assert callable(app.render_app)


def test_ui_loader_reads_generated_dashboard_outputs(tmp_path):
    _write_ui_fixture(tmp_path, "2026-06-13")

    data = load_dashboard_outputs(date="2026-06-13", data_root=tmp_path)

    assert data.selected_date == "2026-06-13"
    assert data.missing_files == []
    assert data.dashboard_data["metadata"]["report_date"] == "2026-06-13"
    assert "Russ-Works Operator Report" in data.operator_report
    assert available_output_dates(tmp_path) == ["2026-06-13"]


def test_ui_views_render_tables_cards_and_warnings(tmp_path):
    _write_ui_fixture(tmp_path, "2026-06-13")
    data = load_dashboard_outputs(date="2026-06-13", data_root=tmp_path)

    overview = views.overview_metrics(data)
    targets = views.top_hr_targets(data)
    clusters = views.team_clusters(data)
    slips = views.slip_cards(data)
    warnings = views.validation_warning_rows(data)
    command = views.command_center_rows(data)

    assert {"Metric": "Date", "Value": "2026-06-13"} in overview
    assert targets[0]["Batter"] == "KC Power"
    assert targets[0]["Confidence"] == "Medium 61.8"
    assert clusters[0]["Team"] == "KC"
    assert slips["Core"][0]["name"] == "KC Core"
    assert "KC Power" in slips["Core"][0]["batters"]
    assert any("Neutral park factor fallback used" in row["Message"] for row in warnings)
    assert any(row["Section"] == "Slate" for row in command)


def _write_ui_fixture(root: Path, date: str) -> None:
    (root / "web").mkdir(parents=True)
    (root / "command_center").mkdir(parents=True)
    (root / "dashboard").mkdir(parents=True)
    (root / "outputs" / date).mkdir(parents=True)

    dashboard_data = {
        "metadata": {
            "report_date": date,
            "games_reviewed": 1,
            "validation_status": "valid",
            "schema_version": "1.0",
            "game_ids": ["kc-hou-1"],
        },
        "batters": [
            {
                "rank": 1,
                "batter": "KC Power",
                "team": "KC",
                "opponent": "HOU Starter",
                "lineup_slot": 4,
                "russ_score": 91.2,
                "tier": "Gold",
                "confidence_score": 61.8,
                "confidence_grade": "Medium",
                "key_factors": ["ypi", "weak_spot_collision"],
            }
        ],
        "teams": [
            {
                "rank": 1,
                "team": "KC",
                "opponent": "HOU",
                "tag_grade": "A+",
                "cps_grade": "A+",
                "total_cluster_score": 79.04,
                "cluster_strength_label": "Strong Cluster",
                "cluster_captain": "KC Power",
                "hidden_cluster_beneficiary": "KC Value",
                "confidence_grade": "Medium",
            }
        ],
        "slips": [
            {
                "name": "KC Core",
                "slip_type": "core",
                "confidence_score": 61.8,
                "confidence_grade": "Medium",
                "batters": ["KC Power", "KC Value"],
                "teams": ["KC"],
                "justification": "Core slip with confidence warning.",
            }
        ],
        "portfolio": {"risk_grade": "MODERATE", "risk_score": 40.0},
        "simulation": {"expected_hit_rate": 0.12, "expected_roi": 0.04, "drawdown_risk": 0.2, "risk_grade": "MODERATE"},
        "confidence_views": {"batter_confidence_grade_counts": {"Medium": 1}},
        "command_center": {},
        "dashboard_summary": {},
        "errors": [],
    }
    command_center = {
        "slate_status": {
            "date": date,
            "games_loaded": 1,
            "batters_loaded": 18,
            "confirmed_lineups": 2,
            "skipped_games": [],
            "validation_summary": {"park_factor_fallback_games": 1},
        },
        "execution_summary": {
            "reports_generated": ["russworks_full_report.json"],
            "exports_generated": ["dashboard.json"],
            "errors": [],
            "warnings": [],
        },
        "formula_health": {"confidence_summary": {"average_confidence": 61.8}},
        "warnings": ["kc-hou-1: Neutral park factor fallback used"],
        "errors": [],
    }
    calibration_dashboard = {
        "validation_summaries": ["Slate validation: total_games=1, complete_games=1, skipped_games=0, park_factor_fallback_games=1."],
        "skipped_game_summaries": [],
    }
    full_report = {"context": dashboard_data["metadata"], "step3": {}, "step4": {}, "step5": {}, "schema_version": "1.0"}

    _write_json(root / "web" / "dashboard_data.json", dashboard_data)
    _write_json(root / "command_center" / "command_center.json", command_center)
    _write_json(root / "dashboard" / "dashboard.json", calibration_dashboard)
    _write_json(root / "outputs" / date / "russworks_full_report.json", full_report)
    (root / "outputs" / date / "russworks_operator_report.md").write_text("# Russ-Works Operator Report\n", encoding="utf-8")


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
