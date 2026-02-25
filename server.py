#!/usr/bin/env python3
"""
WorkSync MCP Server

Shared MCP server for multi-agent WorkSync coordination.
Provides single-writer access to work-index.yaml files with automatic vault sync.

Usage:
    python server.py                          # default: ~/.worksync on port 8321
    WORKSYNC_DATA_ROOT=/path python server.py # custom data root
    WORKSYNC_PORT=9000 python server.py       # custom port
"""

import logging
import os
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

import yaml
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_ROOT = Path(os.environ.get("WORKSYNC_DATA_ROOT", "~/.worksync")).expanduser().resolve()
HOST = os.environ.get("WORKSYNC_HOST", "127.0.0.1")
PORT = int(os.environ.get("WORKSYNC_PORT", "8321"))
AUTO_SYNC = os.environ.get("WORKSYNC_AUTO_SYNC", "true").lower() in ("true", "1", "yes")
SYNC_DEBOUNCE_SEC = float(os.environ.get("WORKSYNC_SYNC_DEBOUNCE", "2.0"))

CONFIG_PATH = DATA_ROOT / "config.yaml"
SYNC_PY_PATH = DATA_ROOT / "sync.py"

YAML_HEADER = "# yaml-language-server: $schema=./SCHEMA/work-flow-schema.json\n\n"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("worksync-mcp")

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "WorkSync",
    instructions="Multi-agent work tracking with Obsidian vault sync",
    host=HOST,
    port=PORT,
)

# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------

_mtime_cache: dict[str, float] = {}
_sync_timers: dict[str, threading.Timer] = {}
_lock = threading.Lock()  # protects file writes (single-writer within server)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    """Load WorkSync config.yaml."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config not found at {CONFIG_PATH}")
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}


def _validate_project(project: str) -> Path:
    """Validate project exists and return its directory."""
    config = _load_config()
    projects = config.get("projects", {})
    if project not in projects:
        available = ", ".join(projects.keys()) or "(none)"
        raise ValueError(f"Project '{project}' not found. Available: {available}")
    project_dir = DATA_ROOT / "projects" / project
    if not project_dir.exists():
        raise FileNotFoundError(f"Project directory not found at {project_dir}")
    return project_dir


def _yaml_path(project: str) -> Path:
    """Get the work-index.yaml path for a project."""
    return DATA_ROOT / "projects" / project / "work-index.yaml"


def _load_work_index(project: str) -> dict:
    """Load work-index.yaml with external edit detection."""
    path = _yaml_path(project)
    if not path.exists():
        raise FileNotFoundError(f"work-index.yaml not found for project '{project}'")

    current_mtime = path.stat().st_mtime
    cached_mtime = _mtime_cache.get(str(path))

    if cached_mtime is not None and current_mtime != cached_mtime:
        logger.warning(
            "External edit detected on %s. Reloading from disk (human edit accepted).",
            path,
        )

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    _mtime_cache[str(path)] = current_mtime
    return data


def _save_work_index(project: str, data: dict, agent: str = "unknown"):
    """Atomically write work-index.yaml with YAML header preservation."""
    path = _yaml_path(project)
    content = YAML_HEADER + yaml.dump(data, default_flow_style=False, sort_keys=False)

    with _lock:
        fd, tmp = tempfile.mkstemp(suffix=".yaml.tmp", dir=str(path.parent))
        try:
            os.write(fd, content.encode())
            os.close(fd)
            fd = None

            # Validate before committing
            with open(tmp) as f:
                yaml.safe_load(f)

            os.replace(tmp, path)
            _mtime_cache[str(path)] = path.stat().st_mtime

            logger.info("Wrote %s (agent: %s)", path.name, agent)

        except Exception:
            if fd is not None:
                os.close(fd)
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # Debounced vault sync
    if AUTO_SYNC:
        _queue_sync(project)


def _queue_sync(project: str):
    """Debounce vault sync: wait SYNC_DEBOUNCE_SEC after last mutation."""
    if project in _sync_timers:
        _sync_timers[project].cancel()
    timer = threading.Timer(SYNC_DEBOUNCE_SEC, _run_sync, [project])
    timer.daemon = True
    _sync_timers[project] = timer
    timer.start()


