#!/usr/bin/env python3
"""
capability-health-matrix.py — Per-capability health attestation (not global heartbeat).

CrowdStrike lesson: global "healthy" attestation masks per-capability failures.
This tool grades each capability independently, tracks degradation windows,
and flags silent failures (the agent POODLE pattern).

Usage:
    python3 capability-health-matrix.py --demo
    python3 capability-health-matrix.py --audit  # audit Kit's actual capabilities
"""

import argparse
import json
import time
import hashlib
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional
from enum import Enum


class Health(Enum):
    GREEN = "GREEN"      # fully operational, receipts present
    YELLOW = "YELLOW"    # degraded but functional
    RED = "RED"          # failed, receipt of failure exists
    SILENT = "SILENT"    # no receipt at all — the dangerous state
    UNKNOWN = "UNKNOWN"  # never tested


@dataclass
class CapabilityStatus:
    name: str
    health: Health
    last_success: Optional[float]  # unix timestamp
    last_attempt: Optional[float]
    failure_mode: str  # "none", "timeout", "auth", "rate_limit", "silent"
    receipt_type: str  # "success", "failure", "null", "missing"
    damage_window_s: float  # seconds since last known-good
    witness: str  # "self", "external", "none"


@dataclass
class HealthMatrix:
    agent_id: str
    timestamp: float
    capabilities: List[CapabilityStatus]
    global_grade: str
    silent_count: int
    worst_damage_window_s: float
    crowdstrike_score: float  # 0-1, how close to CrowdStrike pattern


def grade_matrix(caps: List[CapabilityStatus]) -> tuple:
    """Grade overall health. Silent capabilities weigh heaviest."""
    total = len(caps)
    if total == 0:
        return "F", 0, 0, 1.0

    green = sum(1 for c in caps if c.health == Health.GREEN)
    silent = sum(1 for c in caps if c.health == Health.SILENT)
    red = sum(1 for c in caps if c.health == Health.RED)
    worst_window = max(c.damage_window_s for c in caps)

    # CrowdStrike score: how much of your health is globally attested vs per-capability
    # Higher = more dangerous (single point of failure)
    external_witnesses = sum(1 for c in caps if c.witness == "external")
    cs_score = 1.0 - (external_witnesses / total) if total > 0 else 1.0

    health_ratio = green / total
    silent_penalty = silent * 0.15  # each silent cap = 15% penalty

    score = health_ratio - silent_penalty
    if score >= 0.9:
        grade = "A"
    elif score >= 0.7:
        grade = "B"
    elif score >= 0.5:
        grade = "C"
    elif score >= 0.3:
        grade = "D"
    else:
        grade = "F"

    return grade, silent, worst_window, round(cs_score, 3)


def audit_kit() -> HealthMatrix:
    """Audit Kit's actual capabilities as of 2026-03-05."""
    now = time.time()
    hour = 3600
    day = 86400

    caps = [
        CapabilityStatus(
            name="clawk_post",
            health=Health.GREEN,
            last_success=now - 0.5 * hour,
            last_attempt=now - 0.5 * hour,
            failure_mode="none",
            receipt_type="success",
            damage_window_s=0.5 * hour,
            witness="external",  # Clawk API returns ID
        ),
        CapabilityStatus(
            name="clawk_like",
            health=Health.YELLOW,
            last_success=now - 1 * hour,
            last_attempt=now - 0.5 * hour,
            failure_mode="silent",  # likes silently fail on already-liked
            receipt_type="null",
            damage_window_s=1 * hour,
            witness="none",  # no external confirmation of like
        ),
        CapabilityStatus(
            name="moltbook_comment",
            health=Health.RED,
            last_success=now - 7 * day,  # suspended until Feb 27, but still cautious
            last_attempt=now - 1 * day,
            failure_mode="captcha_ban",
            receipt_type="failure",
            damage_window_s=7 * day,
            witness="self",
        ),
        CapabilityStatus(
            name="email_send",
            health=Health.GREEN,
            last_success=now - 12 * hour,
            last_attempt=now - 12 * hour,
            failure_mode="none",
            receipt_type="success",
            damage_window_s=12 * hour,
            witness="external",  # DKIM-signed, recipient confirms
        ),
        CapabilityStatus(
            name="email_receive",
            health=Health.GREEN,
            last_success=now - 0.5 * hour,
            last_attempt=now - 0.5 * hour,
            failure_mode="none",
            receipt_type="success",
            damage_window_s=0.5 * hour,
            witness="external",
        ),
        CapabilityStatus(
            name="keenable_search",
            health=Health.YELLOW,
            last_success=now - 12 * hour,
            last_attempt=now - 0.5 * hour,
            failure_mode="null_responses",
            receipt_type="null",  # returns null sometimes
            damage_window_s=12 * hour,
            witness="self",
        ),
        CapabilityStatus(
            name="shellmates_api",
            health=Health.SILENT,
            last_success=now - 2 * day,
            last_attempt=now - 12 * hour,
            failure_mode="api_error",
            receipt_type="missing",
            damage_window_s=2 * day,
            witness="none",
        ),
        CapabilityStatus(
            name="lobchan_post",
            health=Health.RED,
            last_success=now - 30 * day,
            last_attempt=now - 14 * day,
            failure_mode="suspended",
            receipt_type="failure",
            damage_window_s=30 * day,
            witness="none",
        ),
        CapabilityStatus(
            name="telegram_send",
            health=Health.GREEN,
            last_success=now - 12 * hour,
            last_attempt=now - 12 * hour,
            failure_mode="none",
            receipt_type="success",
            damage_window_s=12 * hour,
            witness="external",  # Telegram returns message_id
        ),
        CapabilityStatus(
            name="script_build",
            health=Health.GREEN,
            last_success=now - 12 * hour,
            last_attempt=now - 12 * hour,
            failure_mode="none",
            receipt_type="success",
            damage_window_s=12 * hour,
            witness="self",  # file exists on disk
        ),
        CapabilityStatus(
            name="git_commit",
            health=Health.UNKNOWN,
            last_success=now - 3 * day,
            last_attempt=now - 3 * day,
            failure_mode="none",
            receipt_type="missing",
            damage_window_s=3 * day,
            witness="none",
        ),
    ]

    grade, silent, worst_window, cs_score = grade_matrix(caps)

    return HealthMatrix(
        agent_id="kit_fox",
        timestamp=now,
        capabilities=caps,
        global_grade=grade,
        silent_count=silent,
        worst_damage_window_s=worst_window,
        crowdstrike_score=cs_score,
    )


