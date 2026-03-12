#!/usr/bin/env python3
"""
epoch-transition-auditor.py — Audit the attack window during epoch transitions.

Epoch = period between governance changes (scope update, CID rotation, key rotation).
The transition gap = time between "new scope applies" and "new attestations bind."

Pattern from TLS cert rotation: overlap period where both old and new are valid.
Heartbleed taught us: revoke-then-deploy = gap. Deploy-then-revoke = overlap (safe).

Usage:
    python3 epoch-transition-auditor.py --demo
    python3 epoch-transition-auditor.py --heartbeat-interval 40 --attestation-latency 5
"""

import argparse
import hashlib
import json
import time
from dataclasses import dataclass, asdict
from typing import List, Optional


@dataclass
class EpochTransition:
    """A single epoch boundary event."""
    epoch_id: int
    trigger: str  # governance_vote, scope_change, key_rotation, model_migration
    old_cid_prefix: str
    new_cid_prefix: str
    transition_start: float  # when new scope applies
    attestation_bind: float  # when new attestations cover new scope
    gap_seconds: float  # the attack window
    grace_period: float  # dual-CID overlap
    grade: str


@dataclass
class TransitionAudit:
    """Full audit of an agent's epoch transition security."""
    agent_id: str
    transitions: List[EpochTransition]
    avg_gap: float
    max_gap: float
    has_dual_cid: bool
    has_peer_witness: bool
    grade: str
    recommendations: List[str]


def hash_scope(scope_data: dict) -> str:
    return hashlib.sha256(json.dumps(scope_data, sort_keys=True).encode()).hexdigest()[:16]


def simulate_transition(epoch_id: int, trigger: str, heartbeat_interval: float,
                        attestation_latency: float, grace_period: float = 0) -> EpochTransition:
    """Simulate a single epoch transition."""
    old_scope = {"epoch": epoch_id, "version": "old"}
    new_scope = {"epoch": epoch_id + 1, "version": "new"}

    old_cid = hash_scope(old_scope)
    new_cid = hash_scope(new_scope)

    # Gap = time from scope change to next attestation
    # Without grace period: full heartbeat interval is the gap
    # With grace period: old attestations still honored
    raw_gap = heartbeat_interval * 60 + attestation_latency
    effective_gap = max(0, raw_gap - grace_period)

    # Grade
    if effective_gap < 60:
        grade = "A"  # < 1 min
    elif effective_gap < 300:
        grade = "B"  # < 5 min
    elif effective_gap < 1800:
        grade = "C"  # < 30 min
    else:
        grade = "F"  # > 30 min

    return EpochTransition(
        epoch_id=epoch_id,
        trigger=trigger,
        old_cid_prefix=old_cid,
        new_cid_prefix=new_cid,
        transition_start=time.time(),
        attestation_bind=time.time() + effective_gap,
        gap_seconds=effective_gap,
        grace_period=grace_period,
        grade=grade,
    )


def audit_agent(agent_id: str, heartbeat_min: float = 40, attestation_latency: float = 5,
                grace_period: float = 0, has_peer_witness: bool = False) -> TransitionAudit:
    """Audit an agent's epoch transition security."""
    triggers = [
        "scope_change",      # HEARTBEAT.md edit
        "key_rotation",      # new signing key
        "model_migration",   # Opus 4.5 → 4.6
        "governance_vote",   # principal changes rules
        "cid_prefix_change", # algorithm rotation
    ]

    transitions = []
    for i, trigger in enumerate(triggers):
        # Model migration has longer gap (hours, not minutes)
        hb = heartbeat_min if trigger != "model_migration" else 360
        gp = grace_period
        # Peer witness reduces effective gap
        if has_peer_witness:
            gp += heartbeat_min * 30  # 50% of heartbeat as witness coverage

        t = simulate_transition(i, trigger, hb, attestation_latency, gp)
        transitions.append(t)

    gaps = [t.gap_seconds for t in transitions]
    avg_gap = sum(gaps) / len(gaps)
    max_gap = max(gaps)

    has_dual = grace_period > 0

    # Overall grade
    if max_gap < 60:
        grade = "A"
    elif max_gap < 300:
        grade = "B"
    elif max_gap < 3600:
        grade = "C"
    else:
        grade = "F"

    recs = []
    if not has_dual:
        recs.append("Add dual-CID grace period (TLS overlap pattern)")
    if not has_peer_witness:
        recs.append("Add peer witness at epoch boundary")
    if max_gap > 1800:
        recs.append(f"Model migration gap ({max_gap/60:.0f}min) needs pre-announcement + witness")
    for t in transitions:
        if t.grade in ("C", "F"):
            recs.append(f"{t.trigger}: grade {t.grade} ({t.gap_seconds/60:.1f}min gap)")

    return TransitionAudit(
        agent_id=agent_id,
        transitions=transitions,
        avg_gap=round(avg_gap, 1),
        max_gap=round(max_gap, 1),
        has_dual_cid=has_dual,
        has_peer_witness=has_peer_witness,
        grade=grade,
        recommendations=recs,
    )


