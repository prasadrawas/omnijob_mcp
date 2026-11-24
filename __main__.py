"""
CLI Entrypoint for running OmniJob MCP Server.
Supports stdio, sse, and streamable-http transports.
"""
import os
import sys
import types
import argparse
from pathlib import Path

# Ensure omnijob_mcp package is importable regardless of working directory
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_ROOT.parent))

if "omnijob_mcp" not in sys.modules:
    try:
        import omnijob_mcp  # type: ignore
    except ModuleNotFoundError:
        _pkg = types.ModuleType("omnijob_mcp")
        _pkg.__path__ = [str(_ROOT)]
        _pkg.__file__ = str(_ROOT / "__init__.py")
        sys.modules["omnijob_mcp"] = _pkg

from omnijob_mcp.server import run_server


def main():
    parser = argparse.ArgumentParser(
        description="omnijob-mcp: Unified 7-Platform Model Context Protocol Server (Naukri, Hirist, Wellfound, Instahyre, Cutshort, Greenhouse, Foundit)"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="Transport mode (default: stdio or MCP_TRANSPORT env)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", 8000)),
        help="Port for HTTP/SSE mode (default: PORT env or 8000)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host for HTTP/SSE mode (default: 0.0.0.0)",
    )
    args = parser.parse_args()
    run_server(transport=args.transport, port=args.port, host=args.host)


if __name__ == "__main__":
    main()
