"""Command-line interface for csvlens."""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import TOOL_NAME, TOOL_VERSION
from .core import profile_csv, clean_csv, head_csv, select_columns


def _render_table(rows: List[List[str]], header: List[str]) -> str:
    cols = len(header)
    widths = [len(str(h)) for h in header]
    for r in rows:
        for i in range(cols):
            cell = str(r[i]) if i < len(r) else ""
            if len(cell) > widths[i]:
                widths[i] = len(cell)
    widths = [min(w, 40) for w in widths]

    def fmt_row(vals):
        cells = []
        for i in range(cols):
            v = str(vals[i]) if i < len(vals) else ""
            if len(v) > widths[i]:
                v = v[: widths[i] - 1] + "…"
            cells.append(v.ljust(widths[i]))
        return " | ".join(cells)

    sep = "-+-".join("-" * w for w in widths)
    out = [fmt_row(header), sep]
    out.extend(fmt_row(r) for r in rows)
    return "\n".join(out)


def _print_profile_table(prof) -> None:
    print(f"file: {prof.path}")
    print(f"delimiter: {prof.delimiter!r}  rows: {prof.rows}  columns: {prof.columns}")
    header = ["column", "type", "nulls", "distinct", "min", "max", "mean"]
    rows = []
    for cs in prof.column_stats:
        rows.append([
            cs.name,
            cs.inferred_type,
            str(cs.nulls),
            str(cs.distinct_estimate),
            "" if cs.min is None else str(cs.min),
            "" if cs.max is None else str(cs.max),
            "" if cs.mean is None else str(cs.mean),
        ])
    print(_render_table(rows, header))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Fast CLI for profiling and cleaning huge CSV files.",
    )
    p.add_argument("--version", action="version", version=f"{TOOL_NAME} {TOOL_VERSION}")
    p.add_argument(
        "--format", choices=["table", "json"], default="table",
        help="output format (default: table)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    pp = sub.add_parser("profile", help="profile column types and stats")
    pp.add_argument("path")
    pp.add_argument("-d", "--delimiter", default=None)

    pc = sub.add_parser("clean", help="trim, dedupe, drop-empty, fill nulls")
    pc.add_argument("path")
    pc.add_argument("-o", "--output", required=True)
    pc.add_argument("-d", "--delimiter", default=None)
    pc.add_argument("--keep-duplicates", action="store_true")
    pc.add_argument("--no-trim", action="store_true")
    pc.add_argument("--keep-empty-rows", action="store_true")
    pc.add_argument("--fill-null", default=None, help="replacement for null cells")

    ph = sub.add_parser("head", help="show the first N rows")
    ph.add_argument("path")
    ph.add_argument("-n", "--rows", type=int, default=10)
    ph.add_argument("-d", "--delimiter", default=None)

    ps = sub.add_parser("select", help="project columns by name")
    ps.add_argument("path")
    ps.add_argument("-c", "--columns", required=True, help="comma-separated names")
    ps.add_argument("-n", "--rows", type=int, default=None)
    ps.add_argument("-d", "--delimiter", default=None)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    as_json = args.format == "json"

    try:
        if args.command == "profile":
            prof = profile_csv(args.path, delimiter=args.delimiter)
            if as_json:
                print(json.dumps(prof.to_dict(), indent=2))
            else:
                _print_profile_table(prof)
            return 0

        if args.command == "clean":
            report = clean_csv(
                args.path,
                args.output,
                delimiter=args.delimiter,
                drop_duplicates=not args.keep_duplicates,
                trim=not args.no_trim,
                drop_empty_rows=not args.keep_empty_rows,
                fill_null=args.fill_null,
            )
            if as_json:
                print(json.dumps(report, indent=2))
            else:
                for k, v in report.items():
                    print(f"{k}: {v}")
            return 0

        if args.command == "head":
            res = head_csv(args.path, n=args.rows, delimiter=args.delimiter)
            if as_json:
                print(json.dumps(res, indent=2))
            else:
                print(_render_table(res["rows"], res["header"]))
            return 0

        if args.command == "select":
            cols = [c.strip() for c in args.columns.split(",") if c.strip()]
            res = select_columns(args.path, cols, delimiter=args.delimiter, n=args.rows)
            if as_json:
                print(json.dumps(res, indent=2))
            else:
                print(_render_table(res["rows"], res["header"]))
            return 0

    except FileNotFoundError:
        print(f"error: file not found: {args.path}", file=sys.stderr)
        return 2
    except KeyError as e:
        print(f"error: {e.args[0] if e.args else e}", file=sys.stderr)
        return 3
    except Exception as e:  # noqa: BLE001 — surface any runtime failure cleanly
        print(f"error: {e}", file=sys.stderr)
        return 1

    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