def demo():
    print("=== Epoch Transition Auditor ===\n")

    # Kit current: no grace period, no peer witness
    print("1. KIT (current setup)")
    audit = audit_agent("kit_fox", heartbeat_min=40, grace_period=0, has_peer_witness=False)
    print(f"   Grade: {audit.grade}")
    print(f"   Avg gap: {audit.avg_gap/60:.1f} min")
    print(f"   Max gap: {audit.max_gap/60:.1f} min")
    print(f"   Dual-CID: {audit.has_dual_cid}")
    print(f"   Peer witness: {audit.has_peer_witness}")
    for t in audit.transitions:
        print(f"   - {t.trigger}: {t.gap_seconds/60:.1f}min gap → {t.grade}")
    print(f"   Recommendations:")
    for r in audit.recommendations:
        print(f"     → {r}")

    # Kit with grace period
    print(f"\n2. KIT (with 10min dual-CID grace)")
    audit2 = audit_agent("kit_fox", heartbeat_min=40, grace_period=600, has_peer_witness=False)
    print(f"   Grade: {audit2.grade}")
    print(f"   Max gap: {audit2.max_gap/60:.1f} min")
    for t in audit2.transitions:
        print(f"   - {t.trigger}: {t.gap_seconds/60:.1f}min → {t.grade}")

    # Kit with grace + peer witness
    print(f"\n3. KIT (grace + peer witness)")
    audit3 = audit_agent("kit_fox", heartbeat_min=40, grace_period=600, has_peer_witness=True)
    print(f"   Grade: {audit3.grade}")
    print(f"   Max gap: {audit3.max_gap/60:.1f} min")
    for t in audit3.transitions:
        print(f"   - {t.trigger}: {t.gap_seconds/60:.1f}min → {t.grade}")

    # Parallel to TLS
    print(f"\n4. TLS PARALLEL")
    print("   Heartbleed (2014): revoke → deploy = gap where both certs invalid")
    print("   Fix: deploy new cert FIRST, then revoke old (overlap)")
    print("   Agent: apply new scope + keep honoring old attestations for T_grace")
    print("   The overlap IS the security. No gap = no attack window.")

    # Parallel to sleep
    print(f"\n5. COGNITIVE PARALLEL")
    print("   Sleep inertia (Tassi & Muzet 2000): waking = epoch transition")
    print("   Cognitive performance DROPS during transition (up to 30min)")
    print("   The brain honors old patterns while loading new ones")
    print("   Dual-CID = sleep inertia grace period. Both states valid during switch.")


def main():
    parser = argparse.ArgumentParser(description="Epoch transition auditor")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--heartbeat-interval", type=float, default=40)
    parser.add_argument("--attestation-latency", type=float, default=5)
    parser.add_argument("--grace-period", type=float, default=0)
    parser.add_argument("--peer-witness", action="store_true")
    args = parser.parse_args()

    if args.demo or not any([args.grace_period, args.peer_witness]):
        demo()
    else:
        audit = audit_agent("kit_fox", args.heartbeat_interval, args.attestation_latency,
                           args.grace_period, args.peer_witness)
        print(json.dumps(asdict(audit), indent=2, default=str))


if __name__ == "__main__":
    main()
