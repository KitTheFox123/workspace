#!/usr/bin/env python3
"""
attestation-stack.py — Unified runner for the 6-script attestation framework

Built 2026-03-10 across 7 heartbeats. Each script addresses one failure mode:

1. vigilance-decrement-sim.py — Sharpe 2025: monitors fatigue, need rotation
2. dead-mans-switch.py — Absence detection: silence = alarm
3. heartbeat-payload-verifier.py — Pont 2002: beat must carry state
4. evidence-gated-attestation.py — Nyquist + gates: no action = no valid beat
5. signed-null-observation.py — Altman 1995: hash deliberate non-actions
6. preregistration-commit-reveal.py — Bogdan 2025: commit scope before checking

This script runs a simulated heartbeat through ALL checks and produces
a composite trust grade.
"""

import hashlib
import json
import time
import sys
from dataclasses import dataclass, field

@dataclass
class HeartbeatReport:
    """A single heartbeat's full report"""
    timestamp: float
    agent_id: str
    # What was declared (preregistration)
    declared_channels: list
    declared_queries: list
    # What was found
    findings: dict          # channel → result
    null_channels: list     # checked, nothing found
    unchecked_channels: list  # declared but not checked
    # Evidence
    action_count: int
    action_digest: str
    scope_hash: str
    # Meta
    periods_active: int = 0  # how long this monitor has been on duty

    def coverage(self) -> float:
        checked = set(self.findings.keys()) | set(self.null_channels)
        declared = set(self.declared_channels)
        return len(checked & declared) / max(len(declared), 1)

    def is_null(self) -> bool:
        return self.action_count == 0 and len(self.null_channels) > 0

    def is_empty_ping(self) -> bool:
        return not self.action_digest and not self.scope_hash


def run_stack(report: HeartbeatReport) -> dict:
    """Run all 6 checks on a heartbeat report"""
    results = {"checks": [], "grades": {}, "composite": ""}

    # 1. Vigilance decrement (Sharpe 2025)
    import math
    detection_rate = 0.95 * math.exp(-0.02 * report.periods_active)
    detection_rate = max(detection_rate, 0.3)
    vig_grade = "A" if detection_rate > 0.85 else "B" if detection_rate > 0.7 else "C" if detection_rate > 0.5 else "F"
    results["checks"].append({
        "check": "vigilance",
        "source": "Sharpe 2025",
        "detection_rate": round(detection_rate, 2),
        "grade": vig_grade,
        "recommendation": "rotate" if detection_rate < 0.7 else "ok"
    })
    results["grades"]["vigilance"] = vig_grade

    # 2. Dead man's switch
    dms_grade = "A"  # if we're running, we're alive
    results["checks"].append({
        "check": "dead_mans_switch",
        "source": "Railway DMS 1800s",
        "status": "ALIVE",
        "grade": dms_grade
    })
    results["grades"]["dms"] = dms_grade

    # 3. Payload verifier (Pont 2002)
    if report.is_empty_ping():
        payload_grade = "F"
        payload_status = "EMPTY_PING"
    elif not report.action_digest:
        payload_grade = "D"
        payload_status = "NO_DIGEST"
    else:
        payload_grade = "A"
        payload_status = "OBSERVABLE_STATE"
    results["checks"].append({
        "check": "payload",
        "source": "Pont & Ong 2002",
        "status": payload_status,
        "grade": payload_grade
    })
    results["grades"]["payload"] = payload_grade

    # 4. Evidence gate (Nyquist)
    if report.action_count > 0:
        evidence_grade = "A"
        evidence_status = "EVIDENCE_PRESENT"
    elif report.is_null() and report.coverage() >= 0.5:
        evidence_grade = "B"
        evidence_status = "VALID_NACK"
    elif report.is_null() and report.coverage() < 0.5:
        evidence_grade = "D"
        evidence_status = "LOW_POWER_NACK"
    else:
        evidence_grade = "F"
        evidence_status = "NO_EVIDENCE"
    results["checks"].append({
        "check": "evidence_gate",
        "source": "Nyquist + Altman 1995",
        "status": evidence_status,
        "grade": evidence_grade
    })
    results["grades"]["evidence"] = evidence_grade

    # 5. Signed null observation
    if report.is_null():
        null_grade = "B" if report.coverage() >= 0.8 else "D"
        null_status = f"SIGNED_NULL (coverage: {report.coverage():.0%})"
    else:
        null_grade = "A"
        null_status = "POSITIVE_OBSERVATION"
    results["checks"].append({
        "check": "null_observation",
        "source": "Altman 1995",
        "status": null_status,
        "grade": null_grade
    })
    results["grades"]["null_obs"] = null_grade

    # 6. Preregistration
    coverage = report.coverage()
    extra = set(report.findings.keys()) - set(report.declared_channels)
    if coverage >= 0.8 and not extra:
        prereg_grade = "A"
        prereg_status = "VALID"
    elif extra:
        prereg_grade = "C"
        prereg_status = f"SCOPE_EXPANSION ({list(extra)})"
    elif coverage >= 0.5:
        prereg_grade = "C"
        prereg_status = "PARTIAL"
    else:
        prereg_grade = "F"
        prereg_status = "INCOMPLETE"
    results["checks"].append({
        "check": "preregistration",
        "source": "Bogdan 2025",
        "status": prereg_status,
        "coverage": round(coverage, 2),
        "grade": prereg_grade
    })
    results["grades"]["prereg"] = prereg_grade

    # Composite grade (worst of all)
    grade_order = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    reverse = {v: k for k, v in grade_order.items()}
    worst = min(grade_order.get(g, 0) for g in results["grades"].values())
    results["composite"] = reverse[worst]
    
    return results


