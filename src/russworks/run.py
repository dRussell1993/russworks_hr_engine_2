from __future__ import annotations

import argparse
import json
import sys

from russworks.pipeline import DailyRunRequest, RussWorksPipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Russ-Works daily automation workflow.")
    parser.add_argument("--date", required=True, help="Slate date in YYYY-MM-DD format.")
    parser.add_argument("--data-root", default="data/daily", help="Root folder containing daily input folders.")
    parser.add_argument("--output-root", default="data/outputs", help="Root folder for daily output folders.")
    args = parser.parse_args(argv)

    request = DailyRunRequest(date=args.date, data_root=args.data_root, output_root=args.output_root)
    result = RussWorksPipeline().run_daily_pipeline(args.date, request)
    print(
        json.dumps(
            {
                "success": result.success,
                "date": result.request.date,
                "validation_status": result.validation_status,
                "total_batters_reviewed": result.total_batters_reviewed,
                "output_dir": result.output_dir,
                "report_json_path": result.report_json_path,
                "errors": result.errors,
                "missing_data": result.missing_data,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
