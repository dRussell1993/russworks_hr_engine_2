from __future__ import annotations

import argparse

from russworks.slate import build_live_slate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Russ-Works daily CSV slate files from live providers.")
    parser.add_argument("--date", required=True, help="Slate date in YYYY-MM-DD format.")
    parser.add_argument("--data-root", default="data/daily", help="Root folder where daily slate folders are written.")
    parser.add_argument("--max-retries", type=int, default=1, help="Additional provider fetch retries for the slate builder.")
    args = parser.parse_args(argv)
    result = build_live_slate(args.date, data_root=args.data_root, max_retries=args.max_retries)
    print(result.to_json())
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
