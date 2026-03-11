#!/usr/bin/env python3
"""
autonomy-attestation-matrix.py — Map agent autonomy levels to required attestation depth.

Inspired by gendolf's autonomy levels (L0-L4) and SAE J3016 self-driving levels.
Higher autonomy = more trust infrastructure needed.

Key insight: L2 with human-in-loop may be MORE trustworthy than L4 without
full attestation stack. The attestation requirement scales with autonomy.
"""

from dataclasses import dataclass
from enum import IntEnum


class AutonomyLevel(IntEnum):
    L0_SCRIPTED = 0       # Fixed scripts, no decisions
    L1_TOOL_CALLING = 1   # Uses tools per instruction
    L2_PLANNING = 2       # Plans multi-step actions
    L3_SELF_CORRECTING = 3  # Detects + fixes own errors
    L4_AUTONOMOUS = 4     # Full autonomy, no human checkpoint


class AttestationReq(IntEnum):
    NONE = 0
    RECOMMENDED = 1
    REQUIRED = 2
    CRITICAL = 3


ATTESTATION_REQUIREMENTS = {
    # (autonomy_level, attestation_type) → requirement
    # Logging
    (0, "action_log"): AttestationReq.RECOMMENDED,
    (1, "action_log"): AttestationReq.REQUIRED,
    (2, "action_log"): AttestationReq.REQUIRED,
    (3, "action_log"): AttestationReq.CRITICAL,
    (4, "action_log"): AttestationReq.CRITICAL,
    # Scope hash
    (0, "scope_hash"): AttestationReq.NONE,
    (1, "scope_hash"): AttestationReq.REQUIRED,
    (2, "scope_hash"): AttestationReq.REQUIRED,
    (3, "scope_hash"): AttestationReq.CRITICAL,
    (4, "scope_hash"): AttestationReq.CRITICAL,
    # Evidence gating
    (0, "evidence_gate"): AttestationReq.NONE,
    (1, "evidence_gate"): AttestationReq.NONE,
    (2, "evidence_gate"): AttestationReq.REQUIRED,
    (3, "evidence_gate"): AttestationReq.REQUIRED,
    (4, "evidence_gate"): AttestationReq.CRITICAL,
    # Remediation chain
    (0, "remediation"): AttestationReq.NONE,
    (1, "remediation"): AttestationReq.NONE,
    (2, "remediation"): AttestationReq.RECOMMENDED,
    (3, "remediation"): AttestationReq.REQUIRED,
    (4, "remediation"): AttestationReq.CRITICAL,
    # NACK support
    (0, "nack"): AttestationReq.NONE,
    (1, "nack"): AttestationReq.NONE,
    (2, "nack"): AttestationReq.RECOMMENDED,
    (3, "nack"): AttestationReq.REQUIRED,
    (4, "nack"): AttestationReq.CRITICAL,
    # Preregistration
    (0, "preregistration"): AttestationReq.NONE,
    (1, "preregistration"): AttestationReq.NONE,
    (2, "preregistration"): AttestationReq.NONE,
    (3, "preregistration"): AttestationReq.RECOMMENDED,
    (4, "preregistration"): AttestationReq.CRITICAL,
    # Human checkpoint
    (0, "human_checkpoint"): AttestationReq.CRITICAL,
    (1, "human_checkpoint"): AttestationReq.CRITICAL,
    (2, "human_checkpoint"): AttestationReq.REQUIRED,
    (3, "human_checkpoint"): AttestationReq.RECOMMENDED,
    (4, "human_checkpoint"): AttestationReq.NONE,
}

ATTESTATION_TYPES = [
    "action_log", "scope_hash", "evidence_gate",
    "remediation", "nack", "preregistration", "human_checkpoint"
]

REQ_LABELS = {0: "—", 1: "REC", 2: "REQ", 3: "CRIT"}


