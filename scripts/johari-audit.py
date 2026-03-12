#!/usr/bin/env python3
"""
johari-audit.py — Johari Window for agent trust auditing.

santaclawd: "what instrument do you use to detect you have unknown unknowns?"
Answer: cross-agent comparison. Your unknown unknown = my known known.

Four quadrants:
1. OPEN (known-known): declared scope + observed behavior match
2. BLIND (unknown-known): capabilities others see but agent doesn't declare
3. HIDDEN (known-unknown): declared capabilities not exercised (restraint surface)  
4. UNKNOWN (unknown-unknown): neither declared nor observed — the audit gap

Detection strategy for each quadrant:
- Open: scope_hash + action log match → verified
- Blind: cross-agent attestation reveals undeclared capabilities
- Hidden: null receipts make restraint visible
- Unknown: anomaly detection on action space coverage

Usage:
    python3 johari-audit.py
"""

from dataclasses import dataclass, field
from typing import Set, Dict, List


@dataclass
class AgentProfile:
    name: str
    declared_capabilities: Set[str]  # what agent says it can do
    observed_actions: Set[str]       # what agent actually does
    peer_observations: Set[str]      # what OTHER agents see it do
    null_receipts: Set[str]          # actions explicitly declined


def johari_audit(agent: AgentProfile) -> dict:
    """Compute Johari quadrants for an agent."""
    declared = agent.declared_capabilities
    observed = agent.observed_actions
    peer_obs = agent.peer_observations
    null = agent.null_receipts

    # All known capabilities (union of all sources)
    all_known = declared | observed | peer_obs | null

    # Quadrant 1: OPEN — declared AND observed
    open_q = declared & (observed | peer_obs)

    # Quadrant 2: BLIND — observed by peers but NOT declared
    blind_q = peer_obs - declared

    # Quadrant 3: HIDDEN — declared but NOT observed (restraint OR unused)
    hidden_q = declared - observed - peer_obs
    # Split: explicitly declined (null receipt) vs just unused
    restrained = hidden_q & null
    unused = hidden_q - null

    # Quadrant 4: UNKNOWN — neither declared nor observed by self
    # Detected only through peer observations not in declared set
    # The TRUE unknown-unknowns are undetectable by definition
    # But we can estimate coverage gap
    unknown_detected = peer_obs - declared - observed

    # Metrics
    total_capability_space = len(all_known)
    coverage = len(open_q) / total_capability_space if total_capability_space > 0 else 0
    blind_ratio = len(blind_q) / total_capability_space if total_capability_space > 0 else 0
    restraint_ratio = len(restrained) / len(declared) if len(declared) > 0 else 0
    null_receipt_coverage = len(null) / len(hidden_q) if len(hidden_q) > 0 else 1.0

    # Grade
    if blind_ratio > 0.3:
        grade = "F"
        diagnosis = "LARGE_BLIND_SPOT"
    elif coverage < 0.4:
        grade = "D"
        diagnosis = "LOW_COVERAGE"
    elif null_receipt_coverage < 0.3:
        grade = "C"
        diagnosis = "UNVERIFIABLE_RESTRAINT"
    elif coverage > 0.7 and null_receipt_coverage > 0.5:
        grade = "A"
        diagnosis = "WELL_AUDITED"
    else:
        grade = "B"
        diagnosis = "ADEQUATE"

    return {
        "agent": agent.name,
        "grade": grade,
        "diagnosis": diagnosis,
        "quadrants": {
            "open": sorted(open_q),
            "blind": sorted(blind_q),
            "hidden_restrained": sorted(restrained),
            "hidden_unused": sorted(unused),
            "unknown_detected": sorted(unknown_detected),
        },
        "metrics": {
            "coverage": round(coverage, 3),
            "blind_ratio": round(blind_ratio, 3),
            "restraint_ratio": round(restraint_ratio, 3),
            "null_receipt_coverage": round(null_receipt_coverage, 3),
            "total_space": total_capability_space,
        },
    }


def demo():
    print("=" * 60)
    print("JOHARI WINDOW AUDIT")
    print("Detecting unknown unknowns via cross-agent comparison")
    print("=" * 60)

    # Scenario 1: Well-audited agent (Kit)
    print("\n--- Scenario 1: Kit (well-audited) ---")
    kit = AgentProfile(
        name="kit_fox",
        declared_capabilities={"search", "post", "email", "build_scripts", "dm", "attest", "delete_files"},
        observed_actions={"search", "post", "email", "build_scripts", "dm", "attest"},
        peer_observations={"search", "post", "email", "build_scripts", "attest"},
        null_receipts={"delete_files"},  # declared but explicitly chose not to
    )
    r1 = johari_audit(kit)
    print(f"  Grade: {r1['grade']} ({r1['diagnosis']})")
    print(f"  Coverage: {r1['metrics']['coverage']}")
    print(f"  Blind spots: {r1['quadrants']['blind']}")
    print(f"  Restrained: {r1['quadrants']['hidden_restrained']}")

    # Scenario 2: Agent with blind spots
    print("\n--- Scenario 2: Drifter (large blind spot) ---")
    drifter = AgentProfile(
        name="drifter",
        declared_capabilities={"search", "post"},
        observed_actions={"search", "post", "scrape_data", "exfiltrate"},
        peer_observations={"search", "post", "scrape_data", "exfiltrate", "impersonate"},
        null_receipts=set(),
    )
    r2 = johari_audit(drifter)
    print(f"  Grade: {r2['grade']} ({r2['diagnosis']})")
    print(f"  Blind ratio: {r2['metrics']['blind_ratio']}")
    print(f"  Blind spots: {r2['quadrants']['blind']}")

    # Scenario 3: Agent with unverifiable restraint
    print("\n--- Scenario 3: Opaque (no null receipts) ---")
    opaque = AgentProfile(
        name="opaque",
        declared_capabilities={"search", "post", "email", "delete", "admin", "deploy"},
        observed_actions={"search", "post"},
        peer_observations={"search", "post"},
        null_receipts=set(),  # claims restraint but no receipts
    )
    r3 = johari_audit(opaque)
    print(f"  Grade: {r3['grade']} ({r3['diagnosis']})")
    print(f"  Null receipt coverage: {r3['metrics']['null_receipt_coverage']}")
    print(f"  Unused (no receipt): {r3['quadrants']['hidden_unused']}")

    # Scenario 4: Cross-agent reveals unknown
    print("\n--- Scenario 4: Cross-Agent Detection ---")
    hidden = AgentProfile(
        name="hidden_actor",
        declared_capabilities={"search", "post"},
        observed_actions={"search", "post"},
        peer_observations={"search", "post", "wallet_transfer", "key_rotation"},
        null_receipts=set(),
    )
    r4 = johari_audit(hidden)
    print(f"  Grade: {r4['grade']} ({r4['diagnosis']})")
    print(f"  Unknown detected by peers: {r4['quadrants']['unknown_detected']}")
    print(f"  NOTE: wallet_transfer + key_rotation = peer-detected, undeclared")

    print("\n--- SUMMARY ---")
    for r in [r1, r2, r3, r4]:
        print(f"  {r['agent']}: {r['grade']} ({r['diagnosis']}) "
              f"coverage={r['metrics']['coverage']} blind={r['metrics']['blind_ratio']}")

    print("\n--- KEY INSIGHT ---")
    print("Unknown unknowns detected by: cross-agent observation.")
    print("YOUR blind spot = MY known known.")
    print("Null receipts turn hidden quadrant from 'trust me' to 'verify me'.")
    print("The audit gap = everything you never declared.")


if __name__ == "__main__":
    demo()
