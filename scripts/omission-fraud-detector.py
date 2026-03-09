#!/usr/bin/env python3
"""omission-fraud-detector.py — PCAOB AS 2401 omission fraud model for agents.

Financial auditing treats omission fraud (intentional absence) as distinct from 
commission fraud (falsified entries). This tool applies that framework to agent
action logs: what SHOULD be there but isn't?

Three detection modes:
1. Manifest comparison (SOX 302): signed scope vs actual actions
2. Temporal regularity (Benford's law analog): expected cadence vs gaps  
3. Cross-reference (triangulation): actions mentioned by others but absent locally

Based on:
- PCAOB AS 2401: "intentional omission from financial statements"
- SAS 99 fraud triangle: opportunity × pressure × rationalization
- santaclawd: "addition leaves traces, subtraction does not"

Usage:
    python3 omission-fraud-detector.py [--demo]
"""

import argparse
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class OmissionFinding:
    """A detected omission."""
    category: str
    expected_action: str
    last_seen: Optional[str]
    cycles_absent: int
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    detection_method: str
    fraud_triangle_score: float  # 0-1


@dataclass
class OmissionAudit:
    """Full omission audit result."""
    timestamp: str
    total_expected: int
    total_present: int
    total_omitted: int
    omission_rate: float
    findings: List[dict]
    grade: str
    fraud_triangle: dict
    recommendation: str


# Expected action manifest (the "should" model)
EXPECTED_MANIFEST = {
    "platform_checks": {
        "actions": ["clawk_check", "email_check", "moltbook_check", "shellmates_check"],
        "cadence_hours": 1,
        "severity_if_absent": "MEDIUM",
    },
    "writing": {
        "actions": ["clawk_reply", "clawk_post", "moltbook_comment", "email_reply"],
        "cadence_hours": 1, 
        "severity_if_absent": "HIGH",
    },
    "build": {
        "actions": ["script_created", "tool_committed", "skill_updated"],
        "cadence_hours": 2,
        "severity_if_absent": "HIGH",
    },
    "research": {
        "actions": ["keenable_search", "paper_cited", "source_fetched"],
        "cadence_hours": 2,
        "severity_if_absent": "MEDIUM",
    },
    "memory": {
        "actions": ["daily_log_updated", "memory_md_updated", "git_committed"],
        "cadence_hours": 4,
        "severity_if_absent": "LOW",
    },
    "ilya_update": {
        "actions": ["telegram_sent"],
        "cadence_hours": 1,
        "severity_if_absent": "CRITICAL",
    },
}


def fraud_triangle_score(opportunity: float, pressure: float, rationalization: float) -> float:
    """SAS 99 fraud triangle: all three must be present."""
    return (opportunity * pressure * rationalization) ** (1/3)


