"""csvlens — part of the Cognis Neural Suite."""
import os as _os

# Tool identity constants — canonical source of truth for the package
TOOL_NAME: str = "csvlens"

def _read_version() -> str:
    """Read the version from VERSION file at the package root, falling back to pyproject."""
    _pkg_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    _ver_file = _os.path.join(_pkg_root, "VERSION")
    try:
        with open(_ver_file, encoding="utf-8") as _f:
            _v = _f.read().strip()
            if _v:
                return _v
    except OSError:
        pass
    return "0.1.0"

TOOL_VERSION: str = _read_version()
__version__ = TOOL_VERSION

try:  # re-export the tool's public API from core
    from csvlens.core import *  # noqa: F401,F403
except Exception:  # pragma: no cover
    pass
