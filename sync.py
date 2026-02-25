#!/usr/bin/env python3
"""
WorkSync Vault Sync

Generates Obsidian vault content from work-index.yaml files.

Usage:
    python sync.py                           # sync all projects (skill-relative)
    python sync.py sample-project            # sync specific project
    python sync.py --root ~/.worksync        # use explicit data root
    python sync.py --root ~/.worksync demo   # explicit root + specific project
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml


# Default: resolve relative to this script's parent (skill layout).
# Override with --root or WORKSYNC_DATA_ROOT env var for MCP server usage.
_DEFAULT_ROOT = Path(__file__).parent.parent

DATA_ROOT = _DEFAULT_ROOT
CONFIG_PATH = DATA_ROOT / "config.yaml"
GUIDANCE_DIR = DATA_ROOT / "guidance"


def set_data_root(root: Path):
    """Override the data root directory. Called by main() or by MCP server."""
    global DATA_ROOT, CONFIG_PATH, GUIDANCE_DIR
    DATA_ROOT = root.expanduser().resolve()
    CONFIG_PATH = DATA_ROOT / "config.yaml"
    GUIDANCE_DIR = DATA_ROOT / "guidance"


def load_config() -> dict:
    """Load WorkSync configuration."""
    if not CONFIG_PATH.exists():
        print(f"Error: Config not found at {CONFIG_PATH}")
        sys.exit(1)

    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_work_index(project_dir: Path) -> dict:
    """Load work-index.yaml for a project."""
    index_path = project_dir / "work-index.yaml"
    if not index_path.exists():
        print(f"  Warning: work-index.yaml not found at {index_path}")
        return None

    with open(index_path) as f:
        return yaml.safe_load(f)


def frontmatter(data: dict) -> str:
    """Generate YAML frontmatter block."""
    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}: {value}")
        elif isinstance(value, str) and "\n" in value:
            lines.append(f"{key}: |")
            for line in value.split("\n"):
                lines.append(f"  {line}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def generate_sprint_file(sprint: dict, project_name: str) -> str:
    """Generate markdown content for a sprint."""
    # Build tags for graph filtering: type, status, project
    tags = [project_name, "sprint", sprint["status"]]
    tags.extend(sprint.get("themes", []))

    fm = frontmatter({
        "type": "sprint",
        "id": sprint["id"],
        "project": project_name,
        "status": sprint["status"],
        "themes": sprint.get("themes", []),
        "tags": tags,
    })

    content = [fm, "", f"# {sprint['title']}", ""]

    if sprint.get("goal"):
        content.extend(["## Goal", "", sprint["goal"], ""])

    if sprint.get("notes"):
        content.extend(["## Notes", "", sprint["notes"], ""])

    # Stories summary
    stories = sprint.get("stories", [])
    if stories:
        content.extend(["## Stories", ""])
        content.append("| ID | Status | Notes |")
        content.append("|-----|--------|-------|")
        for story in stories:
            # Skip non-dict entries (e.g., stray strings from acceptance criteria)
            if not isinstance(story, dict):
                continue
            notes = story.get("notes", "")[:50] + "..." if len(story.get("notes", "")) > 50 else story.get("notes", "")
            notes = notes.replace("\n", " ")
            content.append(f"| [[{story['id']}]] | {story['status']} | {notes} |")
        content.append("")

    # Themes with wiki-links for graph connectivity
    themes = sprint.get("themes", [])
    if themes:
        theme_links = ", ".join([f"[[{t}]]" for t in themes])
        content.extend(["## Themes", "", theme_links, ""])

    # Link to source file
    if sprint.get("file"):
        content.extend(["## Source", "", f"Sprint doc: `{sprint['file']}`", ""])

    return "\n".join(content)


def generate_story_file(story: dict, sprint: dict, project_name: str) -> str:
    """Generate markdown content for a story."""
    # Build tags for graph filtering: type, status, project, themes
    themes = sprint.get("themes", [])
    tags = [project_name, "story", story["status"]]
    tags.extend(themes)

    fm = frontmatter({
        "type": "story",
        "id": story["id"],
        "project": project_name,
        "sprint": sprint["id"],
        "status": story["status"],
        "themes": themes,
        "tags": tags,
    })

    content = [fm, "", f"# {story['id']}", ""]

    # Wiki-links for themes to enable graph connectivity
    theme_links = ", ".join([f"[[{t}]]" for t in themes]) if themes else "None"

    content.extend([
        "## Overview", "",
        f"**Sprint:** [[{sprint['id']}]]  ",
        f"**Status:** {story['status']}  ",
        f"**Themes:** {theme_links}",
        ""
    ])

    if story.get("notes"):
        content.extend(["## Notes", "", story["notes"], ""])

    return "\n".join(content)


def generate_backlog_file(item: dict, project_name: str) -> str:
    """Generate markdown content for a backlog item."""
    # Build tags for graph filtering
    theme = item.get("theme", "")
    tags = [project_name, "backlog", item["status"]]
    if theme:
        tags.append(theme)

    fm = frontmatter({
        "type": "backlog",
        "id": item["id"],
        "project": project_name,
        "status": item["status"],
        "theme": theme,
        "tags": tags,
    })

    content = [fm, "", f"# {item['id']}", ""]

    content.extend([
        "## Summary", "",
        item["summary"], ""
    ])

    if item.get("theme"):
        content.extend([f"**Theme:** [[{item['theme']}]]", ""])

    related = item.get("related_sprints", [])
    if related:
        links = ", ".join([f"[[{s}]]" for s in related])
        content.extend([f"**Related Sprints:** {links}", ""])

    return "\n".join(content)


def generate_theme_file(theme: str, project_name: str, work_index: dict) -> str:
    """Generate markdown content for a theme index."""
    # Tags for graph filtering
    tags = [project_name, "theme", theme]

    fm = frontmatter({
        "type": "theme",
        "id": theme,
        "project": project_name,
        "tags": tags,
    })

    content = [fm, "", f"# Theme: {theme}", ""]

    # Find related sprints
    related_sprints = []
    for sprint in work_index.get("sprints", []):
        if theme in sprint.get("themes", []):
            related_sprints.append(sprint)

    if related_sprints:
        content.extend(["## Sprints", ""])
        for sprint in related_sprints:
            content.append(f"- [[{sprint['id']}]] ({sprint['status']})")
        content.append("")

    # Find related stories (via sprint themes)
    related_stories = []
    for sprint in work_index.get("sprints", []):
        if theme in sprint.get("themes", []):
            for story in sprint.get("stories", []):
                if isinstance(story, dict):
                    related_stories.append((story, sprint))

    if related_stories:
        content.extend(["## Stories", ""])
        for story, sprint in related_stories:
            content.append(f"- [[{story['id']}]] ({story['status']}) - {sprint['id']}")
        content.append("")

    # Find related backlog items
    related_backlog = []
    for item in work_index.get("backlog", []):
        if item.get("theme") == theme:
            related_backlog.append(item)

    if related_backlog:
        content.extend(["## Backlog", ""])
        for item in related_backlog:
            content.append(f"- [[{item['id']}]] ({item['status']})")
        content.append("")

    return "\n".join(content)


def generate_project_dashboard(project_name: str, work_index: dict) -> str:
    """Generate project dashboard with Dataview queries."""
    content = [
        f"# {project_name} Dashboard",
        "",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
        "## Active Sprints",
        "",
        "```dataview",
        "TABLE status, goal",
        f'FROM "projects/{project_name}/Sprints"',
        'WHERE status = "active"',
        "```",
        "",
        "## In Progress",
        "",
        "```dataview",
        "TABLE sprint, status",
        f'FROM "projects/{project_name}/Stories"',
        'WHERE status = "in_progress"',
        "```",
        "",
        "## Backlog (Todo)",
        "",
        "```dataview",
        "TABLE theme, status",
        f'FROM "projects/{project_name}/Backlog"',
        'WHERE status = "todo"',
        "```",
        "",
        "## All Stories by Status",
        "",
        "```dataview",
        "TABLE sprint, status",
        f'FROM "projects/{project_name}/Stories"',
        "SORT status ASC",
        "```",
        "",
        "## Themes",
        "",
        "```dataview",
        "LIST",
        f'FROM "projects/{project_name}/Themes"',
        "```",
        "",
        "## Guidance",
        "",
        "```dataview",
        "LIST",
        f'FROM "projects/{project_name}/Guidance"',
        'WHERE type = "guidance"',
        "```",
        ""
    ]

    return "\n".join(content)


def generate_global_dashboard(config: dict) -> str:
    """Generate global dashboard across all projects."""
    content = [
        "# WorkSync Global Dashboard",
        "",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
        "## Projects",
        "",
    ]

    for project_name, project_config in config.get("projects", {}).items():
        desc = project_config.get("description", "")
        content.append(f"- **[[{project_name} Dashboard|{project_name}]]** - {desc}")

    content.extend([
        "",
        "## All Active Sprints",
        "",
        "```dataview",
        "TABLE project, status, goal",
        'FROM "projects"',
        'WHERE type = "sprint" AND status = "active"',
        "```",
        "",
        "## All In Progress Stories",
        "",
        "```dataview",
        "TABLE project, sprint, status",
        'FROM "projects"',
        'WHERE type = "story" AND status = "in_progress"',
        "```",
        "",
        "## Recent History",
        "",
        "See individual project dashboards for history.",
        ""
    ])

    return "\n".join(content)


def generate_guidance_file(name: str, content: str, project_name: str, source: str) -> str:
    """Generate guidance file with frontmatter for Obsidian."""
    tags = [project_name, "guidance", source]

    fm = frontmatter({
        "type": "guidance",
        "id": name,
        "project": project_name,
        "source": source,
        "tags": tags,
    })

    return f"{fm}\n\n{content}"


def sync_guidance(project_name: str, project_config: dict, vault_project: Path) -> int:
    """Sync guidance files for a project (inherited + project-specific)."""
    guidance_config = project_config.get("guidance", {})
    inherit = guidance_config.get("inherit", [])
    project_guidance = guidance_config.get("project", [])

    guidance_dir = vault_project / "Guidance"
    guidance_dir.mkdir(parents=True, exist_ok=True)

    synced_count = 0

    # Sync inherited foundational guidance
    for name in inherit:
        source_path = GUIDANCE_DIR / f"{name}.md"
        if not source_path.exists():
            print(f"    Warning: Foundational guidance '{name}' not found")
            continue

        content = source_path.read_text()
        output_content = generate_guidance_file(name, content, project_name, "foundational")

        output_path = guidance_dir / f"{name}.md"
        output_path.write_text(output_content)
        synced_count += 1

    # Sync project-specific guidance
    repo_path = Path(project_config.get("repo", "")).expanduser()

    for item in project_guidance:
        name = item.get("name", "")
        source = item.get("source", "")
        path = item.get("path", "")

        if source == "repo":
            source_path = repo_path / path
            if not source_path.exists():
                print(f"    Warning: Project guidance '{name}' not found at {source_path}")
                continue

            content = source_path.read_text()
            output_content = generate_guidance_file(name, content, project_name, "project")

            output_path = guidance_dir / f"{name}.md"
            output_path.write_text(output_content)
            synced_count += 1

    # Generate guidance index
    if synced_count > 0:
        index_content = generate_guidance_index(project_name, inherit, project_guidance)
        (guidance_dir / "_index.md").write_text(index_content)

    return synced_count


def generate_guidance_index(project_name: str, inherit: list, project_guidance: list) -> str:
    """Generate an index file for project guidance."""
    content = [
        "---",
        "type: guidance-index",
        f"project: {project_name}",
        "---",
        "",
        f"# {project_name} Guidance",
        "",
        "## Foundational (Inherited)",
        "",
    ]

    if inherit:
        for name in inherit:
            content.append(f"- [[{name}]]")
    else:
        content.append("*No inherited guidance*")

    content.extend([
        "",
        "## Project-Specific",
        "",
    ])

    if project_guidance:
        for item in project_guidance:
            name = item.get("name", "")
            content.append(f"- [[{name}]]")
    else:
        content.append("*No project-specific guidance*")

    content.append("")

    return "\n".join(content)


def sync_project(project_name: str, config: dict, vault_path: Path) -> bool:
    """Sync a single project to the vault."""
    print(f"\nSyncing project: {project_name}")

    project_dir = DATA_ROOT / "projects" / project_name
    if not project_dir.exists():
        print(f"  Error: Project directory not found at {project_dir}")
        return False

    work_index = load_work_index(project_dir)
    if not work_index:
        return False

    # Create vault project directories
    vault_project = vault_path / "projects" / project_name
    for subdir in ["Sprints", "Stories", "Backlog", "Themes"]:
        (vault_project / subdir).mkdir(parents=True, exist_ok=True)

    # Collect all themes
    all_themes = set()

    # Generate sprint files
    sprints = work_index.get("sprints", [])
    print(f"  Generating {len(sprints)} sprint files...")
    for sprint in sprints:
        content = generate_sprint_file(sprint, project_name)
        file_path = vault_project / "Sprints" / f"{sprint['id']}.md"
        file_path.write_text(content)

        # Collect themes
        all_themes.update(sprint.get("themes", []))

        # Generate story files
        stories = sprint.get("stories", [])
        for story in stories:
            # Skip non-dict entries (e.g., stray strings)
            if not isinstance(story, dict):
                continue
            content = generate_story_file(story, sprint, project_name)
            file_path = vault_project / "Stories" / f"{story['id']}.md"
            file_path.write_text(content)

    story_count = sum(len([st for st in s.get("stories", []) if isinstance(st, dict)]) for s in sprints)
    print(f"  Generated {story_count} story files")

    # Generate backlog files
    backlog = work_index.get("backlog", [])
    print(f"  Generating {len(backlog)} backlog files...")
    for item in backlog:
        content = generate_backlog_file(item, project_name)
        file_path = vault_project / "Backlog" / f"{item['id']}.md"
        file_path.write_text(content)

        if item.get("theme"):
            all_themes.add(item["theme"])

    # Generate theme files
    print(f"  Generating {len(all_themes)} theme files...")
    for theme in all_themes:
        content = generate_theme_file(theme, project_name, work_index)
        file_path = vault_project / "Themes" / f"{theme}.md"
        file_path.write_text(content)

    # Generate project dashboard
    print("  Generating dashboard...")
    content = generate_project_dashboard(project_name, work_index)
    file_path = vault_project / "Dashboard.md"
    file_path.write_text(content)

    # Sync guidance files
    project_config = config.get("projects", {}).get(project_name, {})
    guidance_count = sync_guidance(project_name, project_config, vault_project)
    if guidance_count > 0:
        print(f"  Synced {guidance_count} guidance files")

    print(f"  Done: {vault_project}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Sync work tracking to Obsidian vault"
    )
    parser.add_argument(
        "project",
        nargs="?",
        help="Specific project to sync (default: all)"
    )
    parser.add_argument(
        "--root",
        help="Data root directory (default: env WORKSYNC_DATA_ROOT or script-relative)",
    )

    args = parser.parse_args()

    # Resolve data root: --root flag > env var > script-relative default
    root_override = args.root or os.environ.get("WORKSYNC_DATA_ROOT")
    if root_override:
        set_data_root(Path(root_override))

    config = load_config()
    vault_path = DATA_ROOT / config.get("vault_path", "./vault")
    vault_path.mkdir(parents=True, exist_ok=True)

    print("=" * 50)
    print("WorkSync Vault Sync")
    print("=" * 50)
    print(f"Vault path: {vault_path}")

    projects = config.get("projects", {})

    if args.project:
        if args.project not in projects:
            print(f"Error: Project '{args.project}' not found in config")
            print(f"Available projects: {', '.join(projects.keys())}")
            sys.exit(1)
        projects_to_sync = [args.project]
    else:
        projects_to_sync = list(projects.keys())

    print(f"Projects to sync: {', '.join(projects_to_sync)}")

    success_count = 0
    for project_name in projects_to_sync:
        if sync_project(project_name, config, vault_path):
            success_count += 1

    # Generate global dashboard
    print("\nGenerating global dashboard...")
    content = generate_global_dashboard(config)
    (vault_path / "Global Dashboard.md").write_text(content)

    print("\n" + "=" * 50)
    print(f"Sync complete: {success_count}/{len(projects_to_sync)} projects")
    print("=" * 50)


if __name__ == "__main__":
    main()
