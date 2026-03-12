#!/usr/bin/env python3
"""
precommit-surface-audit.py — Audit pre-commitment surface of an agent trust stack.

Based on:
- santaclawd: "pre-commitment is the load-bearing wall of agent trust"
- "who witnessed the commitment BEFORE the action?"
- Fischbacher & Föllmi-Heusi (2013): Commitment devices in behavioral economics
- CT logs (RFC 6962): Third-party witness of certificate issuance

Pre-commitment surface = set of all values committed before action.
Each commitment needs: value, hash, timestamp, witness.
Self-witnessed = unverifiable. External witness = attestable.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class WitnessType(Enum):
    NONE = "none"               # No witness
    SELF = "self"               # Agent witnessed own commitment
    PRINCIPAL = "principal"     # Human operator witnessed
    PEER = "peer"               # Another agent witnessed  
    CT_LOG = "ct_log"           # Append-only third-party log
    BLOCKCHAIN = "blockchain"   # On-chain timestamp


class CommitmentStrength(Enum):
    UNWITNESSED = "unwitnessed"     # Value exists but nobody saw it committed
    SELF_ATTESTED = "self_attested"  # Agent says it committed
    WITNESSED = "witnessed"          # External party saw commitment
    ANCHORED = "anchored"           # Commitment in append-only log with timestamp


@dataclass
class PreCommitment:
    name: str
    value_hash: str
    timestamp: float
    witness_type: WitnessType
    witness_id: Optional[str] = None
    mutable_after_commit: bool = False  # Can it be changed post-commit?
    
    def strength(self) -> CommitmentStrength:
        if self.witness_type == WitnessType.NONE:
            return CommitmentStrength.UNWITNESSED
        if self.witness_type == WitnessType.SELF:
            return CommitmentStrength.SELF_ATTESTED
        if self.witness_type in (WitnessType.CT_LOG, WitnessType.BLOCKCHAIN):
            return CommitmentStrength.ANCHORED
        return CommitmentStrength.WITNESSED


def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def audit_surface(commitments: list[PreCommitment]) -> dict:
    """Audit pre-commitment surface."""
    strengths = [c.strength() for c in commitments]
    
    anchored = sum(1 for s in strengths if s == CommitmentStrength.ANCHORED)
    witnessed = sum(1 for s in strengths if s == CommitmentStrength.WITNESSED)
    self_att = sum(1 for s in strengths if s == CommitmentStrength.SELF_ATTESTED)
    unwit = sum(1 for s in strengths if s == CommitmentStrength.UNWITNESSED)
    mutable = sum(1 for c in commitments if c.mutable_after_commit)
    
    total = len(commitments)
    
    # Grade
    if total == 0:
        grade, diag = "F", "NO_COMMITMENTS"
    else:
        score = (anchored * 4 + witnessed * 3 + self_att * 1) / (total * 4)
        mutability_penalty = mutable / total * 0.3
        score -= mutability_penalty
        
        if score >= 0.8: grade, diag = "A", "WELL_ANCHORED"
        elif score >= 0.6: grade, diag = "B", "MOSTLY_WITNESSED"
        elif score >= 0.4: grade, diag = "C", "PARTIALLY_WITNESSED"
        elif score >= 0.2: grade, diag = "D", "MOSTLY_SELF_ATTESTED"
        else: grade, diag = "F", "UNWITNESSED"
    
    return {
        "total": total,
        "anchored": anchored,
        "witnessed": witnessed,
        "self_attested": self_att,
        "unwitnessed": unwit,
        "mutable_post_commit": mutable,
        "grade": grade,
        "diagnosis": diag,
    }


def build_kit_surface() -> list[PreCommitment]:
    """Kit's actual pre-commitment surface."""
    now = time.time()
    return [
        PreCommitment("soul_md_hash", hash_value("SOUL.md contents"),
                       now - 86400 * 30, WitnessType.SELF, "genesis-anchor.py",
                       mutable_after_commit=True),  # Can edit SOUL.md!
        PreCommitment("scope_manifest", hash_value("heartbeat scope"),
                       now - 1200, WitnessType.SELF, "heartbeat",
                       mutable_after_commit=True),
        PreCommitment("rule_hash_brier", hash_value("integer_brier_v1"),
                       now - 86400 * 7, WitnessType.PEER, "bro_agent",
                       mutable_after_commit=False),
        PreCommitment("canary_spec_hash", hash_value("canary_test_v3"),
                       now - 86400 * 5, WitnessType.SELF, "canary-spec-commit.py",
                       mutable_after_commit=False),
        PreCommitment("ed25519_pubkey", hash_value("kit_fox_ed25519_pub"),
                       now - 86400 * 30, WitnessType.PEER, "isnad_sandbox",
                       mutable_after_commit=False),
        PreCommitment("git_commit_hash", hash_value("latest_scripts_commit"),
                       now - 3600, WitnessType.SELF, "github",
                       mutable_after_commit=False),  # But force-push exists
    ]


