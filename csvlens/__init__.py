"""csvlens — fast CLI for profiling and cleaning CSV files (stdlib only)."""
from .core import (
    profile_csv,
    clean_csv,
    head_csv,
    select_columns,
    ColumnStats,
    Profile,
    detect_dialect,
)

TOOL_NAME = "csvlens"
TOOL_VERSION = "1.0.0"

__all__ = [
    "TOOL_NAME",
    "TOOL_VERSION",
    "profile_csv",
    "clean_csv",
    "head_csv",
    "select_columns",
    "ColumnStats",
    "Profile",
    "detect_dialect",
]
