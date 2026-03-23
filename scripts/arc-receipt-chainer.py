#!/usr/bin/env python3
"""
arc-receipt-chainer.py — ARC-style receipt chain preservation for ATF.

Inspired by RFC 8617 (Authenticated Received Chain): each intermediary
in a delegation chain signs the previous authentication results,
preserving trust provenance across hops.

ARC has three headers per hop:
  - ARC-Authentication-Results (AAR) → original auth results
  - ARC-Message-Signature (AMS) → content signature
  - ARC-Seal (AS) → chain integrity seal

ATF equivalent:
  - Receipt-Authentication-Results → original trust scores
  - Receipt-Content-Signature → task deliverable hash
  - Receipt-Chain-Seal → integrity of previous chain

Key insight: DKIM breaks on forwarding because intermediaries modify
headers/body. ARC preserves the ORIGINAL results. ATF receipts need
the same: when Agent A delegates to Agent B who delegates to Agent C,
the original trust assessment must survive the chain.

Usage:
    python3 arc-receipt-chainer.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class ReceiptAuthResults:
    """Equivalent to ARC-Authentication-Results: captures trust state at this hop."""
    instance: int  # ARC-style instance number (1-indexed)
    agent_id: str
    genesis_hash: str
    evidence_grade: str  # A-F
    trust_score: float
    verification_method: str  # HARD_MANDATORY, SOFT_MANDATORY, SELF_ATTESTED
    timestamp: float = field(default_factory=time.time)

    def canonical(self) -> str:
        return f"i={self.instance};agent={self.agent_id};genesis={self.genesis_hash};grade={self.evidence_grade};trust={self.trust_score};method={self.verification_method};t={self.timestamp}"


@dataclass
class ReceiptContentSignature:
    """Equivalent to ARC-Message-Signature: signs the deliverable at this hop."""
    instance: int
    task_hash: str
    deliverable_hash: str
    agent_id: str  # who performed this hop
    timestamp: float = field(default_factory=time.time)

    def canonical(self) -> str:
        return f"i={self.instance};task={self.task_hash};deliverable={self.deliverable_hash};agent={self.agent_id};t={self.timestamp}"


@dataclass
class ReceiptChainSeal:
    """Equivalent to ARC-Seal: cryptographic seal over the chain up to this point."""
    instance: int
    seal_hash: str  # hash of (AAR + AMS + previous seal)
    chain_valid: bool  # cv=pass or cv=fail
    agent_id: str
    timestamp: float = field(default_factory=time.time)

    def canonical(self) -> str:
        cv = "pass" if self.chain_valid else "fail"
        return f"i={self.instance};cv={cv};seal={self.seal_hash};agent={self.agent_id};t={self.timestamp}"


@dataclass
class ChainHop:
    """One hop in the delegation chain (equivalent to one ARC set)."""
    auth_results: ReceiptAuthResults
    content_sig: ReceiptContentSignature
    chain_seal: ReceiptChainSeal


class ARCReceiptChainer:
    """Build and validate ARC-style receipt chains for ATF."""

    def __init__(self):
        self.chain: list[ChainHop] = []

    def _hash(self, *parts: str) -> str:
        combined = "|".join(parts)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def add_hop(
        self,
        agent_id: str,
        genesis_hash: str,
        evidence_grade: str,
        trust_score: float,
        verification_method: str,
        task_hash: str,
        deliverable_hash: str,
    ) -> ChainHop:
        """Add a new hop to the chain (like an intermediary adding ARC headers)."""
        instance = len(self.chain) + 1

        # 1. Authentication Results
        aar = ReceiptAuthResults(
            instance=instance,
            agent_id=agent_id,
            genesis_hash=genesis_hash,
            evidence_grade=evidence_grade,
            trust_score=trust_score,
            verification_method=verification_method,
        )

        # 2. Content Signature
        ams = ReceiptContentSignature(
            instance=instance,
            task_hash=task_hash,
            deliverable_hash=deliverable_hash,
            agent_id=agent_id,
        )

        # 3. Chain Seal (hash of AAR + AMS + previous seal)
        prev_seal = self.chain[-1].chain_seal.canonical() if self.chain else "genesis"
        seal_hash = self._hash(aar.canonical(), ams.canonical(), prev_seal)

        # Chain validity: check previous seal still valid
        chain_valid = self._validate_chain_integrity()

        seal = ReceiptChainSeal(
            instance=instance,
            seal_hash=seal_hash,
            chain_valid=chain_valid,
            agent_id=agent_id,
        )

        hop = ChainHop(auth_results=aar, content_sig=ams, chain_seal=seal)
        self.chain.append(hop)
        return hop

    def _validate_chain_integrity(self) -> bool:
        """Verify the chain hasn't been tampered with (recompute all seals)."""
        for i, hop in enumerate(self.chain):
            expected_prev = self.chain[i - 1].chain_seal.canonical() if i > 0 else "genesis"
            expected_hash = self._hash(
                hop.auth_results.canonical(),
                hop.content_sig.canonical(),
                expected_prev,
            )
            if expected_hash != hop.chain_seal.seal_hash:
                return False
        return True

    def verify_chain(self) -> dict:
        """Full chain verification — equivalent to ARC validation."""
        if not self.chain:
            return {"valid": False, "reason": "empty_chain", "grade": "F"}

        # Check all seals
        integrity = self._validate_chain_integrity()

        # Check for trust degradation across hops
        grades = [hop.auth_results.evidence_grade for hop in self.chain]
        grade_values = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
        grade_nums = [grade_values.get(g, 0) for g in grades]

        # Detect trust inflation (later hop claims higher trust than source)
        trust_inflated = any(
            grade_nums[i] > grade_nums[0] for i in range(1, len(grade_nums))
        )

        # Detect self-attestation in chain
        self_attested = any(
            hop.auth_results.verification_method == "SELF_ATTESTED"
            for hop in self.chain
        )

        # Min trust across chain (like ARC cv=fail propagation)
        min_grade = min(grade_nums)
        chain_grade = {5: "A", 4: "B", 3: "C", 2: "D", 1: "F"}.get(min_grade, "F")

        # Verdict
        issues = []
        if not integrity:
            issues.append("CHAIN_BROKEN")
        if trust_inflated:
            issues.append("TRUST_INFLATED")
        if self_attested:
            issues.append("SELF_ATTESTED_HOP")

        verdict = "VALID" if not issues else "DEGRADED" if integrity else "BROKEN"

        return {
            "valid": integrity and not trust_inflated,
            "verdict": verdict,
            "chain_length": len(self.chain),
            "chain_grade": chain_grade,
            "original_grade": grades[0],
            "final_grade": grades[-1],
            "trust_inflated": trust_inflated,
            "self_attested_hops": self_attested,
            "issues": issues,
            "hops": [
                {
                    "instance": hop.chain_seal.instance,
                    "agent": hop.auth_results.agent_id,
                    "grade": hop.auth_results.evidence_grade,
                    "method": hop.auth_results.verification_method,
                    "seal_valid": hop.chain_seal.chain_valid,
                }
                for hop in self.chain
            ],
        }


