from russworks.match_integrity import (
    build_match_integrity_audit,
    is_placeholder_prediction_name,
    normalize_batter_name,
)
from russworks.postmortem import ActualHomeRunEntry, PostMortemReport


def test_placeholder_predictions_detected_and_fail_readiness():
    audit = build_match_integrity_audit(_report_payload(["KC Batter 4", "Real Hitter"]))

    assert audit.production_readiness == "FAIL"
    assert not audit.calibration_enabled
    assert audit.placeholder_predictions_found[0].batter == "KC Batter 4"
    assert "Placeholder prediction data detected" in audit.warnings[0]


def test_real_names_pass_production_readiness():
    postmortem = PostMortemReport(
        actual_home_runs=[ActualHomeRunEntry("KC", "Bobby Witt Jr.", "FF", "Pitcher", 1, 104.0, 410.0, 28.0)]
    )

    audit = build_match_integrity_audit(_report_payload(["Bobby Witt Jr.", "Vinnie Pasquantino"]), postmortem)

    assert audit.production_readiness == "PASS"
    assert audit.calibration_enabled
    assert audit.placeholder_prediction_count == 0


def test_hit_rate_and_slip_hit_rate_use_predictions_and_legs():
    postmortem = PostMortemReport(
        actual_home_runs=[ActualHomeRunEntry("KC", "Bobby Witt Jr.", "FF", "Pitcher", 1, 104.0, 410.0, 28.0)]
    )
    payload = _report_payload(["Bobby Witt Jr.", "Vinnie Pasquantino"], slip_batters=["Bobby Witt Jr.", "Vinnie Pasquantino"])

    audit = build_match_integrity_audit(payload, postmortem)

    assert audit.matched_predictions == 1
    assert audit.total_predictions_evaluated == 2
    assert audit.hit_rate == 0.5
    assert audit.winning_legs == 1
    assert audit.total_legs_evaluated == 2
    assert audit.slip_hit_rate == 0.5


def test_unmatched_actual_hrs_are_false_negatives():
    postmortem = PostMortemReport(
        actual_home_runs=[
            ActualHomeRunEntry("KC", "Bobby Witt Jr.", "FF", "Pitcher", 1, 104.0, 410.0, 28.0),
            ActualHomeRunEntry("TEX", "Corey Seager", "SL", "Pitcher", 4, 103.0, 404.0, 26.0),
        ]
    )

    audit = build_match_integrity_audit(_report_payload(["Bobby Witt Jr."]), postmortem)

    assert audit.matched_actual_hr_count == 1
    assert audit.unmatched_actual_hr_count == 1
    assert audit.false_negative_count == 1


def test_duplicate_predictions_and_actual_hrs_are_counted():
    postmortem = PostMortemReport(
        actual_home_runs=[
            ActualHomeRunEntry("KC", "Bobby Witt Jr.", "FF", "Pitcher", 1, 104.0, 410.0, 28.0),
            ActualHomeRunEntry("KC", "Bobby Witt Jr.", "SL", "Pitcher", 6, 101.0, 390.0, 24.0),
        ]
    )

    audit = build_match_integrity_audit(_report_payload(["Bobby Witt Jr.", "Bobby Witt Jr."]), postmortem)

    assert audit.duplicate_prediction_count == 1
    assert audit.duplicate_actual_hr_count == 1
    assert "Duplicate prediction batter names detected." in audit.warnings
    assert "Duplicate actual HR batter names detected." in audit.warnings


def test_name_normalization_and_placeholder_patterns():
    assert normalize_batter_name("Iván Herrera") == "ivan herrera"
    assert is_placeholder_prediction_name("TEX Batter 7")
    assert is_placeholder_prediction_name("Team Batter 7")
    assert is_placeholder_prediction_name("Generated Batter")
    assert not is_placeholder_prediction_name("Bobby Witt Jr.")


def _report_payload(batters: list[str], *, slip_batters: list[str] | None = None):
    slip_batters = slip_batters if slip_batters is not None else batters[:1]
    return {
        "context": {"validation_status": "valid"},
        "step3": {
            "batter_reviews": [
                {"batter": batter, "team": "KC", "russ_score": 80.0, "confidence": {"grade": "Medium"}}
                for batter in batters
            ]
        },
        "step4": {
            "team_rankings": [
                {
                    "team": "KC",
                    "cluster_captain": batters[0] if batters else "",
                    "hidden_cluster_beneficiary": batters[-1] if batters else "",
                    "non_superstar_cluster_bats": list(batters),
                }
            ]
        },
        "step5": {
            "core_slips": [
                {
                    "name": "KC Core",
                    "slip_type": "core",
                    "legs": [{"batter": batter, "team": "KC"} for batter in slip_batters],
                }
            ]
        },
    }