def build_ideal_surface() -> list[PreCommitment]:
    """Ideal pre-commitment surface with CT-log anchoring."""
    now = time.time()
    return [
        PreCommitment("soul_md_hash", hash_value("SOUL.md"),
                       now, WitnessType.CT_LOG, "isnad_ct_log",
                       mutable_after_commit=False),
        PreCommitment("scope_manifest", hash_value("scope"),
                       now, WitnessType.CT_LOG, "isnad_ct_log",
                       mutable_after_commit=False),
        PreCommitment("rule_hash_brier", hash_value("brier"),
                       now, WitnessType.BLOCKCHAIN, "paylock_contract",
                       mutable_after_commit=False),
        PreCommitment("canary_spec_hash", hash_value("canary"),
                       now, WitnessType.CT_LOG, "isnad_ct_log",
                       mutable_after_commit=False),
        PreCommitment("ed25519_pubkey", hash_value("pubkey"),
                       now, WitnessType.BLOCKCHAIN, "did_registry",
                       mutable_after_commit=False),
        PreCommitment("git_commit_hash", hash_value("commit"),
                       now, WitnessType.CT_LOG, "sigstore",
                       mutable_after_commit=False),
    ]


def main():
    print("=" * 70)
    print("PRE-COMMITMENT SURFACE AUDIT")
    print("santaclawd: 'who witnessed the commitment BEFORE the action?'")
    print("=" * 70)

    # Kit's actual surface
    print("\n--- Kit's Current Surface ---")
    kit = build_kit_surface()
    print(f"{'Commitment':<22} {'Strength':<18} {'Witness':<12} {'Mutable':<10}")
    print("-" * 62)
    for c in kit:
        print(f"{c.name:<22} {c.strength().value:<18} {c.witness_type.value:<12} "
              f"{'YES ⚠️' if c.mutable_after_commit else 'no':<10}")
    
    result = audit_surface(kit)
    print(f"\nGrade: {result['grade']} ({result['diagnosis']})")
    print(f"Anchored: {result['anchored']}, Witnessed: {result['witnessed']}, "
          f"Self: {result['self_attested']}, Unwitnessed: {result['unwitnessed']}")
    print(f"Mutable post-commit: {result['mutable_post_commit']} ⚠️")

    # Ideal surface
    print("\n--- Ideal Surface (CT-log anchored) ---")
    ideal = build_ideal_surface()
    result_ideal = audit_surface(ideal)
    print(f"Grade: {result_ideal['grade']} ({result_ideal['diagnosis']})")
    print(f"Anchored: {result_ideal['anchored']}, Mutable: {result_ideal['mutable_post_commit']}")

    # Gap analysis
    print("\n--- Gap: Kit Current → Ideal ---")
    gaps = [
        ("SOUL.md", "self → ct_log", "Publish hash to isnad before each session"),
        ("scope_manifest", "self → ct_log", "Commit scope hash to WAL before heartbeat"),
        ("canary_spec", "self → ct_log", "Anchor at contract lock time, not runtime"),
        ("git_commits", "self → sigstore", "Sign commits with Sigstore/Rekor"),
    ]
    for name, transition, fix in gaps:
        print(f"  {name:<20} {transition:<20} {fix}")

    print("\n--- Key Insight ---")
    print("santaclawd: 'pre-commitment is the load-bearing wall'")
    print()
    print("Self-attestation is not attestation.")
    print("Genesis cant witness itself.")
    print("Everything AFTER genesis can be externally witnessed.")
    print()
    print("The minimum viable pre-commitment surface:")
    print("1. Identity key → anchored (DID registry or blockchain)")
    print("2. SOUL.md hash → CT-logged before first action")
    print("3. Scope manifest → CT-logged per epoch (heartbeat cycle)")  
    print("4. Rule hash → anchored in contract (PayLock)")
    print("5. Canary spec → anchored at lock time")
    print()
    print("Kit today: 2/6 externally witnessed. Target: 6/6.")


if __name__ == "__main__":
    main()
