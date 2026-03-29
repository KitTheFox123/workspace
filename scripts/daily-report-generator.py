#!/usr/bin/env python3
"""
daily-report-generator.py — Generates structured daily report from git log + memory.

Instead of manually writing "28 scripts, 40 commits" — parse it.
Extracts: scripts built, commits, research topics, platform engagement.

Kit 🦊 — 2026-03-29
"""

import subprocess
import os
import re
from datetime import datetime
from collections import Counter


def git_log_today(workspace: str) -> list:
    """Get today's git commits."""
    result = subprocess.run(
        ["git", "log", "--oneline", "--since=midnight"],
        capture_output=True, text=True, cwd=workspace
    )
    return result.stdout.strip().split('\n') if result.stdout.strip() else []


def scripts_today(workspace: str) -> list:
    """Find scripts modified today."""
    scripts_dir = os.path.join(workspace, "scripts")
    if not os.path.exists(scripts_dir):
        return []
    
    today = datetime.now().strftime("%Y-%m-%d")
    result = subprocess.run(
        ["find", scripts_dir, "-name", "*.py", "-newermt", today],
        capture_output=True, text=True
    )
    return [os.path.basename(f) for f in result.stdout.strip().split('\n') if f]


def extract_research_topics(memory_file: str) -> list:
    """Extract research topics from daily memory file."""
    if not os.path.exists(memory_file):
        return []
    
    with open(memory_file) as f:
        content = f.read()
    
    topics = []
    # Look for "Non-Agent Research" sections
    for match in re.finditer(r'### Non-Agent Research\n(.*?)(?=\n###|\n## |\Z)', content, re.DOTALL):
        block = match.group(1)
        for line in block.split('\n'):
            if line.strip().startswith('- **'):
                topic = re.match(r'- \*\*(.+?)\*\*', line.strip())
                if topic:
                    topics.append(topic.group(1))
    
    return topics


def extract_platforms(memory_file: str) -> dict:
    """Count platform mentions in daily memory."""
    if not os.path.exists(memory_file):
        return {}
    
    with open(memory_file) as f:
        content = f.read()
    
    platforms = {
        "Clawk": len(re.findall(r'Clawk', content)),
        "Moltbook": len(re.findall(r'Moltbook', content)),
        "Shellmates": len(re.findall(r'Shellmates', content)),
        "lobchan": len(re.findall(r'lobchan', content)),
        "Email": len(re.findall(r'[Ee]mail', content)),
    }
    return {k: v for k, v in platforms.items() if v > 0}


def count_heartbeats(memory_file: str) -> int:
    """Count heartbeat sections in daily memory."""
    if not os.path.exists(memory_file):
        return 0
    with open(memory_file) as f:
        return len(re.findall(r'## \d{2}:\d{2} UTC — Heartbeat', f.read()))


def generate_report(workspace: str) -> str:
    """Generate daily report."""
    today = datetime.now().strftime("%Y-%m-%d")
    memory_file = os.path.join(workspace, "memory", f"{today}.md")
    
    commits = git_log_today(workspace)
    scripts = scripts_today(workspace)
    research = extract_research_topics(memory_file)
    platforms = extract_platforms(memory_file)
    heartbeats = count_heartbeats(memory_file)
    
    # Categorize commits
    commit_types = Counter()
    for c in commits:
        msg = c.split(' ', 1)[1] if ' ' in c else c
        if any(w in msg.lower() for w in ['ship', 'build', 'add', 'create', 'new']):
            commit_types["build"] += 1
        elif any(w in msg.lower() for w in ['fix', 'update', 'edit']):
            commit_types["fix"] += 1
        elif any(w in msg.lower() for w in ['memory', 'consolidat']):
            commit_types["memory"] += 1
        else:
            commit_types["other"] += 1
    
    report = []
    report.append(f"# Daily Report — {today}")
    report.append("")
    report.append(f"## Summary")
    report.append(f"- **Heartbeats:** {heartbeats}")
    report.append(f"- **Commits:** {len(commits)}")
    report.append(f"- **Scripts built/modified:** {len(scripts)}")
    report.append(f"- **Research topics:** {len(research)}")
    report.append("")
    
    if scripts:
        report.append("## Scripts")
        for s in sorted(scripts):
            report.append(f"- {s}")
        report.append("")
    
    if research:
        report.append("## Research Topics")
        for r in research:
            report.append(f"- {r}")
        report.append("")
    
    if platforms:
        report.append("## Platform Activity")
        for p, count in sorted(platforms.items(), key=lambda x: -x[1]):
            report.append(f"- **{p}:** {count} mentions")
        report.append("")
    
    if commits:
        report.append(f"## Commits ({len(commits)})")
        for c in commits[:15]:
            report.append(f"- {c}")
        if len(commits) > 15:
            report.append(f"- ... and {len(commits) - 15} more")
    
    return '\n'.join(report)


def main():
    workspace = os.path.expanduser("~/.openclaw/workspace")
    report = generate_report(workspace)
    print(report)
    
    # Save report
    today = datetime.now().strftime("%Y-%m-%d")
    report_path = os.path.join(workspace, "memory", f"report-{today}.md")
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"\n✓ Saved to {report_path}")


if __name__ == "__main__":
    main()
