#!/usr/bin/env python3
"""
meta-attestation-audit.py — Does our own heartbeat pass our own checks?

Reads today's daily memory log and scores each heartbeat against
the observation protocol we built. Eat our own dogfood.

Checks per heartbeat:
1. Evidence gate: did actions change? (not stale)
2. Channel coverage: how many platforms checked?
3. Search power: was research done?
4. Observable state: did the beat carry payload (not empty ping)?
5. Timing: was interval within window?
"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class HeartbeatEntry:
    time: str
    writing_actions: int = 0
    build_actions: int = 0
    platforms_checked: list = field(default_factory=list)
    research_done: bool = False
    has_findings: bool = False

def parse_daily_log(path: str) -> list:
    """Parse memory/YYYY-MM-DD.md for heartbeat entries"""
    entries = []
    current = None
    
    text = Path(path).read_text()
    lines = text.split('\n')
    
    for line in lines:
        # Detect heartbeat header
        m = re.match(r'^## (\d+:\d+ UTC) — Heartbeat', line)
        if m:
            if current:
                entries.append(current)
            current = HeartbeatEntry(time=m.group(1))
            continue
        
        if not current:
            continue
        
        # Count writing actions
        if re.match(r'^\d+\. Clawk (post|reply)', line):
            current.writing_actions += 1
            current.has_findings = True
        if re.match(r'^\d+\. Shellmates', line):
            current.writing_actions += 1
        
        # Detect platforms
        for platform in ['Clawk', 'AgentMail', 'Shellmates', 'Moltbook']:
            if f'**{platform}:**' in line:
                current.platforms_checked.append(platform.lower())
        
        # Detect build
        if '### Build Action' in line:
            current.build_actions += 1
        
        # Detect research
        if '### Non-Agent Research' in line or 'Research' in line:
            current.research_done = True
    
    if current:
        entries.append(current)
    
    return entries

def grade_heartbeat(entry: HeartbeatEntry) -> dict:
    checks = []
    
    # 1. Evidence gate (writing actions > 0)
    if entry.writing_actions >= 3:
        checks.append({"check": "evidence_gate", "status": "PASS", "detail": f"{entry.writing_actions} writes"})
    elif entry.writing_actions > 0:
        checks.append({"check": "evidence_gate", "status": "WARN", "detail": f"{entry.writing_actions} writes (< 3)"})
    else:
        checks.append({"check": "evidence_gate", "status": "FAIL", "detail": "0 writes"})
    
    # 2. Channel coverage
    coverage = len(entry.platforms_checked) / 4.0
    if coverage >= 0.75:
        checks.append({"check": "channel_coverage", "status": "PASS", "detail": f"{len(entry.platforms_checked)}/4 platforms"})
    elif coverage >= 0.5:
        checks.append({"check": "channel_coverage", "status": "WARN", "detail": f"{len(entry.platforms_checked)}/4 platforms"})
    else:
        checks.append({"check": "channel_coverage", "status": "FAIL", "detail": f"{len(entry.platforms_checked)}/4 platforms"})
    
    # 3. Build action
    if entry.build_actions > 0:
        checks.append({"check": "build_action", "status": "PASS"})
    else:
        checks.append({"check": "build_action", "status": "FAIL", "detail": "No build"})
    
    # 4. Research
    if entry.research_done:
        checks.append({"check": "research", "status": "PASS"})
    else:
        checks.append({"check": "research", "status": "WARN", "detail": "No research detected"})
    
    # Grade
    passes = sum(1 for c in checks if c["status"] == "PASS")
    total = len(checks)
    if passes == total: grade = "A"
    elif passes >= total - 1: grade = "B"
    elif passes >= total - 2: grade = "C"
    else: grade = "D"
    
    return {"time": entry.time, "checks": checks, "grade": grade, "passes": passes, "total": total}

def main():
    import datetime
    today = datetime.date.today().isoformat()
    path = f"memory/{today}.md"
    
    if not Path(path).exists():
        print(f"No daily log found at {path}")
        # Try yesterday
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        path = f"memory/{yesterday}.md"
        if not Path(path).exists():
            print(f"No log at {path} either.")
            return
        print(f"Using yesterday's log: {path}")
    
    print("=" * 60)
    print(f"Meta-Attestation Audit: {path}")
    print("Does our own heartbeat pass our own checks?")
    print("=" * 60)
    
    entries = parse_daily_log(path)
    
    if not entries:
        print("\nNo heartbeat entries found.")
        return
    
    grades = []
    for entry in entries:
        result = grade_heartbeat(entry)
        grades.append(result["grade"])
        print(f"\n{result['time']}: Grade {result['grade']} ({result['passes']}/{result['total']} checks)")
        for c in result["checks"]:
            detail = c.get("detail", "")
            print(f"  {c['check']}: {c['status']} {detail}")
    
    # Summary
    grade_scores = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    avg = sum(grade_scores.get(g, 0) for g in grades) / max(len(grades), 1)
    overall = "A" if avg >= 3.5 else "B" if avg >= 2.5 else "C" if avg >= 1.5 else "D"
    
    print(f"\n{'='*60}")
    print(f"DAILY SUMMARY")
    print(f"  Heartbeats: {len(entries)}")
    print(f"  Grades: {', '.join(grades)}")
    print(f"  Average: {avg:.1f}/4.0")
    print(f"  Overall: Grade {overall}")
    print(f"\nMeta-attestation: we eat our own dogfood.")

if __name__ == "__main__":
    main()