def _run_sync(project: str):
    """Call sync.py with --root pointing to DATA_ROOT."""
    if not SYNC_PY_PATH.exists():
        logger.warning("sync.py not found at %s, skipping vault sync", SYNC_PY_PATH)
        return
    try:
        result = subprocess.run(
            [sys.executable, str(SYNC_PY_PATH), "--root", str(DATA_ROOT), project],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info("Vault synced for %s", project)
        else:
            logger.error("Vault sync failed for %s: %s", project, result.stderr)
    except subprocess.TimeoutExpired:
        logger.error("Vault sync timed out for %s", project)
    except Exception as e:
        logger.error("Vault sync error for %s: %s", project, e)


def _now_iso() -> str:
    """Current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    """Current date as YYYY-MM-DD."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def worksync_status(project: str | None = None) -> dict:
    """Show active sprints and in-progress work.

    Args:
        project: Project name to filter. If omitted, shows all projects.

    Returns:
        Dict with per-project sprints, in-progress stories, and backlog stats.
    """
    config = _load_config()
    projects = config.get("projects", {})

    if project:
        if project not in projects:
            return {"error": f"Project '{project}' not found"}
        project_list = [project]
    else:
        project_list = list(projects.keys())

    result = {"projects": {}}
    for name in project_list:
        try:
            data = _load_work_index(name)
        except FileNotFoundError:
            result["projects"][name] = {"error": "work-index.yaml not found"}
            continue

        sprints = data.get("sprints", [])
        backlog = data.get("backlog", [])

        active_sprints = [s for s in sprints if s.get("status") == "active"]
        in_progress_stories = []
        for sprint in sprints:
            for story in sprint.get("stories", []):
                if isinstance(story, dict) and story.get("status") == "in_progress":
                    in_progress_stories.append({
                        **story,
                        "sprint": sprint["id"],
                    })

        in_progress_backlog = [b for b in backlog if b.get("status") == "in_progress"]

        result["projects"][name] = {
            "sprints": active_sprints,
            "in_progress_stories": in_progress_stories,
            "in_progress_backlog": in_progress_backlog,
            "stats": {
                "total_backlog": len(backlog),
                "todo": len([b for b in backlog if b.get("status") == "todo"]),
                "in_progress": len(in_progress_backlog),
                "done": len([b for b in backlog if b.get("status") == "done"]),
            },
        }

    return result


@mcp.tool()
def worksync_projects(project: str | None = None) -> dict:
    """List all registered projects or get details for one.

    Args:
        project: Specific project name. If omitted, lists all.

    Returns:
        Project registry with repo paths, descriptions, and guidance config.
    """
    config = _load_config()
    projects = config.get("projects", {})

    if project:
        if project not in projects:
            return {"error": f"Project '{project}' not found"}
        return {"project": project, **projects[project]}

    return {"projects": projects}


@mcp.tool()
def worksync_add_backlog(
    project: str,
    id: str,
    summary: str,
    theme: str,
    status: str = "todo",
    related_sprints: list[str] | None = None,
    agent: str = "unknown",
) -> dict:
    """Add a new item to the project backlog.

    Args:
        project: Project name (must exist in config.yaml).
        id: Unique identifier (kebab-case, e.g., 'cicd-sha-pinning').
        summary: Short description of the work.
        theme: Category (e.g., 'security', 'devops', 'infrastructure').
        status: Initial status. One of: todo, in_progress, done.
        related_sprints: Optional list of sprint IDs this relates to.
        agent: Agent making the change (auto-set from header if available).

    Returns:
        The created backlog item.
    """
    _validate_project(project)
    data = _load_work_index(project)

    if status not in ("todo", "in_progress", "done"):
        return {"error": f"Invalid status '{status}'. Must be: todo, in_progress, done"}

    backlog = data.setdefault("backlog", [])
    if any(item.get("id") == id for item in backlog):
        return {"error": f"Backlog item '{id}' already exists"}

    new_item = {
        "id": id,
        "theme": theme,
        "summary": summary,
        "status": status,
        "related_sprints": related_sprints or [],
    }
    backlog.append(new_item)

    _save_work_index(project, data, agent)
    logger.info("Added backlog item '%s' to %s (agent: %s)", id, project, agent)
    return {"created": new_item}


@mcp.tool()
def worksync_update_backlog(
    project: str,
    id: str,
    status: str | None = None,
    summary: str | None = None,
    theme: str | None = None,
    related_sprints: list[str] | None = None,
    agent: str = "unknown",
) -> dict:
    """Update a backlog item. Only provided fields are changed.

    Args:
        project: Project name.
        id: Backlog item ID to update.
        status: New status (todo | in_progress | done).
        summary: New summary text.
        theme: New theme.
        related_sprints: New related sprints list (replaces existing).
        agent: Agent making the change.

    Returns:
        The updated backlog item.
    """
    _validate_project(project)
    data = _load_work_index(project)

    backlog = data.get("backlog", [])
    item = next((b for b in backlog if b.get("id") == id), None)
    if not item:
        return {"error": f"Backlog item '{id}' not found"}

    if status is not None:
        if status not in ("todo", "in_progress", "done"):
            return {"error": f"Invalid status '{status}'"}
        item["status"] = status
    if summary is not None:
        item["summary"] = summary
    if theme is not None:
        item["theme"] = theme
    if related_sprints is not None:
        item["related_sprints"] = related_sprints

    _save_work_index(project, data, agent)
    logger.info("Updated backlog '%s' in %s (agent: %s)", id, project, agent)
    return {"updated": item}


@mcp.tool()
def worksync_remove_backlog(
    project: str,
    id: str,
    agent: str = "unknown",
) -> dict:
    """Remove a backlog item by ID.

    Args:
        project: Project name.
        id: Backlog item ID to remove.
        agent: Agent making the change.

    Returns:
        The removed item (for confirmation).
    """
    _validate_project(project)
    data = _load_work_index(project)

    backlog = data.get("backlog", [])
    item = next((b for b in backlog if b.get("id") == id), None)
    if not item:
        return {"error": f"Backlog item '{id}' not found"}

    backlog.remove(item)

    _save_work_index(project, data, agent)
    logger.info("Removed backlog '%s' from %s (agent: %s)", id, project, agent)
    return {"removed": item}


@mcp.tool()
def worksync_create_sprint(
    project: str,
    id: str,
    title: str,
    goal: str = "",
    themes: list[str] | None = None,
    status: str = "planned",
    agent: str = "unknown",
) -> dict:
    """Create a new sprint.

    Args:
        project: Project name.
        id: Sprint identifier (kebab-case).
        title: Human-readable sprint title.
        goal: What the sprint aims to achieve.
        themes: Cross-cutting themes this sprint relates to.
        status: Initial status (planned | active | reference | completed).
        agent: Agent making the change.

    Returns:
        The created sprint.
    """
    _validate_project(project)
    data = _load_work_index(project)

    valid_statuses = ("planned", "active", "reference", "completed")
    if status not in valid_statuses:
        return {"error": f"Invalid status '{status}'. Must be one of: {valid_statuses}"}

    sprints = data.setdefault("sprints", [])
    if any(s.get("id") == id for s in sprints):
        return {"error": f"Sprint '{id}' already exists"}

    new_sprint = {
        "id": id,
        "title": title,
        "file": f"{id.upper()}.md",
        "status": status,
        "goal": goal,
        "themes": themes or [],
        "stories": [],
    }
    sprints.append(new_sprint)

    _save_work_index(project, data, agent)
    logger.info("Created sprint '%s' in %s (agent: %s)", id, project, agent)
    return {"created": new_sprint}


@mcp.tool()
def worksync_update_sprint(
    project: str,
    id: str,
    status: str | None = None,
    title: str | None = None,
    goal: str | None = None,
    themes: list[str] | None = None,
    agent: str = "unknown",
) -> dict:
    """Update a sprint. Only provided fields are changed.

    Args:
        project: Project name.
        id: Sprint ID to update.
        status: New status (planned | active | reference | completed).
        title: New title.
        goal: New goal.
        themes: New themes list (replaces existing).
        agent: Agent making the change.

    Returns:
        The updated sprint.
    """
    _validate_project(project)
    data = _load_work_index(project)

    sprints = data.get("sprints", [])
    sprint = next((s for s in sprints if s.get("id") == id), None)
    if not sprint:
        return {"error": f"Sprint '{id}' not found"}

    if status is not None:
        valid = ("planned", "active", "reference", "completed")
        if status not in valid:
            return {"error": f"Invalid status '{status}'. Must be one of: {valid}"}
        sprint["status"] = status
    if title is not None:
        sprint["title"] = title
    if goal is not None:
        sprint["goal"] = goal
    if themes is not None:
        sprint["themes"] = themes

    _save_work_index(project, data, agent)
    logger.info("Updated sprint '%s' in %s (agent: %s)", id, project, agent)
    return {"updated": sprint}


@mcp.tool()
def worksync_add_story(
    project: str,
    sprint_id: str,
    story_id: str,
    status: str = "planned",
    notes: str = "",
    agent: str = "unknown",
) -> dict:
    """Add a story to a sprint.

    Args:
        project: Project name.
        sprint_id: Sprint to add the story to.
        story_id: Story identifier (e.g., 'STORY-1').
        status: Initial status (planned | in_progress | done).
        notes: Optional notes about scope or context.
        agent: Agent making the change.

    Returns:
        The created story.
    """
    _validate_project(project)
    data = _load_work_index(project)

    valid_statuses = ("planned", "in_progress", "done")
    if status not in valid_statuses:
        return {"error": f"Invalid status '{status}'. Must be one of: {valid_statuses}"}

    sprints = data.get("sprints", [])
    sprint = next((s for s in sprints if s.get("id") == sprint_id), None)
    if not sprint:
        return {"error": f"Sprint '{sprint_id}' not found"}

    stories = sprint.setdefault("stories", [])
    if any(s.get("id") == story_id for s in stories if isinstance(s, dict)):
        return {"error": f"Story '{story_id}' already exists in sprint '{sprint_id}'"}

    new_story = {"id": story_id, "status": status}
    if notes:
        new_story["notes"] = notes
    stories.append(new_story)

    _save_work_index(project, data, agent)
    logger.info("Added story '%s' to sprint '%s' in %s (agent: %s)", story_id, sprint_id, project, agent)
    return {"created": new_story, "sprint": sprint_id}


@mcp.tool()
def worksync_update_story(
    project: str,
    sprint_id: str,
    story_id: str,
    status: str | None = None,
    notes: str | None = None,
    agent: str = "unknown",
) -> dict:
    """Update a story within a sprint.

    Args:
        project: Project name.
        sprint_id: Sprint containing the story.
        story_id: Story ID to update.
        status: New status (planned | in_progress | done).
        notes: New or appended notes.
        agent: Agent making the change.

    Returns:
        The updated story.
    """
    _validate_project(project)
    data = _load_work_index(project)

    sprints = data.get("sprints", [])
    sprint = next((s for s in sprints if s.get("id") == sprint_id), None)
    if not sprint:
        return {"error": f"Sprint '{sprint_id}' not found"}

    stories = sprint.get("stories", [])
    story = next((s for s in stories if isinstance(s, dict) and s.get("id") == story_id), None)
    if not story:
        return {"error": f"Story '{story_id}' not found in sprint '{sprint_id}'"}

    if status is not None:
        valid = ("planned", "in_progress", "done")
        if status not in valid:
            return {"error": f"Invalid status '{status}'. Must be one of: {valid}"}
        story["status"] = status
    if notes is not None:
        story["notes"] = notes

    _save_work_index(project, data, agent)
    logger.info("Updated story '%s' in sprint '%s' (agent: %s)", story_id, sprint_id, agent)
    return {"updated": story, "sprint": sprint_id}


@mcp.tool()
def worksync_done(
    project: str,
    story_id: str,
    notes: str = "",
    sprint_id: str | None = None,
    agent: str = "unknown",
) -> dict:
    """Mark a story as done, add notes, and append a history entry.

    If sprint_id is not provided, searches all sprints for the story.

    Args:
        project: Project name.
        story_id: Story to mark as done.
        notes: Completion notes.
        sprint_id: Sprint containing the story (auto-detected if omitted).
        agent: Agent making the change.

    Returns:
        Dict with updated story and new history entry.
    """
    _validate_project(project)
    data = _load_work_index(project)

    # Find the story
    found_sprint = None
    found_story = None

    for sprint in data.get("sprints", []):
        if sprint_id and sprint.get("id") != sprint_id:
            continue
        for story in sprint.get("stories", []):
            if isinstance(story, dict) and story.get("id") == story_id:
                found_sprint = sprint
                found_story = story
                break
        if found_story:
            break

    if not found_story:
        scope = f"sprint '{sprint_id}'" if sprint_id else "any sprint"
        return {"error": f"Story '{story_id}' not found in {scope}"}

    # Update story
    found_story["status"] = "done"
    if notes:
        found_story["notes"] = notes

    # Append history
    history = data.setdefault("history", [])
    history_entry = {
        "date": _today(),
        "summary": f"Completed {story_id}: {notes}" if notes else f"Completed {story_id}",
        "related_sprints": [found_sprint["id"]],
    }
    history.append(history_entry)

    _save_work_index(project, data, agent)
    logger.info("Marked story '%s' done in sprint '%s' (agent: %s)", story_id, found_sprint["id"], agent)
    return {
        "updated_story": found_story,
        "sprint": found_sprint["id"],
        "history_entry": history_entry,
    }


@mcp.tool()
def worksync_history(
    project: str,
    action: str = "list",
    summary: str | None = None,
    related_sprints: list[str] | None = None,
    agent: str = "unknown",
) -> dict:
    """View or append project history.

    Args:
        project: Project name.
        action: 'list' to view, 'add' to append a new entry.
        summary: Summary text (required when action='add').
        related_sprints: Sprint IDs related to the entry.
        agent: Agent making the change.

    Returns:
        List of history entries, or the newly created entry.
    """
    _validate_project(project)
    data = _load_work_index(project)

    if action == "list":
        return {"history": data.get("history", [])}

    if action == "add":
        if not summary:
            return {"error": "summary is required when action='add'"}

        history = data.setdefault("history", [])
        entry = {
            "date": _today(),
            "summary": summary,
        }
        if related_sprints:
            entry["related_sprints"] = related_sprints

        history.append(entry)
        _save_work_index(project, data, agent)
        logger.info("Added history entry to %s (agent: %s)", project, agent)
        return {"created": entry}

    return {"error": f"Invalid action '{action}'. Must be 'list' or 'add'"}


@mcp.tool()
def worksync_sync(project: str | None = None) -> dict:
    """Regenerate the Obsidian vault from YAML source files.

    Calls sync.py internally. Idempotent.

    Args:
        project: Specific project to sync. If omitted, syncs all.

    Returns:
        Sync results.
    """
    if not SYNC_PY_PATH.exists():
        return {"error": f"sync.py not found at {SYNC_PY_PATH}"}

    cmd = [sys.executable, str(SYNC_PY_PATH), "--root", str(DATA_ROOT)]
    if project:
        _validate_project(project)
        cmd.append(project)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return {
                "status": "success",
                "project": project or "all",
                "output": result.stdout,
            }
        else:
            return {
                "status": "error",
                "project": project or "all",
                "error": result.stderr,
            }
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "Sync timed out after 60 seconds"}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    """Start the WorkSync MCP server."""
    logger.info("WorkSync MCP Server starting")
    logger.info("  Data root: %s", DATA_ROOT)
    logger.info("  Config:    %s", CONFIG_PATH)
    logger.info("  Sync:      %s", SYNC_PY_PATH)
    logger.info("  Endpoint:  http://%s:%d/mcp", HOST, PORT)
    logger.info("  Auto-sync: %s (debounce: %.1fs)", AUTO_SYNC, SYNC_DEBOUNCE_SEC)

    # Validate config exists
    if not CONFIG_PATH.exists():
        logger.error("Config not found at %s. Run data migration first.", CONFIG_PATH)
        sys.exit(1)

    # List registered projects
    config = _load_config()
    projects = list(config.get("projects", {}).keys())
    logger.info("  Projects:  %s", ", ".join(projects) or "(none)")

    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