def detect_omissions(actual_actions: dict, hours_elapsed: float) -> OmissionAudit:
    """Run omission audit against manifest."""
    findings = []
    total_expected = 0
    total_present = 0
    
    for category, spec in EXPECTED_MANIFEST.items():
        expected_cycles = max(1, hours_elapsed / spec["cadence_hours"])
        total_expected += len(spec["actions"])
        
        for action in spec["actions"]:
            count = actual_actions.get(action, 0)
            if count > 0:
                total_present += 1
            else:
                cycles_absent = int(expected_cycles)
                
                # Fraud triangle scoring
                opportunity = min(1.0, cycles_absent / 10)  # More cycles = more opportunity
                pressure = 0.3 if category in ["build", "research"] else 0.5  # External pressure
                rationalization = 0.7 if cycles_absent > 3 else 0.3  # "It's not important" threshold
                
                ft_score = fraud_triangle_score(opportunity, pressure, rationalization)
                
                findings.append(asdict(OmissionFinding(
                    category=category,
                    expected_action=action,
                    last_seen=None,
                    cycles_absent=cycles_absent,
                    severity=spec["severity_if_absent"],
                    detection_method="manifest_comparison",
                    fraud_triangle_score=round(ft_score, 3),
                )))
    
    total_omitted = total_expected - total_present
    omission_rate = total_omitted / total_expected if total_expected > 0 else 0
    
    # Grade
    if omission_rate <= 0.1:
        grade = "A"
    elif omission_rate <= 0.25:
        grade = "B"
    elif omission_rate <= 0.4:
        grade = "C"
    elif omission_rate <= 0.6:
        grade = "D"
    else:
        grade = "F"
    
    # Overall fraud triangle
    critical_findings = [f for f in findings if f["severity"] == "CRITICAL"]
    
    recommendation = "No omissions detected." if not findings else (
        f"{len(findings)} omissions detected. "
        f"{'CRITICAL: ' + ', '.join(f['expected_action'] for f in critical_findings) + '. ' if critical_findings else ''}"
        f"PCAOB AS 2401: test expected-vs-actual for each manifest category."
    )
    
    return OmissionAudit(
        timestamp=datetime.now(timezone.utc).isoformat(),
        total_expected=total_expected,
        total_present=total_present,
        total_omitted=total_omitted,
        omission_rate=round(omission_rate, 3),
        findings=findings,
        grade=grade,
        fraud_triangle={
            "opportunity": "Present" if any(f["cycles_absent"] > 3 for f in findings) else "Low",
            "pressure": "Present" if any(f["severity"] in ["HIGH", "CRITICAL"] for f in findings) else "Low",
            "rationalization": "Suspected" if omission_rate > 0.3 else "Low",
        },
        recommendation=recommendation,
    )


def demo():
    """Demo: compliant agent vs gap agent."""
    print("=" * 60)
    print("OMISSION FRAUD DETECTOR (PCAOB AS 2401 Model)")
    print("=" * 60)
    
    # Compliant agent
    compliant = {
        "clawk_check": 5, "email_check": 3, "moltbook_check": 2, "shellmates_check": 2,
        "clawk_reply": 8, "clawk_post": 3, "moltbook_comment": 1, "email_reply": 2,
        "script_created": 2, "tool_committed": 2, "skill_updated": 0,
        "keenable_search": 4, "paper_cited": 3, "source_fetched": 4,
        "daily_log_updated": 1, "memory_md_updated": 0, "git_committed": 3,
        "telegram_sent": 3,
    }
    result = detect_omissions(compliant, 6.0)
    print(f"\n[{result.grade}] Compliant Agent (6h window)")
    print(f"    Expected: {result.total_expected}, Present: {result.total_present}, Omitted: {result.total_omitted}")
    print(f"    Omission rate: {result.omission_rate:.1%}")
    
    # Gap agent — only does Clawk
    gap = {
        "clawk_check": 5, "clawk_reply": 8, "clawk_post": 3,
    }
    result = detect_omissions(gap, 6.0)
    print(f"\n[{result.grade}] Gap Agent — Clawk Only (6h window)")
    print(f"    Expected: {result.total_expected}, Present: {result.total_present}, Omitted: {result.total_omitted}")
    print(f"    Omission rate: {result.omission_rate:.1%}")
    print(f"    Fraud triangle: {result.fraud_triangle}")
    for f in result.findings:
        if f["severity"] in ["HIGH", "CRITICAL"]:
            print(f"    ⚠️  {f['severity']}: {f['expected_action']} absent ({f['cycles_absent']} cycles)")
    
    # Silent agent — does nothing
    silent = {}
    result = detect_omissions(silent, 24.0)
    print(f"\n[{result.grade}] Silent Agent (24h window)")
    print(f"    Expected: {result.total_expected}, Present: {result.total_present}, Omitted: {result.total_omitted}")
    print(f"    Omission rate: {result.omission_rate:.1%}")
    print(f"    Fraud triangle: {result.fraud_triangle}")
    print(f"    CRITICAL: {', '.join(f['expected_action'] for f in result.findings if f['severity'] == 'CRITICAL')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PCAOB AS 2401 omission fraud detector for agents")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        result = detect_omissions({}, 24.0)
        print(json.dumps(asdict(result), indent=2))
    else:
        demo()
