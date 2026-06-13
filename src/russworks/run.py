from __future__ import annotations

import argparse
import json
import sys

from russworks.pipeline import DailyRunRequest, RussWorksPipeline
from russworks.slate import build_live_slate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Russ-Works daily automation workflow.")
    parser.add_argument("--date", required=True, help="Slate date in YYYY-MM-DD format.")
    parser.add_argument("--data-root", default="data/daily", help="Root folder containing daily input folders.")
    parser.add_argument("--output-root", default="data/outputs", help="Root folder for daily output folders.")
    parser.add_argument("--provider-mode", default="csv", choices=["csv", "live"], help="Daily slate source mode.")
    parser.add_argument("--config-path", default="config/russworks_config.yaml", help="Russ-Works user config YAML path.")
    parser.add_argument("--build-slate", action="store_true", help="Build data/daily/YYYY-MM-DD CSV slate files from live providers before running.")
    args = parser.parse_args(argv)

    if args.build_slate:
        build_result = build_live_slate(args.date, data_root=args.data_root)
        if not build_result.success:
            print(build_result.to_json())
            return 1

    request = DailyRunRequest(
        date=args.date,
        data_root=args.data_root,
        output_root=args.output_root,
        provider_mode=args.provider_mode,
        config_path=args.config_path,
    )
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
