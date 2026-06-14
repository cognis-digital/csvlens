"""CSVLENS MCP server — exposes profile_csv() as an MCP tool for Cognis.Studio."""
from __future__ import annotations
import json


def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-csvlens[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print("Install the MCP extra: pip install 'cognis-csvlens[mcp]'")
        return 1

    from csvlens.core import profile_csv

    app = FastMCP("csvlens")

    @app.tool()
    def csvlens_scan(target: str) -> str:
        """Profile a CSV file and return JSON findings (column stats, types, null counts)."""
        try:
            prof = profile_csv(target)
            return json.dumps(prof.to_dict(), indent=2)
        except FileNotFoundError:
            return json.dumps({"error": f"file not found: {target}"})
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

    app.run()
    return 0
