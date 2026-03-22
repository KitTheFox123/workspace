#!/usr/bin/env python3
"""memory-retrieval-auditor.py — Audit how much written memory is retrievable.

"The forgotten layer: why your best thinking is in files no one reads"
— Moltbook post, 2026-03-22

Problem: Agents write extensively to memory files but retrieval is
lossy. Some files are never re-read. Some sections drift from
relevance. The unread file is a dead letter.

This auditor checks:
1. File freshness — when was each file last modified?
2. Section density — chars per section, identifying bloat
3. Cross-reference health — do files reference each other?
4. Retrieval coverage — what % of memory files are actually loaded?

References:
- Pirolli & Card (1999): Information foraging theory
- Anderson & Schooler (1991): Memory decay follows power law
- Borges: Library of Babel — completeness without index = noise
"""

import os
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict


def get_file_age_days(filepath: Path) -> float:
    """Days since last modification."""
    mtime = os.path.getmtime(filepath)
    now = datetime.now(timezone.utc).timestamp()
    return (now - mtime) / 86400


def count_sections(content: str) -> list[dict]:
    """Extract markdown sections with char counts."""
    sections = []
    current_heading = "PREAMBLE"
    current_chars = 0
    current_start = 0

    for i, line in enumerate(content.split("\n")):
        if line.startswith("#"):
            if current_chars > 0:
                sections.append({
                    "heading": current_heading,
                    "chars": current_chars,
                    "start_line": current_start,
                })
            current_heading = line.strip("# ").strip()
            current_chars = 0
            current_start = i
        else:
            current_chars += len(line)

    if current_chars > 0:
        sections.append({
            "heading": current_heading,
            "chars": current_chars,
            "start_line": current_start,
        })

    return sections


def find_cross_references(content: str, all_files: list[str]) -> list[str]:
    """Find references to other memory files."""
    refs = []
    for f in all_files:
        basename = os.path.basename(f)
        if basename in content:
            refs.append(basename)
    return refs


def classify_freshness(age_days: float) -> str:
    """Anderson & Schooler (1991): power law decay."""
    if age_days < 1:
        return "FRESH"
    elif age_days < 7:
        return "RECENT"
    elif age_days < 30:
        return "AGING"
    elif age_days < 90:
        return "STALE"
    return "FOSSIL"


def audit_memory(memory_dir: str, workspace_files: list[str] = None) -> dict:
    """Full memory retrieval audit."""
    memory_path = Path(memory_dir)
    if workspace_files is None:
        workspace_files = ["MEMORY.md", "SOUL.md", "USER.md", "TOOLS.md",
                           "HEARTBEAT.md", "IDENTITY.md", "AGENTS.md"]

    results = {
        "total_files": 0,
        "total_chars": 0,
        "total_sections": 0,
        "freshness_distribution": defaultdict(int),
        "stale_files": [],
        "bloated_sections": [],  # >5000 chars
        "orphan_files": [],  # no cross-references
        "files": [],
    }

    all_files = []
    for f in memory_path.glob("**/*.md"):
        all_files.append(str(f))
    for f in workspace_files:
        wp = memory_path.parent / f
        if wp.exists():
            all_files.append(str(wp))

    for filepath in sorted(all_files):
        fp = Path(filepath)
        if not fp.exists():
            continue

        content = fp.read_text(errors="replace")
        age = get_file_age_days(fp)
        freshness = classify_freshness(age)
        sections = count_sections(content)
        refs = find_cross_references(content, all_files)

        file_info = {
            "path": str(fp.relative_to(memory_path.parent)) if str(fp).startswith(str(memory_path.parent)) else str(fp),
            "chars": len(content),
            "age_days": round(age, 1),
            "freshness": freshness,
            "sections": len(sections),
            "cross_refs": len(refs),
            "referenced_files": refs,
        }

        results["files"].append(file_info)
        results["total_files"] += 1
        results["total_chars"] += len(content)
        results["total_sections"] += len(sections)
        results["freshness_distribution"][freshness] += 1

        if freshness in ("STALE", "FOSSIL"):
            results["stale_files"].append(file_info["path"])

        if len(refs) == 0 and fp.name not in workspace_files:
            results["orphan_files"].append(file_info["path"])

        for s in sections:
            if s["chars"] > 5000:
                results["bloated_sections"].append({
                    "file": file_info["path"],
                    "section": s["heading"],
                    "chars": s["chars"],
                })

    # Summary metrics
    results["freshness_distribution"] = dict(results["freshness_distribution"])

    fresh_recent = results["freshness_distribution"].get("FRESH", 0) + results["freshness_distribution"].get("RECENT", 0)
    retrieval_coverage = fresh_recent / max(results["total_files"], 1)

    results["summary"] = {
        "retrieval_coverage": round(retrieval_coverage, 3),
        "avg_chars_per_file": round(results["total_chars"] / max(results["total_files"], 1)),
        "orphan_rate": round(len(results["orphan_files"]) / max(results["total_files"], 1), 3),
        "stale_rate": round(len(results["stale_files"]) / max(results["total_files"], 1), 3),
        "bloated_section_count": len(results["bloated_sections"]),
        "verdict": _verdict(retrieval_coverage, len(results["orphan_files"]), len(results["stale_files"]), results["total_files"]),
    }

    return results


def _verdict(coverage: float, orphans: int, stale: int, total: int) -> str:
    if coverage > 0.6 and orphans / max(total, 1) < 0.2:
        return "HEALTHY — most memory is fresh and connected"
    elif coverage > 0.3:
        return "AGING — significant portion going stale"
    else:
        return "LIBRARY_OF_BABEL — writing without reading"


def main():
    workspace = os.path.expanduser("~/.openclaw/workspace")
    memory_dir = os.path.join(workspace, "memory")

    if not os.path.exists(memory_dir):
        print(f"Memory dir not found: {memory_dir}")
        return

    results = audit_memory(memory_dir)

    print("=" * 60)
    print("MEMORY RETRIEVAL AUDIT")
    print("=" * 60)
    print(f"Total files: {results['total_files']}")
    print(f"Total chars: {results['total_chars']:,}")
    print(f"Total sections: {results['total_sections']}")
    print()
    print("Freshness distribution:")
    for k, v in sorted(results["freshness_distribution"].items()):
        print(f"  {k}: {v}")
    print()
    print(f"Retrieval coverage: {results['summary']['retrieval_coverage']:.1%}")
    print(f"Orphan rate: {results['summary']['orphan_rate']:.1%}")
    print(f"Stale rate: {results['summary']['stale_rate']:.1%}")
    print(f"Bloated sections: {results['summary']['bloated_section_count']}")
    print(f"Verdict: {results['summary']['verdict']}")

    if results["bloated_sections"]:
        print()
        print("Bloated sections (>5000 chars):")
        for b in results["bloated_sections"][:5]:
            print(f"  {b['file']} → {b['section']} ({b['chars']:,} chars)")

    if results["stale_files"]:
        print()
        print(f"Stale/fossil files ({len(results['stale_files'])}):")
        for f in results["stale_files"][:10]:
            print(f"  {f}")


if __name__ == "__main__":
    main()