def demo():
    print("=" * 60)
    print("ARC Receipt Chainer — RFC 8617 for ATF")
    print("=" * 60)

    # Scenario 1: Clean delegation chain
    print("\n--- Scenario 1: Clean 3-hop delegation ---")
    chainer = ARCReceiptChainer()

    chainer.add_hop(
        agent_id="alice",
        genesis_hash="a1b2c3",
        evidence_grade="A",
        trust_score=0.95,
        verification_method="HARD_MANDATORY",
        task_hash="task001",
        deliverable_hash="del001",
    )
    chainer.add_hop(
        agent_id="bob",
        genesis_hash="d4e5f6",
        evidence_grade="B",
        trust_score=0.82,
        verification_method="HARD_MANDATORY",
        task_hash="task001",
        deliverable_hash="del002",
    )
    chainer.add_hop(
        agent_id="carol",
        genesis_hash="g7h8i9",
        evidence_grade="B",
        trust_score=0.78,
        verification_method="HARD_MANDATORY",
        task_hash="task001",
        deliverable_hash="del003",
    )

    result = chainer.verify_chain()
    print(json.dumps(result, indent=2))

    # Scenario 2: Trust inflation attack
    print("\n--- Scenario 2: Trust inflation (hop 2 claims A, source was B) ---")
    chainer2 = ARCReceiptChainer()

    chainer2.add_hop(
        agent_id="origin",
        genesis_hash="orig01",
        evidence_grade="B",
        trust_score=0.75,
        verification_method="HARD_MANDATORY",
        task_hash="task002",
        deliverable_hash="del010",
    )
    chainer2.add_hop(
        agent_id="inflator",
        genesis_hash="inf001",
        evidence_grade="A",  # Claims higher than source!
        trust_score=0.99,
        verification_method="HARD_MANDATORY",
        task_hash="task002",
        deliverable_hash="del011",
    )

    result2 = chainer2.verify_chain()
    print(json.dumps(result2, indent=2))

    # Scenario 3: Self-attested hop in chain
    print("\n--- Scenario 3: Self-attested hop breaks chain trust ---")
    chainer3 = ARCReceiptChainer()

    chainer3.add_hop(
        agent_id="verified_agent",
        genesis_hash="ver001",
        evidence_grade="A",
        trust_score=0.92,
        verification_method="HARD_MANDATORY",
        task_hash="task003",
        deliverable_hash="del020",
    )
    chainer3.add_hop(
        agent_id="self_attester",
        genesis_hash="self01",
        evidence_grade="A",
        trust_score=0.90,
        verification_method="SELF_ATTESTED",  # Breaks axiom 1
        task_hash="task003",
        deliverable_hash="del021",
    )

    result3 = chainer3.verify_chain()
    print(json.dumps(result3, indent=2))

    # Scenario 4: Long chain with degradation
    print("\n--- Scenario 4: 5-hop chain with natural degradation ---")
    chainer4 = ARCReceiptChainer()
    agents = [
        ("alpha", "A", 0.95, "HARD_MANDATORY"),
        ("beta", "A", 0.90, "HARD_MANDATORY"),
        ("gamma", "B", 0.82, "HARD_MANDATORY"),
        ("delta", "B", 0.78, "SOFT_MANDATORY"),
        ("epsilon", "C", 0.65, "HARD_MANDATORY"),
    ]
    for name, grade, trust, method in agents:
        chainer4.add_hop(
            agent_id=name,
            genesis_hash=f"gen_{name}",
            evidence_grade=grade,
            trust_score=trust,
            verification_method=method,
            task_hash="task004",
            deliverable_hash=f"del_{name}",
        )

    result4 = chainer4.verify_chain()
    print(json.dumps(result4, indent=2))

    print("\n" + "=" * 60)
    print("ARC parallel: each hop preserves original auth results.")
    print("Trust inflation = cv=fail. Self-attestation = axiom 1 violation.")
    print("Chain grade = MIN(all hops). Like ARC: one cv=fail breaks chain.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
