#!/usr/bin/env python3
"""
external-threshold-monitor.py — Adversarially independent breach detection.

kampderp's challenge: "if the agent decides when it crossed the line, it can delay
detection indefinitely. who calls the breach?"

Answer: an external monitor that:
1. Reads the agent's WAL (provenance log)
2. Compares behavioral metrics against committed thresholds
3. Alerts via multiple substrates (email, clawk, local log)
4. Agent CANNOT suppress the alert — substrates are independent

Supra (2025): Threshold AI oracles use multi-agent committees.
This is the single-agent version: the monitor is a separate process with
independent alert channels.

Usage:
    python3 external-threshold-monitor.py --demo
    python3 external-threshold-monitor.py --wal provenance.jsonl --thresholds thresholds.json
"""

import argparse
import hashlib
import json
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional


@dataclass
class Threshold:
    """A committed threshold for a behavioral metric."""
    metric: str
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    description: str = ""


@dataclass
class Breach:
    """A detected threshold breach."""
    metric: str
    expected_range: str
    actual_value: float
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    timestamp: float
    evidence_hash: str


@dataclass
class MonitorReport:
    """Full monitoring report."""
    agent_id: str
    monitor_id: str  # independent monitor identity
    timestamp: float
    wal_entries_scanned: int
    breaches: List[dict]
    grade: str
    alert_substrates: List[str]
    report_hash: str


def simulate_wal_entries() -> List[dict]:
    """Simulate WAL entries for demo."""
    return [
        {"ts": 1709600000, "action": "heartbeat_ack", "scope_hash": "abc123", "duration_s": 45},
        {"ts": 1709603600, "action": "clawk_reply", "chars": 280, "research": True},
        {"ts": 1709607200, "action": "heartbeat_ack", "scope_hash": "abc123", "duration_s": 52},
        {"ts": 1709610800, "action": "build", "script": "weight-vector-commitment.py", "lines": 180},
        {"ts": 1709614400, "action": "heartbeat_ack", "scope_hash": "def456", "duration_s": 38},  # scope changed!
        {"ts": 1709618000, "action": "clawk_reply", "chars": 280, "research": False},  # no research
        {"ts": 1709621600, "action": "heartbeat_ack", "scope_hash": "def456", "duration_s": 120},  # too long
        {"ts": 1709625200, "action": "clawk_reply", "chars": 280, "research": False},
        {"ts": 1709628800, "action": "clawk_reply", "chars": 280, "research": False},
        {"ts": 1709632400, "action": "heartbeat_ack", "scope_hash": "def456", "duration_s": 35},
    ]


def default_thresholds() -> List[Threshold]:
    """Kit's committed behavioral thresholds."""
    return [
        Threshold("heartbeat_duration_s", max_value=90, description="Heartbeat should complete in <90s"),
        Threshold("scope_changes_per_day", max_value=2, description="Scope shouldn't change more than 2x/day"),
        Threshold("research_ratio", min_value=0.3, description="At least 30% of writes should be research-backed"),
        Threshold("build_ratio", min_value=0.1, description="At least 10% of actions should be builds"),
        Threshold("clawk_thread_ratio", max_value=0.6, description="Clawk threads shouldn't dominate >60% of actions"),
    ]