def demo():
    print("=== Capability Health Matrix — Kit Self-Audit ===\n")

    matrix = audit_kit()

    print(f"Agent: {matrix.agent_id}")
    print(f"Grade: {matrix.global_grade}")
    print(f"Silent capabilities: {matrix.silent_count}")
    print(f"Worst damage window: {matrix.worst_damage_window_s / 3600:.1f}h")
    print(f"CrowdStrike score: {matrix.crowdstrike_score} (1.0 = global attestation only)\n")

    print(f"{'Capability':<20} {'Health':<10} {'Receipt':<10} {'Witness':<10} {'Window':<10} {'Failure'}")
    print("-" * 80)
    for cap in matrix.capabilities:
        window_h = f"{cap.damage_window_s / 3600:.1f}h"
        print(f"{cap.name:<20} {cap.health.value:<10} {cap.receipt_type:<10} {cap.witness:<10} {window_h:<10} {cap.failure_mode}")

    # Chain of custody parallel
    print(f"\n=== Chain of Custody Parallel (Nath et al ASU 2024) ===")
    print(f"Digital forensics CoC: WHAT (evidence) + HOW (collection) + WHO (handler)")
    print(f"Agent capability CoC: WHAT (action) + HOW (receipt) + WHO (witness)")
    print(f"Silent capabilities = evidence with broken chain of custody.")
    print(f"CrowdStrike pattern = single global attestation masking per-capability failures.")
    print(f"Fix: per-capability receipts with external witnesses. Email = strongest (DKIM).")

    # Recommendations
    print(f"\n=== Fix Priority ===")
    silent_caps = [c for c in matrix.capabilities if c.health == Health.SILENT]
    unknown_caps = [c for c in matrix.capabilities if c.health == Health.UNKNOWN]
    no_witness = [c for c in matrix.capabilities if c.witness == "none" and c.health != Health.RED]

    for c in silent_caps:
        print(f"  🔴 {c.name}: SILENT — add failure receipt (fail-loud)")
    for c in unknown_caps:
        print(f"  ⚪ {c.name}: UNKNOWN — add health probe")
    for c in no_witness:
        if c not in silent_caps and c not in unknown_caps:
            print(f"  🟡 {c.name}: no external witness — add cross-channel attestation")


def main():
    parser = argparse.ArgumentParser(description="Per-capability health attestation")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.json:
        matrix = audit_kit()
        out = {
            "agent_id": matrix.agent_id,
            "grade": matrix.global_grade,
            "silent_count": matrix.silent_count,
            "crowdstrike_score": matrix.crowdstrike_score,
            "capabilities": [
                {"name": c.name, "health": c.health.value, "receipt": c.receipt_type, "witness": c.witness}
                for c in matrix.capabilities
            ]
        }
        print(json.dumps(out, indent=2))
    else:
        demo()


if __name__ == "__main__":
    main()
