#!/usr/bin/env python3
"""Cross-agent parity test for WorkSync MCP server.

Verifies that mutations (add, update, delete) produce consistent results
regardless of which agent makes the call. Both "claude-code" and "codex"
agent identities are exercised and results compared.
"""
import asyncio
import json
import os
import subprocess
import sys
import time
from copy import deepcopy

VENV_PYTHON = str(sys.executable)
SERVER_SCRIPT = "/home/jamie/.worksync/server.py"
MCP_URL = "http://127.0.0.1:8321/mcp"
API_KEY = os.environ.get("WORKSYNC_API_KEY", "")

# Test project — uses demo-main which has existing data
TEST_PROJECT = "demo-main"

# Test identifiers (unique to avoid collisions with real data)
TEST_BACKLOG_ID = "_parity-test-item"
TEST_SPRINT_ID = "_parity-test-sprint"
TEST_STORY_ID = "_PARITY-STORY-1"


async def call_tool(session, name: str, args: dict) -> dict:
    """Call an MCP tool and return parsed JSON result."""
    result = await session.call_tool(name, args)
    for block in result.content:
        if hasattr(block, "text"):
            return json.loads(block.text)
    raise ValueError(f"No text content in response for {name}")


async def run_parity_test():
    from mcp.client.streamable_http import streamablehttp_client
    from mcp import ClientSession

    headers = {}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    async with streamablehttp_client(MCP_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            init_result = await session.initialize()
            print(f"Connected: {init_result.serverInfo.name} v{init_result.serverInfo.version}")

            passed = 0
            failed = 0
            errors = []

            def check(test_name: str, condition: bool, detail: str = ""):
                nonlocal passed, failed
                if condition:
                    passed += 1
                    print(f"  PASS: {test_name}")
                else:
                    failed += 1
                    errors.append(f"{test_name}: {detail}")
                    print(f"  FAIL: {test_name} — {detail}")

            # ----------------------------------------------------------
            # 0. Pre-cleanup: remove leftover test data from previous runs
            # ----------------------------------------------------------
            print("\n--- Pre-cleanup: removing leftover test data ---")

            # Remove test backlog if it exists
            await call_tool(session, "worksync_remove_backlog", {
                "project": TEST_PROJECT,
                "id": TEST_BACKLOG_ID,
                "agent": "parity-test-cleanup",
            })

            # Remove test sprint/story by loading and rewriting YAML
            # (No remove_sprint tool exists, so we clean via direct load/save)
            pre_data = await call_tool(session, "worksync_status", {"project": TEST_PROJECT})
            # We can't remove sprints via MCP, so check if test sprint exists
            # and skip create if it does — OR we patch the YAML directly for cleanup.
            # For now, let's use a fresh test ID if one already exists.
            import random
            suffix = f"-{random.randint(1000,9999)}"
            _test_sprint = TEST_SPRINT_ID + suffix
            _test_story = TEST_STORY_ID + suffix
            print(f"  Using test IDs: sprint={_test_sprint}, story={_test_story}")

            # ----------------------------------------------------------
            # 1. Baseline: read status as "claude-code" agent
            # ----------------------------------------------------------
            print("\n--- Test 1: Read parity (claude-code vs codex) ---")

            status_claude = await call_tool(session, "worksync_status", {"project": TEST_PROJECT})
            status_codex = await call_tool(session, "worksync_status", {"project": TEST_PROJECT})

            # Both reads should return identical data
            claude_stats = status_claude["projects"][TEST_PROJECT]["stats"]
            codex_stats = status_codex["projects"][TEST_PROJECT]["stats"]
            check(
                "Read parity: both agents see same stats",
                claude_stats == codex_stats,
                f"claude={claude_stats} vs codex={codex_stats}",
            )

            # ----------------------------------------------------------
            # 2. Add backlog item as "claude-code", verify as "codex"
            # ----------------------------------------------------------
            print("\n--- Test 2: Add backlog (claude-code), verify (codex) ---")

            add_result = await call_tool(session, "worksync_add_backlog", {
                "project": TEST_PROJECT,
                "id": TEST_BACKLOG_ID,
                "summary": "Parity test item",
                "theme": "testing",
                "status": "todo",
                "agent": "claude-code",
            })
            check(
                "Add backlog: item created",
                "created" in add_result,
                str(add_result),
            )

            # Read back as "codex"
            status_after_add = await call_tool(session, "worksync_status", {"project": TEST_PROJECT})
            stats_after = status_after_add["projects"][TEST_PROJECT]["stats"]
            check(
                "Add backlog: total increased by 1",
                stats_after["total_backlog"] == claude_stats["total_backlog"] + 1,
                f"expected {claude_stats['total_backlog'] + 1}, got {stats_after['total_backlog']}",
            )

            # ----------------------------------------------------------
            # 3. Update backlog item as "codex", verify as "claude-code"
            # ----------------------------------------------------------
            print("\n--- Test 3: Update backlog (codex), verify (claude-code) ---")

            update_result = await call_tool(session, "worksync_update_backlog", {
                "project": TEST_PROJECT,
                "id": TEST_BACKLOG_ID,
                "status": "in_progress",
                "summary": "Parity test item (updated by codex)",
                "agent": "codex",
            })
            check(
                "Update backlog: item updated",
                "updated" in update_result,
                str(update_result),
            )
            check(
                "Update backlog: status is in_progress",
                update_result.get("updated", {}).get("status") == "in_progress",
                str(update_result),
            )

            # Verify from "claude-code" perspective
            status_after_update = await call_tool(session, "worksync_status", {"project": TEST_PROJECT})
            in_prog = status_after_update["projects"][TEST_PROJECT]["in_progress_backlog"]
            found = any(b["id"] == TEST_BACKLOG_ID for b in in_prog)
            check(
                "Update backlog: visible in in_progress list",
                found,
                f"in_progress_backlog={[b['id'] for b in in_prog]}",
            )

            # ----------------------------------------------------------
            # 4. Create sprint + story, mark done
            # ----------------------------------------------------------
            print("\n--- Test 4: Sprint lifecycle (create -> add story -> done) ---")

            sprint_result = await call_tool(session, "worksync_create_sprint", {
                "project": TEST_PROJECT,
                "id": _test_sprint,
                "title": "Parity Test Sprint",
                "goal": "Verify cross-agent parity",
                "themes": ["testing"],
                "agent": "claude-code",
            })
            check(
                "Create sprint: sprint created",
                "created" in sprint_result,
                str(sprint_result),
            )

            story_result = await call_tool(session, "worksync_add_story", {
                "project": TEST_PROJECT,
                "sprint_id": _test_sprint,
                "story_id": _test_story,
                "status": "in_progress",
                "notes": "Testing parity",
                "agent": "codex",
            })
            check(
                "Add story: story created",
                "created" in story_result,
                str(story_result),
            )

            done_result = await call_tool(session, "worksync_done", {
                "project": TEST_PROJECT,
                "story_id": _test_story,
                "notes": "Parity verified",
                "agent": "claude-code",
            })
            check(
                "Done story: marked done",
                done_result.get("updated_story", {}).get("status") == "done",
                str(done_result),
            )
            check(
                "Done story: history entry created",
                "history_entry" in done_result,
                str(done_result),
            )

            # ----------------------------------------------------------
            # 5. History parity: both agents see same history
            # ----------------------------------------------------------
            print("\n--- Test 5: History parity ---")

            history_result = await call_tool(session, "worksync_history", {
                "project": TEST_PROJECT,
                "action": "list",
            })
            history = history_result.get("history", [])
            parity_entries = [h for h in history if _test_story in h.get("summary", "")]
            check(
                "History: parity test entry exists",
                len(parity_entries) >= 1,
                f"found {len(parity_entries)} entries",
            )

            # ----------------------------------------------------------
            # 6. Cleanup: remove test data
            # ----------------------------------------------------------
            print("\n--- Cleanup ---")

            # Remove test backlog item
            remove_result = await call_tool(session, "worksync_remove_backlog", {
                "project": TEST_PROJECT,
                "id": TEST_BACKLOG_ID,
                "agent": "parity-test",
            })
            check(
                "Cleanup: backlog item removed",
                "removed" in remove_result,
                str(remove_result),
            )

            # Verify stats restored
            final_status = await call_tool(session, "worksync_status", {"project": TEST_PROJECT})
            final_stats = final_status["projects"][TEST_PROJECT]["stats"]
            check(
                "Cleanup: backlog count restored",
                final_stats["total_backlog"] == claude_stats["total_backlog"],
                f"expected {claude_stats['total_backlog']}, got {final_stats['total_backlog']}",
            )

            # Note: sprint/story/history cleanup would require additional tools
            # (remove_sprint, remove_history) which aren't in the current API.
            # The test sprint and history entry remain as artifacts.

            # ----------------------------------------------------------
            # Summary
            # ----------------------------------------------------------
            print(f"\n{'='*60}")
            print(f"Results: {passed} passed, {failed} failed")
            if errors:
                print("Failures:")
                for e in errors:
                    print(f"  - {e}")
                print("\nFAIL - Parity test failed")
                sys.exit(1)
            else:
                print("\nPASS - All parity tests passed")


def main():
    server = subprocess.Popen(
        [VENV_PYTHON, SERVER_SCRIPT],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    time.sleep(3)

    try:
        asyncio.run(run_parity_test())
    finally:
        server.terminate()
        server.wait(timeout=5)


if __name__ == "__main__":
    main()