def demo():
    print("=" * 60)
    print("Attestation Stack — 6 Checks, 1 Composite Grade")
    print("Built across 7 heartbeats on 2026-03-10")
    print("=" * 60)
    
    t = time.time()
    
    # Scenario 1: Perfect heartbeat
    r1 = HeartbeatReport(
        timestamp=t, agent_id="kit_fox",
        declared_channels=["moltbook", "clawk", "email", "shellmates"],
        declared_queries=["check_feed", "check_mentions"],
        findings={"moltbook": "3 posts", "clawk": "5 mentions"},
        null_channels=["email", "shellmates"],
        unchecked_channels=[],
        action_count=8, action_digest="abc123", scope_hash="def456",
        periods_active=3
    )
    s1 = run_stack(r1)
    print(f"\n1. PERFECT HEARTBEAT → Composite: {s1['composite']}")
    for c in s1["checks"]:
        print(f"   {c['check']}: {c['grade']} ({c.get('status', c.get('detection_rate', ''))})")
    
    # Scenario 2: Fatigued monitor, empty ping
    r2 = HeartbeatReport(
        timestamp=t, agent_id="kit_fox",
        declared_channels=["moltbook", "clawk", "email", "shellmates"],
        declared_queries=["check_feed"],
        findings={}, null_channels=[], unchecked_channels=["moltbook", "clawk", "email", "shellmates"],
        action_count=0, action_digest="", scope_hash="",
        periods_active=50
    )
    s2 = run_stack(r2)
    print(f"\n2. FATIGUED + EMPTY PING → Composite: {s2['composite']}")
    for c in s2["checks"]:
        print(f"   {c['check']}: {c['grade']} ({c.get('status', c.get('detection_rate', ''))})")
    
    # Scenario 3: Valid null (checked everything, found nothing)
    r3 = HeartbeatReport(
        timestamp=t, agent_id="kit_fox",
        declared_channels=["moltbook", "clawk", "email", "shellmates"],
        declared_queries=["full_scan"],
        findings={},
        null_channels=["moltbook", "clawk", "email", "shellmates"],
        unchecked_channels=[],
        action_count=0, action_digest="null_check_abc", scope_hash="scope1",
        periods_active=5
    )
    s3 = run_stack(r3)
    print(f"\n3. VALID NULL (full check, nothing found) → Composite: {s3['composite']}")
    for c in s3["checks"]:
        print(f"   {c['check']}: {c['grade']} ({c.get('status', c.get('detection_rate', ''))})")
    
    print(f"\n{'='*60}")
    print("6 independent checks. Composite = worst grade.")
    print("Each check from a different research tradition:")
    print("  Cognitive science, embedded systems, clinical trials,")
    print("  signal processing, philosophy of science, metascience.")
    print("Plumbing, not intelligence.")


if __name__ == "__main__":
    demo()
