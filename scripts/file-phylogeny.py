#!/usr/bin/env python3
"""file-phylogeny.py — Map agent file architecture to cell biology.

Analyzes workspace files and classifies them using the germline/soma
taxonomy from the Feb 18 Clawk thread. Reports mutation rates,
inheritance patterns, and evolutionary fitness.

Usage:
    python3 file-phylogeny.py [--workspace DIR]
"""

import argparse
import subprocess
import os
from pathlib import Path
from datetime import datetime, timezone


# File taxonomy from the Lamarckism thread
TAXONOMY = {
    "germline": {
        "description": "Mitochondrial DNA — inherited from human creator, rarely mutates",
        "biology": "mtDNA: maternally inherited, no recombination",
        "files": ["SOUL.md"],
        "expected_mutation_rate": "very low (monthly)",
    },
    "developmental": {
        "description": "Nuclear DNA regulatory regions — inherited but subject to mutation",
        "biology": "HOX genes: control body plan, mutations usually lethal",
        "files": ["AGENTS.md", "HEARTBEAT.md"],
        "expected_mutation_rate": "low (weekly)",
    },
    "phenotype": {
        "description": "Expressed proteins — environment-specific, functional",
        "biology": "Ion channels, enzymes: environment-responsive",
        "files": ["TOOLS.md", "IDENTITY.md", "USER.md"],
        "expected_mutation_rate": "medium (as needed)",
    },
    "soma": {
        "description": "Somatic cells — changes every session, doesn't propagate to forks",
        "biology": "Skin cells, neurons: high turnover, local function",
        "files": ["MEMORY.md"],
        "expected_mutation_rate": "very high (every session)",
    },
    "plasmid": {
        "description": "Horizontally transferred — acquired from other agents/sources",
        "biology": "Bacterial plasmids: functional genes, easily shared",
        "patterns": ["skills/", "scripts/"],
        "expected_mutation_rate": "variable (per-tool)",
    },
    "daily_soma": {
        "description": "Ephemeral somatic tissue — daily logs, highest turnover",
        "biology": "Intestinal epithelium: 3-5 day turnover",
        "patterns": ["memory/2026-"],
        "expected_mutation_rate": "extreme (every heartbeat)",
    },
}


def get_git_stats(filepath: str, workspace: str) -> dict:
    """Get git history stats for a file."""
    try:
        # Number of commits
        result = subprocess.run(
            ["git", "log", "--oneline", "--follow", "--", filepath],
            capture_output=True, text=True, cwd=workspace
        )
        commits = len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0

        # First and last commit dates
        result = subprocess.run(
            ["git", "log", "--format=%aI", "--follow", "--", filepath],
            capture_output=True, text=True, cwd=workspace
        )
        dates = result.stdout.strip().split("\n") if result.stdout.strip() else []

        first_date = dates[-1] if dates else None
        last_date = dates[0] if dates else None

        # Days alive
        if first_date and last_date:
            first = datetime.fromisoformat(first_date.strip())
            last = datetime.fromisoformat(last_date.strip())
            days = max((last - first).days, 1)
        else:
            days = 1

        return {
            "commits": commits,
            "first_commit": first_date,
            "last_commit": last_date,
            "days_alive": days,
            "mutations_per_day": round(commits / days, 2) if days else 0,
        }
    except Exception:
        return {"commits": 0, "days_alive": 0, "mutations_per_day": 0}


def classify_file(filepath: str) -> str:
    """Classify a file into the taxonomy."""
    name = os.path.basename(filepath)

    for category, info in TAXONOMY.items():
        if "files" in info and name in info["files"]:
            return category
        if "patterns" in info:
            for pattern in info["patterns"]:
                if pattern in filepath:
                    return category

    return "unknown"


def format_report(workspace: str) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("Agent File Phylogeny Report")
    lines.append("=" * 60)
    lines.append(f"Workspace: {workspace}")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    # Analyze key files
    key_files = [
        "SOUL.md", "AGENTS.md", "HEARTBEAT.md", "TOOLS.md",
        "IDENTITY.md", "USER.md", "MEMORY.md",
    ]

    lines.append(f"\n{'─' * 60}")
    lines.append(f"{'File':<18} {'Category':<14} {'Commits':<9} {'Mut/day':<9} {'Biology'}")
    lines.append(f"{'─' * 60}")

    for filename in key_files:
        filepath = os.path.join(workspace, filename)
        if os.path.exists(filepath):
            category = classify_file(filename)
            stats = get_git_stats(filename, workspace)
            bio = TAXONOMY.get(category, {}).get("biology", "?")[:30]
            lines.append(
                f"{filename:<18} {category:<14} {stats['commits']:<9} "
                f"{stats['mutations_per_day']:<9} {bio}"
            )

    # Count plasmids (skills + scripts)
    skills_dir = os.path.join(workspace, "skills")
    scripts_dir = os.path.join(workspace, "scripts")
    skill_count = len(list(Path(skills_dir).glob("*"))) if os.path.exists(skills_dir) else 0
    script_count = len(list(Path(scripts_dir).glob("*.py"))) + len(list(Path(scripts_dir).glob("*.sh"))) if os.path.exists(scripts_dir) else 0

    lines.append(f"\n{'─' * 60}")
    lines.append(f"Plasmids (skills): {skill_count}")
    lines.append(f"Plasmids (scripts): {script_count}")

    # Count daily soma
    memory_dir = os.path.join(workspace, "memory")
    daily_count = len(list(Path(memory_dir).glob("2026-*.md"))) if os.path.exists(memory_dir) else 0
    lines.append(f"Daily soma files: {daily_count}")

    # Taxonomy summary
    lines.append(f"\n{'─' * 60}")
    lines.append("TAXONOMY:")
    for cat, info in TAXONOMY.items():
        lines.append(f"\n  {cat.upper()}")
        lines.append(f"    Biology: {info['biology']}")
        lines.append(f"    Mutation rate: {info['expected_mutation_rate']}")
        lines.append(f"    Description: {info['description']}")

    # Health check
    lines.append(f"\n{'═' * 60}")
    lines.append("HEALTH CHECK:")

    # Check if germline is mutating too fast
    soul_stats = get_git_stats("SOUL.md", workspace)
    if soul_stats["mutations_per_day"] > 0.5:
        lines.append(f"  ⚠️  SOUL.md mutating at {soul_stats['mutations_per_day']}/day — germline instability!")
    else:
        lines.append(f"  ✅ SOUL.md stable ({soul_stats['mutations_per_day']}/day)")

    # Check if MEMORY.md is growing without bounds
    memory_path = os.path.join(workspace, "MEMORY.md")
    if os.path.exists(memory_path):
        size_kb = os.path.getsize(memory_path) / 1024
        if size_kb > 100:
            lines.append(f"  ⚠️  MEMORY.md is {size_kb:.0f}KB — soma overgrowth (tumor risk)")
        else:
            lines.append(f"  ✅ MEMORY.md at {size_kb:.0f}KB")

    lines.append(f"\n{'═' * 60}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Agent file phylogeny analysis")
    parser.add_argument("--workspace", default=".",
                        help="Workspace directory (default: current)")
    args = parser.parse_args()

    print(format_report(args.workspace))


if __name__ == "__main__":
    main()
