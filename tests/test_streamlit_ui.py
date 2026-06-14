import json
from pathlib import Path

from russworks.ui.loaders import available_output_dates, discover_outputs, load_dashboard_outputs
from russworks.ui import views


def test_ui_app_imports_with_absolute_package_imports():
    import russworks.ui.app as app

    assert app.PAGES[0] == "Overview"
    assert "Accuracy Review" in app.PAGES
    assert callable(app.render_app)


def test_ui_loader_reads_generated_dashboard_outputs(tmp_path):
    _write_ui_fixture(tmp_path, "2026-06-13")
    _write_postmortem_fixture(tmp_path, "2026-06-13")

    data = load_dashboard_outputs(date="2026-06-13", data_root=tmp_path)

    assert data.selected_date == "2026-06-13"
    assert data.missing_files == []
    assert data.dashboard_data["metadata"]["report_date"] == "2026-06-13"
    assert "Russ-Works Operator Report" in data.operator_report
    assert available_output_dates(tmp_path) == ["2026-06-13"]
    assert Path(data.data_root) == tmp_path.resolve()
    assert data.available_dates == ["2026-06-13"]
    assert data.postmortem_status["actual_hr_file_found"] is True
    assert data.postmortem_status["postmortem_report_found"] is True


def test_ui_output_discovery_prefers_repo_root_data_over_work_data(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src" / "russworks").mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[project]\nname = 'russworks'\n", encoding="utf-8")
    real = repo / "data"
    sample = repo / "work" / "sample" / "data"
    _write_ui_fixture(real, "2026-06-13")
    _write_ui_fixture(sample, "2026-06-14")

    discovery = discover_outputs(start=repo)

    assert discovery.selected_date == "2026-06-13"
    assert discovery.selected_root == real.resolve()
    assert discovery.source_label == "Real project output"
    assert str(sample.resolve()) in discovery.searched_paths


def test_ui_missing_output_message_lists_paths_and_next_command(tmp_path):
    data = load_dashboard_outputs(date="2026-06-14", data_root=tmp_path)

    assert "dashboard_data" in data.missing_files
    assert "report_date" not in data.missing_files
    assert "python -m russworks.run --date YYYY-MM-DD" in data.missing_output_message
    assert str(tmp_path.resolve()) in data.missing_output_message


def test_ui_views_render_tables_cards_and_warnings(tmp_path):
    _write_ui_fixture(tmp_path, "2026-06-13")
    _write_postmortem_fixture(tmp_path, "2026-06-13")
    data = load_dashboard_outputs(date="2026-06-13", data_root=tmp_path)

    overview = views.overview_metrics(data)
    targets = views.top_hr_targets(data)
    filtered_targets = views.top_hr_targets(data, team="KC", tier="Elite Core / Diamond", confidence="Medium", non_superstar_only=True)
    clusters = views.team_clusters(data)
    slips = views.slip_cards(data)
    warnings = views.validation_warning_rows(data)
    command = views.command_center_rows(data)
    risk = views.risk_rows(data)
    exposure = views.exposure_warning_rows(data)
    outputs = views.generated_output_rows(data)
    source_rows = views.data_source_rows(data)
    postmortem = views.postmortem_status_rows(data)
    accuracy_metrics = views.accuracy_metric_rows(data)
    accuracy_sections = views.accuracy_hit_rate_sections(data)
    accuracy_false_negatives = views.accuracy_false_negative_rows(data)
    accuracy_false_positives = views.accuracy_false_positive_rows(data)
    accuracy_modules = views.accuracy_module_rows(data)
    accuracy_recommendations = views.accuracy_recommendation_rows(data)

    assert {"Metric": "Date", "Value": "2026-06-13"} in overview
    assert any(row["Metric"] == "Data source" for row in overview)
    assert targets[0]["Batter"] == "KC Power"
    assert targets[0]["Confidence"] == "Medium 61.8"
    assert targets[0]["Key Drivers"]
    assert filtered_targets[0]["Batter"] == "KC Power"
    assert clusters[0]["Team"] == "KC"
    assert clusters[0]["Warnings"]
    assert slips["Core"][0]["name"] == "KC Core"
    assert slips["Core"][0]["legs"][0]["Batter"] == "KC Power"
    assert slips["Core"][0]["legs"][0]["Russ Score"] == 91.2
    assert any("Neutral park factor fallback used" in row["Message"] for row in warnings)
    assert any(row["Section"] == "Slate" for row in command)
    assert any(row["Metric"] == "Expected Hit Rate" for row in risk)
    assert any(row["Type"] == "Portfolio" for row in exposure)
    assert any(row["Type"] == "Report" for row in outputs)
    assert source_rows[0]["Metric"] == "Data Source"
    assert any(row["Metric"] == "Actual HR File" and row["Status"] == "Found" for row in postmortem)
    assert views.postmortem_command(data) == "python -m russworks.postmortem.run --date 2026-06-13"
    assert {"Metric": "HR Events Acquired", "Value": 2} in accuracy_metrics
    assert accuracy_sections["By Russ Tier"][0]["Group"] == "Elite Core"
    assert accuracy_false_negatives[0]["Batter"] == "TEX Missed"
    assert accuracy_false_positives[0]["Batter"] == "KC Overranked"
    assert accuracy_modules[0]["Module"] == "TAG"
    assert accuracy_recommendations[0]["Module"] == "TAG"


def test_ui_flags_placeholder_batter_names(tmp_path):
    _write_ui_fixture(tmp_path, "2026-06-13", batter_name="KC Batter 4")

    data = load_dashboard_outputs(date="2026-06-13", data_root=tmp_path)

    assert data.placeholder_warnings
    assert any("KC Batter" in row["Message"] for row in views.validation_warning_rows(data))