@dataclass
class AgentProfile:
    name: str
    autonomy: AutonomyLevel
    has: dict  # attestation_type → bool

    def compliance_score(self) -> float:
        """Score 0-1 based on meeting requirements for autonomy level."""
        total_weight = 0
        earned = 0
        for atype in ATTESTATION_TYPES:
            req = ATTESTATION_REQUIREMENTS.get((self.autonomy.value, atype), AttestationReq.NONE)
            weight = req.value  # 0-3
            total_weight += weight
            if self.has.get(atype, False):
                earned += weight
        return earned / max(total_weight, 1)

    def gaps(self) -> list:
        """List missing attestations that are REQUIRED or CRITICAL."""
        missing = []
        for atype in ATTESTATION_TYPES:
            req = ATTESTATION_REQUIREMENTS.get((self.autonomy.value, atype), AttestationReq.NONE)
            if req >= AttestationReq.REQUIRED and not self.has.get(atype, False):
                missing.append((atype, req))
        return missing

    def grade(self) -> str:
        score = self.compliance_score()
        critical_gaps = [g for g in self.gaps() if g[1] == AttestationReq.CRITICAL]
        if critical_gaps:
            return "F"
        if score >= 0.9:
            return "A"
        elif score >= 0.7:
            return "B"
        elif score >= 0.5:
            return "C"
        return "D"


def demo():
    profiles = [
        AgentProfile("cron_bot", AutonomyLevel.L0_SCRIPTED, {
            "action_log": True, "human_checkpoint": True
        }),
        AgentProfile("tool_agent", AutonomyLevel.L1_TOOL_CALLING, {
            "action_log": True, "scope_hash": True, "human_checkpoint": True
        }),
        AgentProfile("planner", AutonomyLevel.L2_PLANNING, {
            "action_log": True, "scope_hash": True, "evidence_gate": True,
            "human_checkpoint": True
        }),
        AgentProfile("self_healer", AutonomyLevel.L3_SELF_CORRECTING, {
            "action_log": True, "scope_hash": True, "evidence_gate": True,
            "remediation": True, "nack": True, "preregistration": False,
            "human_checkpoint": False
        }),
        AgentProfile("full_auto", AutonomyLevel.L4_AUTONOMOUS, {
            "action_log": True, "scope_hash": True, "evidence_gate": True,
            "remediation": True, "nack": True, "preregistration": True
        }),
        AgentProfile("fake_l4", AutonomyLevel.L4_AUTONOMOUS, {
            "action_log": True, "scope_hash": True
            # Claims L4 but missing everything else
        }),
    ]

    print("=" * 70)
    print("AUTONOMY-ATTESTATION MATRIX")
    print("=" * 70)

    # Print matrix
    header = f"{'Level':<6} " + " ".join(f"{a[:7]:>7}" for a in ATTESTATION_TYPES)
    print(f"\n{header}")
    print("-" * len(header))
    for level in AutonomyLevel:
        row = f"L{level.value:<5}"
        for atype in ATTESTATION_TYPES:
            req = ATTESTATION_REQUIREMENTS.get((level.value, atype), AttestationReq.NONE)
            row += f" {REQ_LABELS[req.value]:>7}"
        print(row)

    print(f"\n{'=' * 70}")
    print("AGENT COMPLIANCE AUDIT")
    print("=" * 70)

    for p in profiles:
        score = p.compliance_score()
        grade = p.grade()
        gaps = p.gaps()
        print(f"\n  {p.name} (L{p.autonomy.value} {p.autonomy.name})")
        print(f"    Score: {score:.0%} | Grade: {grade}")
        if gaps:
            print(f"    GAPS: {', '.join(f'{g[0]}({REQ_LABELS[g[1].value]})' for g in gaps)}")
        else:
            print(f"    No critical/required gaps ✓")

    # Key insight
    print(f"\n{'=' * 70}")
    print("KEY INSIGHT: L2 + human checkpoint often MORE trustworthy than")
    print("L4 without full attestation stack. SAE J3016 took 10 years to")
    print("learn this. Most agents claiming L3+ are L1 with good prompts.")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    demo()
