"""Run FastMCP's HTTP and MCP interfaces on loopback only."""


def main() -> None:
    from .app import mcp

    mcp.run(transport="http", host="127.0.0.1", port=8088)


if __name__ == "__main__":
    main()
