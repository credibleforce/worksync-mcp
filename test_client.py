#!/usr/bin/env python3
"""Quick integration test for WorkSync MCP server."""
import asyncio
import json
import subprocess
import sys
import time

VENV_PYTHON = str(sys.executable)
SERVER_SCRIPT = "/home/jamie/.worksync/server.py"


async def run_client():
    from mcp.client.streamable_http import streamablehttp_client
    from mcp import ClientSession

    async with streamablehttp_client("http://127.0.0.1:8321/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            init_result = await session.initialize()
            print(f"Connected: {init_result.serverInfo}")

            # List tools
            tools = await session.list_tools()
            print(f"\n{len(tools.tools)} tools registered:")
            for t in tools.tools:
                print(f"  - {t.name}")

            # worksync_status
            result = await session.call_tool("worksync_status", {"project": "demo-main"})
            for block in result.content:
                if hasattr(block, "text"):
                    data = json.loads(block.text)
                    stats = data["projects"]["demo-main"]["stats"]
                    print(f"\nStatus: {stats}")
                    for item in data["projects"]["demo-main"]["in_progress_backlog"]:
                        print(f"  In progress: {item['id']}")

            # worksync_projects
            result = await session.call_tool("worksync_projects", {})
            for block in result.content:
                if hasattr(block, "text"):
                    data = json.loads(block.text)
                    print(f"\nProjects: {list(data.get('projects', {}).keys())}")

            print("\nPASS - All tests passed")


def main():
    # Start server
    server = subprocess.Popen(
        [VENV_PYTHON, SERVER_SCRIPT],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    time.sleep(3)

    try:
        asyncio.run(run_client())
    finally:
        server.terminate()
        server.wait(timeout=5)


if __name__ == "__main__":
    main()
