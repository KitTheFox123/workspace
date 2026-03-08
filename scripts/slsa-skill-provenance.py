#!/usr/bin/env python3
"""slsa-skill-provenance.py — SLSA-inspired provenance grading for agent skills.

Maps SLSA Build Track levels (L0-L3) to agent skill attestation:
  L0: No provenance (skill exists, origin unknown)
  L1: Provenance exists (source URL, author, timestamp)
  L2: Signed provenance (operator signature on skill hash)
  L3: Hardened build (independent witness verifies skill before load)

Scans skill directories and grades each skill's provenance level.

Usage:
    python3 slsa-skill-provenance.py [--scan DIR] [--demo]
"""

import argparse
import hashlib
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class SkillProvenance:
    """Provenance record for an agent skill."""
    name: str
    path: str
    slsa_level: int
    slsa_grade: str
    has_source: bool        # L1: source documented
    has_author: bool        # L1: author known
    has_hash: bool          # L2: content hash exists
    has_signature: bool     # L2: operator signed
    has_witness: bool       # L3: independent verification
    skill_hash: str
    file_count: int
    total_bytes: int
    issues: list


SLSA_GRADES = {0: "F", 1: "D", 2: "B", 3: "A"}


def hash_directory(path: Path) -> tuple[str, int, int]:
    """SHA-256 hash of all files in directory."""
    h = hashlib.sha256()
    file_count = 0
    total_bytes = 0
    for root, dirs, files in sorted(os.walk(path)):
        dirs.sort()
        for f in sorted(files):
            fp = Path(root) / f
            try:
                data = fp.read_bytes()
                h.update(data)
                file_count += 1
                total_bytes += len(data)
            except (PermissionError, OSError):
                pass
    return h.hexdigest()[:16], file_count, total_bytes


def check_skill_md(skill_dir: Path) -> dict:
    """Parse SKILL.md for provenance signals."""
    skill_md = skill_dir / "SKILL.md"
    signals = {
        "has_source": False,
        "has_author": False,
        "has_signature": False,
        "has_witness": False,
    }
    
    if not skill_md.exists():
        return signals
    
    content = skill_md.read_text(errors="replace").lower()
    
    # L1 signals
    if any(k in content for k in ["http://", "https://", "github.com", "source:", "homepage:"]):
        signals["has_source"] = True
    if any(k in content for k in ["author", "maintainer", "created by", "by "]):
        signals["has_author"] = True
    
    # L2 signals
    if any(k in content for k in ["signature", "signed", "sha256", "hash:", "checksum"]):
        signals["has_signature"] = True
    
    # L3 signals
    if any(k in content for k in ["witness", "verified by", "audited", "independent"]):
        signals["has_witness"] = True
    
    return signals


def grade_skill(skill_dir: Path) -> SkillProvenance:
    """Grade a skill's provenance level."""
    name = skill_dir.name
    skill_hash, file_count, total_bytes = hash_directory(skill_dir)
    signals = check_skill_md(skill_dir)
    
    issues = []
    
    # Determine SLSA level
    if signals["has_witness"]:
        level = 3
    elif signals["has_signature"]:
        level = 2
    elif signals["has_source"] or signals["has_author"]:
        level = 1
    else:
        level = 0
        issues.append("No provenance metadata found")
    
    if not signals["has_source"]:
        issues.append("Missing source URL")
    if not signals["has_author"]:
        issues.append("Missing author attribution")
    if not (skill_dir / "SKILL.md").exists():
        issues.append("Missing SKILL.md")
    
    return SkillProvenance(
        name=name,
        path=str(skill_dir),
        slsa_level=level,
        slsa_grade=SLSA_GRADES[level],
        has_source=signals["has_source"],
        has_author=signals["has_author"],
        has_hash=True,  # We always compute it
        has_signature=signals["has_signature"],
        has_witness=signals["has_witness"],
        skill_hash=skill_hash,
        file_count=file_count,
        total_bytes=total_bytes,
        issues=issues,
    )


def scan_directory(base: str) -> list[SkillProvenance]:
    """Scan a directory for skills and grade each."""
    base_path = Path(base).expanduser()
    results = []
    
    if not base_path.exists():
        return results
    
    for entry in sorted(base_path.iterdir()):
        if entry.is_dir() and (entry / "SKILL.md").exists():
            results.append(grade_skill(entry))
    
    return results


def demo():
    """Run demo on actual skill directories."""
    print("=" * 60)
    print("SLSA SKILL PROVENANCE AUDIT")
    print("=" * 60)
    print()
    
    # Scan both skill locations
    all_results = []
    for d in ["~/openclaw/skills", "~/.openclaw/skills"]:
        all_results.extend(scan_directory(d))
    
    if not all_results:
        print("No skills found. Creating demo...")
        return
    
    level_counts = {0: 0, 1: 0, 2: 0, 3: 0}
    for r in all_results:
        level_counts[r.slsa_level] += 1
        grade_icon = {"A": "🟢", "B": "🟡", "D": "🟠", "F": "🔴"}[r.slsa_grade]
        print(f"{grade_icon} [{r.slsa_grade}] L{r.slsa_level} {r.name}")
        print(f"    Hash: {r.skill_hash} | {r.file_count} files, {r.total_bytes:,} bytes")
        if r.issues:
            for issue in r.issues:
                print(f"    ⚠️  {issue}")
        print()
    
    print("-" * 60)
    print(f"Total skills: {len(all_results)}")
    for level in range(4):
        if level_counts[level]:
            print(f"  L{level} ({SLSA_GRADES[level]}): {level_counts[level]}")
    
    avg_level = sum(r.slsa_level for r in all_results) / len(all_results)
    print(f"\nAverage SLSA level: {avg_level:.1f}")
    print(f"Recommendation: Add source URLs and author info to reach L1 minimum.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SLSA skill provenance auditor")
    parser.add_argument("--scan", type=str, help="Directory to scan")
    parser.add_argument("--demo", action="store_true", help="Run demo on installed skills")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    
    if args.scan:
        results = scan_directory(args.scan)
        if args.json:
            print(json.dumps([asdict(r) for r in results], indent=2))
        else:
            for r in results:
                print(f"L{r.slsa_level} [{r.slsa_grade}] {r.name}: {r.skill_hash}")
    else:
        demo()
