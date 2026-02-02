"""CSVLENS MCP server — exposes scan() as an MCP tool for Cognis.Studio."""
from __future__ import annotations
from csvlens.core import scan, to_json

def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-csvlens[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print("Install the MCP extra: pip install 'cognis-csvlens[mcp]'")
        return 1
    app = FastMCP("csvlens")

    @app.tool()
    def csvlens_scan(target: str) -> str:
        """Fast CLI for profiling and cleaning huge CSV / Parquet files. Returns JSON findings."""
        return to_json(scan(target))

    app.run()
    return 0