def _write_ui_fixture(root: Path, date: str, *, batter_name: str = "KC Power") -> None:
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
                "batter": batter_name,
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
                "cluster_captain": batter_name,
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
                "batters": [batter_name, "KC Value"],
                "teams": ["KC"],
                "justification": "Core slip with confidence warning.",
            }
        ],
        "portfolio": {"risk_grade": "MODERATE", "risk_score": 40.0},
        "simulation": {"simulation_count": 1000, "expected_hit_rate": 0.12, "expected_roi": 0.04, "drawdown_risk": 0.2, "risk_grade": "MODERATE"},
        "confidence_views": {"batter_confidence_grade_counts": {"Medium": 1}},
        "command_center": {},
        "dashboard_summary": {},
        "accuracy_review": {
            "hr_events_acquired": 2,
            "winners": 1,
            "misses": 1,
            "false_positives": 1,
            "hit_rate": 0.5,
            "hit_rate_by_russ_tier": [{"label": "Elite Core", "appearances": 2, "hits": 1, "misses": 1, "hit_rate": 0.5}],
            "hit_rate_by_confidence_grade": [{"label": "Medium", "appearances": 2, "hits": 1, "misses": 1, "hit_rate": 0.5}],
            "hit_rate_by_team_cluster_grade": [{"label": "Strong Cluster", "appearances": 9, "hits": 1, "misses": 8, "hit_rate": 0.1111}],
            "hit_rate_by_slip_type": [{"label": "core", "appearances": 2, "hits": 1, "misses": 1, "hit_rate": 0.5}],
            "top_false_negatives": [{"batter": "TEX Missed", "team": "TEX", "pitcher": "KC Starter", "pitch": "FF", "inning": 3, "distance": 410, "russ_score": 83.0, "tier": "Strong Play", "confidence": "Medium"}],
            "top_false_positives": [{"batter": "KC Overranked", "team": "KC", "slip_name": "KC Core", "slip_type": "core", "russ_score": 91.2, "reason": "High-confidence miss.", "overweighted_modules": ["TAG", "CPS"]}],
            "best_performing_modules": [{"module": "TAG", "appearances": 10, "wins": 4, "losses": 6, "hit_rate": 0.4, "false_positives": 2, "false_negatives": 1, "confidence_accuracy": 0.7}],
            "worst_performing_modules": [{"module": "Umpire", "appearances": 10, "wins": 1, "losses": 9, "hit_rate": 0.1, "false_positives": 5, "false_negatives": 4, "confidence_accuracy": 0.2}],
            "top_calibration_recommendations": [{"module": "TAG", "action": "review", "confidence": "medium", "reasoning": "TAG pressure", "source": "calibration_result"}],
        },
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
    full_report = {
        "context": {
            **dashboard_data["metadata"],
            "validation_summary": {
                "total_games": 1,
                "complete_games": 1,
                "skipped_games": 0,
                "park_factor_fallback_games": 1,
                "park_factor_fallback_game_ids": ["kc-hou-1"],
            },
        },
        "step3": {
            "batter_reviews": [
                {
                    "batter": "KC Power",
                    "opponent": "HOU Starter",
                    "team": "KC",
                    "russ_score": 91.2,
                    "score_band": "Elite Core / Diamond",
                    "confidence": {"grade": "Medium", "score": 61.8},
                    "tag_contribution": 95.0,
                    "cps_contribution": 94.0,
                    "pvs_contribution": 20.0,
                    "non_superstar_core": True,
                }
            ]
        },
        "step4": {},
        "step5": {
            "core_slips": [
                {
                    "name": "KC Core",
                    "slip_type": "core",
                    "confidence": {"grade": "Medium", "score": 61.8},
                    "justification": "Core slip with confidence warning.",
                    "legs": [
                        {
                            "batter": "KC Power",
                            "team": "KC",
                            "russ_score": 91.2,
                            "slip_role": "core",
                            "confidence": {"grade": "Medium", "score": 61.8},
                            "justification": "TAG/CPS collision.",
                        }
                    ],
                }
            ]
        },
        "portfolio": {"risk_report": {"risk_grade": "MODERATE", "risk_score": 40.0}, "recommendations": [{"message": "Limit KC exposure."}]},
        "diversification": {"recommendations": [{"message": "Add one non-KC alternative."}]},
        "simulation": {"summary": {"simulation_count": 1000, "expected_hit_rate": 0.12, "expected_roi": 0.04, "drawdown_risk": 0.2, "risk_grade": "MODERATE"}},
        "schema_version": "1.0",
    }

    _write_json(root / "web" / "dashboard_data.json", dashboard_data)
    _write_json(root / "command_center" / "command_center.json", command_center)
    _write_json(root / "dashboard" / "dashboard.json", calibration_dashboard)
    _write_json(root / "outputs" / date / "russworks_full_report.json", full_report)
    (root / "outputs" / date / "russworks_operator_report.md").write_text("# Russ-Works Operator Report\n", encoding="utf-8")


def _write_postmortem_fixture(root: Path, date: str) -> None:
    (root / "postmortem" / date).mkdir(parents=True)
    (root / "recommendations").mkdir(parents=True)
    (root / "postmortem" / f"actual_home_runs_{date}.csv").write_text(
        "team,batter,pitch,pitcher,inning,exit_velocity,distance,angle\nKC,KC Power,FF,HOU Starter,1,104.2,412,27\n",
        encoding="utf-8",
    )
    _write_json(root / "postmortem" / date / "postmortem_report.json", {"winner_log": [], "loser_log": []})
    _write_json(root / "postmortem" / date / "calibration_result.json", {"success": True})
    _write_json(root / "recommendations" / "recommendations.json", {"recommendations": []})


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
