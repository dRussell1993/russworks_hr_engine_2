from __future__ import annotations

import argparse
from pathlib import Path

from .ingestion import CSVHomeRunDataProvider, PostMortemIngestionRunner, default_csv_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest actual home run data for Russ-Works post-mortems.")
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
    args = parser.parse_args(argv)

    csv_path = Path(args.csv_path) if args.csv_path else default_csv_path(args.date, args.output_dir)
    provider = CSVHomeRunDataProvider(csv_path)
    runner = PostMortemIngestionRunner(provider=provider, output_dir=args.output_dir)
    entries = runner.run(args.date)
    output_path = Path(args.output_dir) / f"actual_home_runs_{args.date}.csv"
    print(f"Normalized {len(entries)} actual HR entries to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
