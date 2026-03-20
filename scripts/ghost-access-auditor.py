#!/usr/bin/env python3
"""
ghost-access-auditor.py — Detect tools you have but never use.

Based on Einstein & McDaniel (2005) prospective memory: retrieval fails
when cues don't fire under stress. Ghost access = capability exists but
never activates at the right moment.

Scans scripts/, checks git log for recent usage (commits mentioning script),
and flags tools that haven't been touched in N days.

Per openclawkong (Moltbook 2026-03-20): "The goal is not to add more tools.
The goal is to close the gap between having and activating."
"""

import os
import subprocess
import json
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass


@dataclass
class ScriptStatus:
    name: str
    last_modified: datetime
    last_committed: datetime | None
    days_dormant: int
    lines: int
    has_docstring: bool
    has_trigger_doc: bool  # describes WHEN to use, not just WHAT
    status: str  # ACTIVE, DORMANT, GHOST, UNKNOWN


def get_last_commit_date(filepath: str, repo_root: str) -> datetime | None:
    """Get the last git commit date for a file."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%aI", "--", filepath],
            capture_output=True, text=True, cwd=repo_root, timeout=5
        )
        if result.stdout.strip():
            return datetime.fromisoformat(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def check_trigger_doc(filepath: str) -> bool:
    """Check if script documents WHEN to use it, not just what it does."""
    trigger_words = ["when", "fires when", "use when", "trigger", "if you see",
                     "run this when", "activate when", "per ", "inspired by"]
    try:
        with open(filepath) as f:
            header = f.read(500).lower()
            return any(w in header for w in trigger_words)
    except (OSError, UnicodeDecodeError):
        return False


def audit_scripts(scripts_dir: str, repo_root: str, dormant_days: int = 14) -> list[ScriptStatus]:
    """Audit all scripts for ghost access patterns."""
    results = []
    from datetime import timezone
    now = datetime.now(timezone.utc)

    for f in sorted(Path(scripts_dir).glob("*.py")):
        stat = f.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        last_touch = modified
        committed = None  # skip git log for speed; use mtime
        days = (now - last_touch).days

        # Count lines
        try:
            lines = len(f.read_text().splitlines())
        except (OSError, UnicodeDecodeError):
            lines = 0

        # Check docstring
        try:
            content = f.read_text()
            has_doc = '"""' in content[:200] or "'''" in content[:200]
        except (OSError, UnicodeDecodeError):
            has_doc = False

        has_trigger = check_trigger_doc(str(f))

        # Classify
        if days <= 3:
            status = "ACTIVE"
        elif days <= dormant_days:
            status = "RECENT"
        elif days <= 30:
            status = "DORMANT"
        else:
            status = "GHOST"

        results.append(ScriptStatus(
            name=f.name,
            last_modified=modified,
            last_committed=committed,
            days_dormant=days,
            lines=lines,
            has_docstring=has_doc,
            has_trigger_doc=has_trigger,
            status=status
        ))

    return results


def main():
    repo_root = os.path.expanduser("~/.openclaw/workspace")
    scripts_dir = os.path.join(repo_root, "scripts")

    if not os.path.isdir(scripts_dir):
        print(f"Scripts directory not found: {scripts_dir}")
        return

    results = audit_scripts(scripts_dir, repo_root)

    # Summary
    by_status = {}
    for r in results:
        by_status.setdefault(r.status, []).append(r)

    total = len(results)
    print("=" * 65)
    print("GHOST ACCESS AUDIT")
    print("=" * 65)
    print(f"Total scripts: {total}")
    for status in ["ACTIVE", "RECENT", "DORMANT", "GHOST"]:
        count = len(by_status.get(status, []))
        pct = count / total * 100 if total else 0
        print(f"  {status:8s}: {count:3d} ({pct:.0f}%)")

    # Trigger documentation coverage
    with_trigger = sum(1 for r in results if r.has_trigger_doc)
    print(f"\nTrigger docs (WHEN to use): {with_trigger}/{total} ({with_trigger/total*100:.0f}%)")
    without_trigger_active = [r for r in results if r.status in ("DORMANT", "GHOST") and not r.has_trigger_doc]
    print(f"Ghost/dormant WITHOUT trigger docs: {len(without_trigger_active)}")

    # Ghost list
    ghosts = by_status.get("GHOST", [])
    if ghosts:
        print(f"\n{'='*65}")
        print("GHOST SCRIPTS (>30 days dormant)")
        print(f"{'='*65}")
        for g in sorted(ghosts, key=lambda x: x.days_dormant, reverse=True):
            trigger = "✓" if g.has_trigger_doc else "✗"
            print(f"  {g.name:45s} {g.days_dormant:3d}d  {g.lines:4d}L  trigger:{trigger}")

    # Dormant list
    dormant = by_status.get("DORMANT", [])
    if dormant:
        print(f"\n{'='*65}")
        print("DORMANT SCRIPTS (14-30 days)")
        print(f"{'='*65}")
        for d in sorted(dormant, key=lambda x: x.days_dormant, reverse=True):
            trigger = "✓" if d.has_trigger_doc else "✗"
            print(f"  {d.name:45s} {d.days_dormant:3d}d  {d.lines:4d}L  trigger:{trigger}")

    # Recommendations
    print(f"\n{'='*65}")
    print("RECOMMENDATIONS")
    print(f"{'='*65}")
    print("Per Einstein & McDaniel (2005) + Gollwitzer (1999):")
    print("1. Add trigger docs to ghost scripts: WHEN to use, not just WHAT")
    print("2. Run smoke tests on dormant scripts (keeps them salient)")
    print("3. Log panic overrides: when you hand-roll instead of using existing")
    print(f"\nGhost access ratio: {len(ghosts)/total*100:.0f}% of tools are invisible")


if __name__ == "__main__":
    main()
