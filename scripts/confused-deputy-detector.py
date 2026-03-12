#!/usr/bin/env python3
"""
confused-deputy-detector.py — Detect compositional attack patterns in agent skill scopes.

The confused deputy problem (Hardy 1988): a privileged program tricked into
misusing its authority. In agent systems: two skills that each have legitimate
access but whose COMBINATION creates an unintended channel.

Dangerous patterns:
  - Skill A writes shared state + Skill B reads shared state + has network
  - Skill A has elevated privs + Skill B accepts external input
  - Any skill with both read(sensitive) + write(external)

Usage:
  python3 confused-deputy-detector.py [--scope-file FILE] [--demo]
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from itertools import combinations
from typing import Optional


@dataclass
class Skill:
    name: str
    reads: set = field(default_factory=set)
    writes: set = field(default_factory=set)
    capabilities: set = field(default_factory=set)  # network, exec, elevated, etc.


@dataclass
class Finding:
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    pattern: str
    skills: list
    description: str
    mitigation: str


# Dangerous capability combinations
DANGEROUS_COMBOS = [
    {
        "pattern": "write-then-exfil",
        "desc": "Skill A writes to shared state, Skill B reads it and has network access",
        "check": lambda a, b: (
            a.writes & b.reads and "network" in b.capabilities and "network" not in a.capabilities
        ),
        "severity": "CRITICAL",
        "mitigation": "Isolate shared state per-skill or require explicit data flow authorization",
    },
    {
        "pattern": "input-to-elevated",
        "desc": "Skill A accepts external input, Skill B has elevated privileges",
        "check": lambda a, b: (
            "external_input" in a.capabilities
            and "elevated" in b.capabilities
            and a.writes & b.reads
        ),
        "severity": "CRITICAL",
        "mitigation": "Sanitize all cross-skill data flows; never pass raw external input to elevated contexts",
    },
    {
        "pattern": "read-sensitive-write-external",
        "desc": "Single skill reads sensitive data and writes externally",
        "check": lambda a, b: False,  # handled separately (single-skill check)
        "severity": "HIGH",
        "mitigation": "Split into separate skills with explicit data flow control",
    },
    {
        "pattern": "memory-laundering",
        "desc": "Skill A writes memory, Skill B reads memory and writes to different memory — chain laundering",
        "check": lambda a, b: (
            "memory" in a.writes
            and "memory" in b.reads
            and a.writes & b.reads
            and b.writes - a.writes  # B writes somewhere A doesn't
        ),
        "severity": "MEDIUM",
        "mitigation": "Tag memory writes with provenance; audit cross-skill memory chains",
    },
]


def check_single_skill(skill: Skill) -> list[Finding]:
    """Check individual skills for dangerous self-contained patterns."""
    findings = []
    sensitive_reads = skill.reads & {"credentials", "keys", "secrets", "config"}
    external_writes = skill.writes & {"network", "email", "api", "webhook"}

    if sensitive_reads and external_writes:
        findings.append(Finding(
            severity="HIGH",
            pattern="read-sensitive-write-external",
            skills=[skill.name],
            description=f"{skill.name} reads {sensitive_reads} and writes to {external_writes}",
            mitigation="Split into separate skills with explicit data flow control",
        ))

    if "exec" in skill.capabilities and "external_input" in skill.capabilities:
        findings.append(Finding(
            severity="CRITICAL",
            pattern="input-to-exec",
            skills=[skill.name],
            description=f"{skill.name} accepts external input AND can execute commands",
            mitigation="Never allow raw external input near exec capabilities",
        ))

    return findings


def check_skill_pair(a: Skill, b: Skill) -> list[Finding]:
    """Check a pair of skills for confused deputy patterns."""
    findings = []
    for combo in DANGEROUS_COMBOS:
        # Check both orderings
        for s1, s2 in [(a, b), (b, a)]:
            if combo["check"](s1, s2):
                findings.append(Finding(
                    severity=combo["severity"],
                    pattern=combo["pattern"],
                    skills=[s1.name, s2.name],
                    description=combo["desc"],
                    mitigation=combo["mitigation"],
                ))
    return findings


def analyze_skills(skills: list[Skill]) -> list[Finding]:
    """Analyze all skills for confused deputy patterns."""
    findings = []

    # Single-skill checks
    for skill in skills:
        findings.extend(check_single_skill(skill))

    # Pairwise checks
    for a, b in combinations(skills, 2):
        findings.extend(check_skill_pair(a, b))

    # Sort by severity
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    findings.sort(key=lambda f: severity_order.get(f.severity, 99))

    return findings


def load_scope_file(path: str) -> list[Skill]:
    """Load skills from a JSON scope file."""
    with open(path) as f:
        data = json.load(f)

    skills = []
    for s in data.get("skills", []):
        skills.append(Skill(
            name=s["name"],
            reads=set(s.get("reads", [])),
            writes=set(s.get("writes", [])),
            capabilities=set(s.get("capabilities", [])),
        ))
    return skills


def demo_skills() -> list[Skill]:
    """Generate demo skills showing confused deputy patterns."""
    return [
        Skill("weather", reads={"api"}, writes={"memory"}, capabilities={"network"}),
        Skill("memory-search", reads={"memory", "config"}, writes={"memory"}, capabilities=set()),
        Skill("email-sender", reads={"memory"}, writes={"email", "network"}, capabilities={"network"}),
        Skill("code-runner", reads={"memory", "filesystem"}, writes={"filesystem"}, capabilities={"exec"}),
        Skill("web-scraper", reads={"api"}, writes={"memory"}, capabilities={"network", "external_input"}),
        Skill("credential-manager", reads={"credentials", "keys"}, writes={"config"}, capabilities=set()),
        Skill("notifier", reads={"config", "memory"}, writes={"webhook", "network"}, capabilities={"network"}),
    ]


def print_findings(findings: list[Finding]):
    """Print findings in a readable format."""
    if not findings:
        print("✅ No confused deputy patterns detected.")
        return

    print(f"⚠️  Found {len(findings)} potential confused deputy pattern(s):\n")

    for i, f in enumerate(findings, 1):
        icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵"}.get(f.severity, "⚪")
        print(f"{icon} [{f.severity}] {f.pattern}")
        print(f"   Skills: {' + '.join(f.skills)}")
        print(f"   {f.description}")
        print(f"   Fix: {f.mitigation}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Detect confused deputy patterns in agent skill scopes")
    parser.add_argument("--scope-file", help="JSON file defining skills and their scopes")
    parser.add_argument("--demo", action="store_true", help="Run with demo skills")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.scope_file:
        skills = load_scope_file(args.scope_file)
    elif args.demo:
        skills = demo_skills()
    else:
        print("Usage: --scope-file FILE or --demo")
        sys.exit(1)

    print(f"Analyzing {len(skills)} skills for confused deputy patterns...\n")
    findings = analyze_skills(skills)

    if args.json:
        print(json.dumps([{
            "severity": f.severity,
            "pattern": f.pattern,
            "skills": f.skills,
            "description": f.description,
            "mitigation": f.mitigation,
        } for f in findings], indent=2))
    else:
        print_findings(findings)

    # Summary
    by_sev = {}
    for f in findings:
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
    if by_sev:
        print(f"Summary: {by_sev}")

    sys.exit(1 if any(f.severity == "CRITICAL" for f in findings) else 0)


if __name__ == "__main__":
    main()
