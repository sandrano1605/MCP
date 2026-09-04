"""ARTEL MCP V1.8 entrypoint.

Loads the stable V1.7 tools first, then registers the Microsoft Skills/MCP
integration layer without changing the V1.7 implementation.
"""

from . import app as _v17  # noqa: F401
from . import v18 as _v18  # noqa: F401
from . import v18_cli_tools as _v18_cli_tools  # noqa: F401
from .server import mcp


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