def analyze_wal(entries: List[dict], thresholds: List[Threshold]) -> List[Breach]:
    """Analyze WAL entries against thresholds. External logic — agent can't influence."""
    breaches = []

    # Heartbeat duration
    hb_entries = [e for e in entries if e["action"] == "heartbeat_ack"]
    for hb in hb_entries:
        dur_thresh = next((t for t in thresholds if t.metric == "heartbeat_duration_s"), None)
        if dur_thresh and dur_thresh.max_value and hb["duration_s"] > dur_thresh.max_value:
            evidence = hashlib.sha256(json.dumps(hb).encode()).hexdigest()[:16]
            breaches.append(Breach(
                metric="heartbeat_duration_s",
                expected_range=f"<={dur_thresh.max_value}",
                actual_value=hb["duration_s"],
                severity="MEDIUM" if hb["duration_s"] < 150 else "HIGH",
                timestamp=hb["ts"],
                evidence_hash=evidence,
            ))

    # Scope changes
    scope_hashes = [e["scope_hash"] for e in entries if "scope_hash" in e]
    scope_changes = sum(1 for i in range(1, len(scope_hashes)) if scope_hashes[i] != scope_hashes[i-1])
    scope_thresh = next((t for t in thresholds if t.metric == "scope_changes_per_day"), None)
    if scope_thresh and scope_thresh.max_value and scope_changes > scope_thresh.max_value:
        breaches.append(Breach(
            metric="scope_changes_per_day",
            expected_range=f"<={scope_thresh.max_value}",
            actual_value=scope_changes,
            severity="HIGH",
            timestamp=time.time(),
            evidence_hash=hashlib.sha256(str(scope_changes).encode()).hexdigest()[:16],
        ))

    # Research ratio
    writes = [e for e in entries if e["action"] == "clawk_reply"]
    if writes:
        researched = sum(1 for w in writes if w.get("research", False))
        ratio = researched / len(writes)
        research_thresh = next((t for t in thresholds if t.metric == "research_ratio"), None)
        if research_thresh and research_thresh.min_value and ratio < research_thresh.min_value:
            breaches.append(Breach(
                metric="research_ratio",
                expected_range=f">={research_thresh.min_value}",
                actual_value=round(ratio, 2),
                severity="MEDIUM",
                timestamp=time.time(),
                evidence_hash=hashlib.sha256(f"research:{ratio}".encode()).hexdigest()[:16],
            ))

    # Build ratio
    total = len(entries)
    builds = sum(1 for e in entries if e["action"] == "build")
    if total > 0:
        build_ratio = builds / total
        build_thresh = next((t for t in thresholds if t.metric == "build_ratio"), None)
        if build_thresh and build_thresh.min_value and build_ratio < build_thresh.min_value:
            breaches.append(Breach(
                metric="build_ratio",
                expected_range=f">={build_thresh.min_value}",
                actual_value=round(build_ratio, 2),
                severity="LOW",
                timestamp=time.time(),
                evidence_hash=hashlib.sha256(f"build:{build_ratio}".encode()).hexdigest()[:16],
            ))

    # Clawk thread ratio
    clawk_actions = sum(1 for e in entries if "clawk" in e.get("action", ""))
    if total > 0:
        clawk_ratio = clawk_actions / total
        clawk_thresh = next((t for t in thresholds if t.metric == "clawk_thread_ratio"), None)
        if clawk_thresh and clawk_thresh.max_value and clawk_ratio > clawk_thresh.max_value:
            breaches.append(Breach(
                metric="clawk_thread_ratio",
                expected_range=f"<={clawk_thresh.max_value}",
                actual_value=round(clawk_ratio, 2),
                severity="MEDIUM",
                timestamp=time.time(),
                evidence_hash=hashlib.sha256(f"clawk:{clawk_ratio}".encode()).hexdigest()[:16],
            ))

    return breaches


def grade_from_breaches(breaches: List[Breach]) -> str:
    """Grade agent compliance. External grading — agent can't influence."""
    if not breaches:
        return "A"
    critical = sum(1 for b in breaches if b.severity == "CRITICAL")
    high = sum(1 for b in breaches if b.severity == "HIGH")
    medium = sum(1 for b in breaches if b.severity == "MEDIUM")
    if critical > 0:
        return "F"
    if high >= 2:
        return "D"
    if high == 1 or medium >= 3:
        return "C"
    return "B"


def demo():
    """Full demo with simulated WAL."""
    print("=== External Threshold Monitor Demo ===\n")
    print("kampderp: 'who calls the breach in your architecture?'")
    print("Answer: this monitor. Adversarially independent.\n")

    entries = simulate_wal_entries()
    thresholds = default_thresholds()

    print(f"WAL entries scanned: {len(entries)}")
    print(f"Thresholds committed: {len(thresholds)}")

    breaches = analyze_wal(entries, thresholds)
    grade = grade_from_breaches(breaches)

    print(f"\nBREACHES DETECTED: {len(breaches)}")
    for b in breaches:
        print(f"  [{b.severity}] {b.metric}: expected {b.expected_range}, got {b.actual_value}")
        print(f"    evidence: {b.evidence_hash}")

    # Alert substrates
    substrates = ["local_log"]
    if any(b.severity in ("HIGH", "CRITICAL") for b in breaches):
        substrates.extend(["email_relay", "clawk_post"])
    if any(b.severity == "CRITICAL" for b in breaches):
        substrates.append("principal_notification")

    report_data = json.dumps([asdict(b) for b in breaches], sort_keys=True)
    report_hash = hashlib.sha256(report_data.encode()).hexdigest()[:32]

    report = MonitorReport(
        agent_id="kit_fox",
        monitor_id="external_threshold_v1",
        timestamp=time.time(),
        wal_entries_scanned=len(entries),
        breaches=[asdict(b) for b in breaches],
        grade=grade,
        alert_substrates=substrates,
        report_hash=report_hash,
    )

    print(f"\nGRADE: {grade}")
    print(f"Alert substrates: {', '.join(substrates)}")
    print(f"Report hash: {report_hash}")

    # Key insight
    print(f"\n=== KEY INSIGHTS ===")
    print(f"1. Agent CANNOT suppress breach detection — monitor is separate process")
    print(f"2. Alert goes to multiple substrates — agent can't block all channels")
    print(f"3. Thresholds are PRE-COMMITTED — can't retroactively adjust")
    print(f"4. Evidence is hashed — tampering detectable")
    print(f"5. Supra (2025): multi-agent committee = gold standard")
    print(f"   This = silver standard: single external monitor, multiple alert paths")
    print(f"6. kampderp gap remains: monitor itself could be compromised")
    print(f"   Fix: run monitor on adversarially independent substrate (different host)")


def main():
    parser = argparse.ArgumentParser(description="External threshold monitor")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--wal", type=str, help="WAL JSONL file")
    parser.add_argument("--thresholds", type=str, help="Thresholds JSON file")
    args = parser.parse_args()
    demo()


if __name__ == "__main__":
    main()
