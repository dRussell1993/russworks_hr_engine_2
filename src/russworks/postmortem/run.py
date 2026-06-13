from __future__ import annotations

import argparse
from pathlib import Path

from russworks.automation import AutoPostMortemRunner, DailyPostMortemRun

from .ingestion import CSVHomeRunDataProvider, PostMortemIngestionRunner, default_csv_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Russ-Works post-mortem ingestion or automation.")
    parser.add_argument("--date", required=True, help="Slate date in YYYY-MM-DD format.")
    parser.add_argument(
        "--csv",
        dest="csv_path",
        default=None,
        help="Manual actual HR CSV path. Defaults to data/postmortem/actual_home_runs_raw_YYYY-MM-DD.csv.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/postmortem",
        help="Directory for normalized post-mortem files.",
    )
    parser.add_argument(
        "--report-path",
        default=None,
        help="Generated Russ-Works report JSON. Defaults to data/outputs/YYYY-MM-DD/russworks_full_report.json.",
    )
    parser.add_argument(
        "--dashboard-dir",
        default="data/dashboard",
        help="Directory for dashboard.json.",
    )
    parser.add_argument(
        "--recommendations-dir",
        default="data/recommendations",
        help="Directory for recommendations.json.",
    )
    parser.add_argument("--auto", action="store_true", help="After optional CSV ingestion, run the automated post-mortem.")
    parser.add_argument("--force", action="store_true", help="Re-run even if metadata shows the date was already processed.")
    args = parser.parse_args(argv)

    if args.csv_path:
        csv_path = Path(args.csv_path)
        provider = CSVHomeRunDataProvider(csv_path)
        runner = PostMortemIngestionRunner(provider=provider, output_dir=args.output_dir)
        entries = runner.run(args.date)
        output_path = Path(args.output_dir) / f"actual_home_runs_{args.date}.csv"
        print(f"Normalized {len(entries)} actual HR entries to {output_path}")
        if not args.auto:
            return 0
    elif not args.auto:
        args.auto = True

    actual_path = Path(args.output_dir) / f"actual_home_runs_{args.date}.csv"
    request = DailyPostMortemRun(
        date=args.date,
        actual_hr_path=str(actual_path),
        report_path=args.report_path or "",
        postmortem_output_dir=args.output_dir,
        dashboard_output_dir=args.dashboard_dir,
        recommendations_output_dir=args.recommendations_dir,
        force=args.force,
    )
    result = AutoPostMortemRunner().run_postmortem(args.date, request)
    for message in result.messages:
        print(message)
    for error in result.errors:
        print(error)
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
