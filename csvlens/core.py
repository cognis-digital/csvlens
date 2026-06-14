"""Core engine for csvlens — streaming CSV profiling and cleaning.

Pure standard library. Designed to handle large files by streaming rows
rather than loading everything into memory for profiling.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, Iterator, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Type inference helpers
# ---------------------------------------------------------------------------

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")
_BOOL_VALUES = {"true", "false", "t", "f", "yes", "no", "y", "n", "0", "1"}
_DATE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?$"
    r"|^\d{1,2}/\d{1,2}/\d{2,4}$"
)
_NULL_TOKENS = {"", "na", "n/a", "null", "none", "nan", "nil", "-"}


def _classify(value: str) -> str:
    """Classify a single cell into a coarse type token."""
    v = value.strip()
    if v.lower() in _NULL_TOKENS:
        return "null"
    if _INT_RE.match(v):
        return "int"
    if _FLOAT_RE.match(v):
        return "float"
    if _DATE_RE.match(v):
        return "date"
    if v.lower() in _BOOL_VALUES:
        return "bool"
    return "str"


def _resolve_type(counts: Dict[str, int]) -> str:
    """Resolve dominant column type from per-cell type counts."""
    non_null = {k: c for k, c in counts.items() if k != "null" and c > 0}
    if not non_null:
        return "empty"
    types = set(non_null)
    if types <= {"int"}:
        return "int"
    if types <= {"int", "float"}:
        return "float"
    if types <= {"bool", "int"}:
        return "bool"
    if types <= {"date"}:
        return "date"
    if len(types) == 1:
        return next(iter(types))
    return "mixed"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ColumnStats:
    name: str
    inferred_type: str = "empty"
    count: int = 0
    nulls: int = 0
    distinct_estimate: int = 0
    min: Optional[str] = None
    max: Optional[str] = None
    mean: Optional[float] = None
    type_counts: Dict[str, int] = field(default_factory=dict)
    sample_values: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Profile:
    path: str
    delimiter: str
    rows: int
    columns: int
    column_stats: List[ColumnStats]

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Dialect detection
# ---------------------------------------------------------------------------


def detect_dialect(sample: str) -> str:
    """Return the most likely delimiter for a CSV text sample."""
    candidates = [",", "\t", ";", "|"]
    first_lines = [ln for ln in sample.splitlines() if ln.strip()][:20]
    if not first_lines:
        return ","
    best, best_score = ",", -1.0
    for delim in candidates:
        per_line = [ln.count(delim) for ln in first_lines]
        if max(per_line) == 0:
            continue
        avg = sum(per_line) / len(per_line)
        var = sum((c - avg) ** 2 for c in per_line) / len(per_line)
        score = avg - var
        if score > best_score:
            best, best_score = delim, score
    return best


def _open_reader(
    path: str, delimiter: Optional[str]
) -> Tuple[str, Iterator[List[str]], "io.TextIOBase"]:
    if not isinstance(path, str) or not path:
        raise ValueError("path must be a non-empty string")
    if delimiter is not None and len(delimiter) != 1:
        raise ValueError(
            f"delimiter must be a single character, got {delimiter!r} (length {len(delimiter)})"
        )
    try:
        fh = open(path, "r", newline="", encoding="utf-8-sig", errors="replace")
    except IsADirectoryError:
        raise IsADirectoryError(f"path is a directory, not a file: {path}")
    if delimiter is None:
        head = fh.read(65536)
        fh.seek(0)
        delimiter = detect_dialect(head)
    reader = csv.reader(fh, delimiter=delimiter)
    return delimiter, reader, fh


# ---------------------------------------------------------------------------
# Profiling
# ---------------------------------------------------------------------------


def profile_csv(
    path: str,
    delimiter: Optional[str] = None,
    max_distinct: int = 2048,
    sample_size: int = 5,
) -> Profile:
    """Stream a CSV file and compute per-column statistics."""
    delim, reader, fh = _open_reader(path, delimiter)
    try:
        try:
            header = next(reader)
        except StopIteration:
            return Profile(path=path, delimiter=delim, rows=0, columns=0, column_stats=[])

        ncols = len(header)
        type_counts: List[Dict[str, int]] = [dict() for _ in range(ncols)]
        nulls = [0] * ncols
        distinct: List[set] = [set() for _ in range(ncols)]
        distinct_capped = [False] * ncols
        num_min: List[Optional[float]] = [None] * ncols
        num_max: List[Optional[float]] = [None] * ncols
        num_sum = [0.0] * ncols
        num_count = [0] * ncols
        str_min: List[Optional[str]] = [None] * ncols
        str_max: List[Optional[str]] = [None] * ncols
        samples: List[List[str]] = [[] for _ in range(ncols)]
        rows = 0

        for record in reader:
            rows += 1
            for i in range(ncols):
                cell = record[i] if i < len(record) else ""
                t = _classify(cell)
                tc = type_counts[i]
                tc[t] = tc.get(t, 0) + 1
                if t == "null":
                    nulls[i] += 1
                    continue
                if not distinct_capped[i]:
                    distinct[i].add(cell)
                    if len(distinct[i]) > max_distinct:
                        distinct_capped[i] = True
                if len(samples[i]) < sample_size and cell not in samples[i]:
                    samples[i].append(cell)
                if t in ("int", "float"):
                    try:
                        val = float(cell)
                    except ValueError:
                        continue
                    num_count[i] += 1
                    num_sum[i] += val
                    if num_min[i] is None or val < num_min[i]:
                        num_min[i] = val
                    if num_max[i] is None or val > num_max[i]:
                        num_max[i] = val
                else:
                    if str_min[i] is None or cell < str_min[i]:
                        str_min[i] = cell
                    if str_max[i] is None or cell > str_max[i]:
                        str_max[i] = cell

        stats: List[ColumnStats] = []
        for i in range(ncols):
            itype = _resolve_type(type_counts[i])
            if itype in ("int", "float"):
                cmin = _fmt_num(num_min[i])
                cmax = _fmt_num(num_max[i])
                mean = (num_sum[i] / num_count[i]) if num_count[i] else None
            else:
                cmin, cmax, mean = str_min[i], str_max[i], None
            dest = len(distinct[i])
            stats.append(
                ColumnStats(
                    name=header[i],
                    inferred_type=itype,
                    count=rows,
                    nulls=nulls[i],
                    distinct_estimate=(dest if not distinct_capped[i] else max_distinct),
                    min=cmin,
                    max=cmax,
                    mean=(round(mean, 6) if mean is not None else None),
                    type_counts=type_counts[i],
                    sample_values=samples[i],
                )
            )
        return Profile(path=path, delimiter=delim, rows=rows, columns=ncols, column_stats=stats)
    finally:
        fh.close()


def _fmt_num(v: Optional[float]) -> Optional[str]:
    if v is None:
        return None
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return repr(v)


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------


def clean_csv(
    path: str,
    out_path: str,
    delimiter: Optional[str] = None,
    drop_duplicates: bool = True,
    trim: bool = True,
    drop_empty_rows: bool = True,
    fill_null: Optional[str] = None,
) -> dict:
    """Clean a CSV: trim whitespace, drop duplicate/empty rows, fill nulls.

    Returns a report dict. Streams input to output.
    """
    delim, reader, fh = _open_reader(path, delimiter)
    seen: set = set()
    report = {
        "input": path,
        "output": out_path,
        "rows_in": 0,
        "rows_out": 0,
        "duplicates_removed": 0,
        "empty_rows_removed": 0,
        "cells_filled": 0,
    }
    try:
        with open(out_path, "w", newline="", encoding="utf-8") as out:
            writer = csv.writer(out, delimiter=delim)
            try:
                header = next(reader)
            except StopIteration:
                return report
            if trim:
                header = [h.strip() for h in header]
            writer.writerow(header)

            for record in reader:
                report["rows_in"] += 1
                row = [c.strip() for c in record] if trim else list(record)

                if drop_empty_rows and all(
                    c.strip().lower() in _NULL_TOKENS for c in row
                ):
                    report["empty_rows_removed"] += 1
                    continue

                if fill_null is not None:
                    for i, c in enumerate(row):
                        if c.strip().lower() in _NULL_TOKENS:
                            row[i] = fill_null
                            report["cells_filled"] += 1

                if drop_duplicates:
                    key = tuple(row)
                    if key in seen:
                        report["duplicates_removed"] += 1
                        continue
                    seen.add(key)

                writer.writerow(row)
                report["rows_out"] += 1
        return report
    finally:
        fh.close()


# ---------------------------------------------------------------------------
# Head / select
# ---------------------------------------------------------------------------


def head_csv(path: str, n: int = 10, delimiter: Optional[str] = None) -> dict:
    """Return the first n data rows plus the header."""
    if not isinstance(n, int) or isinstance(n, bool):
        raise TypeError(f"n must be an integer, got {type(n).__name__}")
    if n < 1:
        raise ValueError(f"n must be at least 1, got {n}")
    delim, reader, fh = _open_reader(path, delimiter)
    try:
        try:
            header = next(reader)
        except StopIteration:
            return {"path": path, "header": [], "rows": []}
        rows = []
        for record in reader:
            if len(rows) >= n:
                break
            rows.append(record)
        return {"path": path, "delimiter": delim, "header": header, "rows": rows}
    finally:
        fh.close()


def select_columns(
    path: str,
    columns: List[str],
    delimiter: Optional[str] = None,
    n: Optional[int] = None,
) -> dict:
    """Project a subset of columns (by name) from the CSV."""
    if not columns:
        raise ValueError("columns list must not be empty")
    if n is not None:
        if not isinstance(n, int) or isinstance(n, bool):
            raise TypeError(f"n must be an integer, got {type(n).__name__}")
        if n < 1:
            raise ValueError(f"n must be at least 1, got {n}")
    delim, reader, fh = _open_reader(path, delimiter)
    try:
        try:
            header = next(reader)
        except StopIteration:
            return {"path": path, "header": [], "rows": []}
        idx = []
        missing = []
        for c in columns:
            if c in header:
                idx.append(header.index(c))
            else:
                missing.append(c)
        if missing:
            raise KeyError(f"columns not found: {', '.join(missing)}")
        rows = []
        for record in reader:
            if n is not None and len(rows) >= n:
                break
            rows.append([record[i] if i < len(record) else "" for i in idx])
        return {
            "path": path,
            "delimiter": delim,
            "header": [header[i] for i in idx],
            "rows": rows,
        }
    finally:
        fh.close()
