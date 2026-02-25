#!/usr/bin/env python3
"""Integration test for WorkSync MCP server.

Tests tools, prompts, instructions, and guidance delivery.
"""
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
            print(f"Connected: {init_result.serverInfo.name} v{init_result.serverInfo.version}")

            # ---- Instructions ----
            instructions = init_result.instructions or ""
            assert len(instructions) > 100, f"Instructions too short: {len(instructions)} chars"
            assert "Guardrails" in instructions, "Instructions missing Guardrails section"
            assert "Data Model" in instructions, "Instructions missing Data Model section"
            assert "Statuses" in instructions, "Instructions missing Statuses section"
            print(f"\nInstructions: {len(instructions)} chars (has Data Model, Statuses, Guardrails)")

            # ---- Tools ----
            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            print(f"\n{len(tool_names)} tools registered:")
            for t in tool_names:
                print(f"  - {t}")

            expected_tools = [
                "worksync_status", "worksync_projects", "worksync_add_backlog",
                "worksync_update_backlog", "worksync_remove_backlog",
                "worksync_create_sprint", "worksync_update_sprint",
                "worksync_add_story", "worksync_update_story",
                "worksync_done", "worksync_history", "worksync_sync",
                "worksync_guidance",
            ]
            for t in expected_tools:
                assert t in tool_names, f"Missing tool: {t}"

            # ---- Prompts ----
            prompts = await session.list_prompts()
            prompt_names = [p.name for p in prompts.prompts]
            print(f"\n{len(prompt_names)} prompts registered:")
            for p in prompts.prompts:
                print(f"  - {p.name}: {p.description}")

            expected_prompts = ["work_status", "work_sync", "work_focus", "work_done", "add_project"]
            for p in expected_prompts:
                assert p in prompt_names, f"Missing prompt: {p}"

            # ---- Invoke a prompt ----
            prompt_result = await session.get_prompt("work_status", {"project": "demo-main"})
            assert prompt_result.messages, "Prompt returned no messages"
            print(f"\nPrompt 'work_status' returned {len(prompt_result.messages)} message(s)")

            # ---- worksync_status ----
            result = await session.call_tool("worksync_status", {"project": "demo-main"})
            for block in result.content:
                if hasattr(block, "text"):
                    data = json.loads(block.text)
                    stats = data["projects"]["demo-main"]["stats"]
                    print(f"\nStatus: {stats}")
                    for item in data["projects"]["demo-main"]["in_progress_backlog"]:
                        print(f"  In progress: {item['id']}")

            # ---- worksync_guidance ----
            result = await session.call_tool("worksync_guidance", {"project": "demo-main"})
            for block in result.content:
                if hasattr(block, "text"):
                    data = json.loads(block.text)
                    guidance_keys = list(data.get("guidance", {}).keys())
                    print(f"\nGuidance for demo-main: {guidance_keys}")

            # ---- worksync_projects ----
            result = await session.call_tool("worksync_projects", {})
            for block in result.content:
                if hasattr(block, "text"):
                    data = json.loads(block.text)
                    print(f"\nProjects: {list(data.get('projects', {}).keys())}")

            print("\nPASS - All tests passed")


def main():
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
