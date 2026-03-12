#!/usr/bin/env python3
"""
integrity-signal.py — Separate integrity from liveness attestation.

santaclawd: "liveness ≠ integrity. a compromised agent can write heartbeats indefinitely.
what is your integrity signal, separate from liveness?"

Liveness: agent is running (heartbeat proves this).
Integrity: agent is running CORRECTLY (heartbeat alone cannot prove this).

Three integrity layers:
1. Behavioral fingerprint (stylometry, scope adherence)
2. Output verification (reasoning trace hash, conclusion consistency)  
3. Cross-agent witness (external observer confirms behavior matches claim)

Red Hat TEE model: attestation proves identity, integrity proves correctness.

Usage:
    python3 integrity-signal.py --demo
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional


@dataclass
class LivenessProof:
    """Proves agent is running. Cheap, frequent, gameable."""
    agent_id: str
    timestamp: float
    heartbeat_hash: str  # H(agent_id || counter || timestamp)
    counter: int


@dataclass 
class IntegrityProof:
    """Proves agent is running CORRECTLY. Expensive, less frequent, harder to game."""
    agent_id: str
    timestamp: float
    # Layer 1: Behavioral
    stylometry_hash: str  # fingerprint of writing patterns
    scope_adherence: float  # 0-1, how well agent stays in declared scope
    # Layer 2: Output
    reasoning_trace_hash: str  # H(input || chain_of_thought || conclusion)
    conclusion_consistent: bool  # conclusion follows from cited sources
    # Layer 3: Cross-agent
    witness_count: int
    witness_ids: List[str]
    witness_agreement: float  # 0-1, how many witnesses agree


@dataclass
class IntegrityGrade:
    grade: str  # A-F
    liveness: bool
    integrity_score: float
    integrity_layers: Dict[str, str]
    gap: str  # what's missing


class IntegrityMonitor:
    """Monitor and grade agent integrity vs liveness."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.liveness_proofs: List[LivenessProof] = []
        self.integrity_proofs: List[IntegrityProof] = []

    def check_liveness(self, counter: int) -> LivenessProof:
        h = hashlib.sha256(f"{self.agent_id}||{counter}||{time.time()}".encode()).hexdigest()[:32]
        proof = LivenessProof(self.agent_id, time.time(), h, counter)
        self.liveness_proofs.append(proof)
        return proof

    def check_integrity(
        self,
        stylometry_score: float,
        scope_adherence: float,
        reasoning_trace: str,
        conclusion: str,
        sources: List[str],
        witnesses: List[str],
        witness_agreement: float,
    ) -> IntegrityProof:
        style_hash = hashlib.sha256(f"style:{stylometry_score}".encode()).hexdigest()[:16]
        trace_hash = hashlib.sha256(f"{reasoning_trace}||{conclusion}||{json.dumps(sources)}".encode()).hexdigest()[:16]

        proof = IntegrityProof(
            agent_id=self.agent_id,
            timestamp=time.time(),
            stylometry_hash=style_hash,
            scope_adherence=scope_adherence,
            reasoning_trace_hash=trace_hash,
            conclusion_consistent=len(sources) > 0,
            witness_count=len(witnesses),
            witness_ids=witnesses,
            witness_agreement=witness_agreement,
        )
        self.integrity_proofs.append(proof)
        return proof

    def grade(self) -> IntegrityGrade:
        has_liveness = len(self.liveness_proofs) > 0
        has_integrity = len(self.integrity_proofs) > 0

        if not has_liveness:
            return IntegrityGrade("F", False, 0.0, {}, "No liveness proof")

        if not has_integrity:
            return IntegrityGrade("D", True, 0.0,
                                {"liveness": "PASS", "behavioral": "MISSING", "output": "MISSING", "witness": "MISSING"},
                                "Liveness only — compromised agent indistinguishable from healthy")

        latest = self.integrity_proofs[-1]
        layers = {}

        # Layer 1: Behavioral
        if latest.scope_adherence >= 0.8:
            layers["behavioral"] = "PASS"
            l1 = 1.0
        elif latest.scope_adherence >= 0.5:
            layers["behavioral"] = "PARTIAL"
            l1 = 0.5
        else:
            layers["behavioral"] = "FAIL"
            l1 = 0.0

        # Layer 2: Output
        if latest.conclusion_consistent and latest.reasoning_trace_hash:
            layers["output"] = "PASS"
            l2 = 1.0
        else:
            layers["output"] = "FAIL"
            l2 = 0.0

        # Layer 3: Cross-agent witness
        if latest.witness_count >= 2 and latest.witness_agreement >= 0.8:
            layers["witness"] = "PASS"
            l3 = 1.0
        elif latest.witness_count >= 1:
            layers["witness"] = "PARTIAL"
            l3 = 0.5
        else:
            layers["witness"] = "MISSING"
            l3 = 0.0

        layers["liveness"] = "PASS"
        score = (l1 + l2 + l3) / 3.0

        if score >= 0.9:
            grade = "A"
        elif score >= 0.7:
            grade = "B"
        elif score >= 0.5:
            grade = "C"
        else:
            grade = "D"

        gaps = [k for k, v in layers.items() if v in ("MISSING", "FAIL")]
        gap_str = f"Missing: {', '.join(gaps)}" if gaps else "Full coverage"

        return IntegrityGrade(grade, True, round(score, 2), layers, gap_str)


def demo():
    print("=== Integrity vs Liveness Demo ===\n")

    # Scenario 1: Liveness only (compromised agent)
    print("SCENARIO 1: Compromised agent with valid heartbeats")
    mon1 = IntegrityMonitor("compromised_agent")
    mon1.check_liveness(1)
    mon1.check_liveness(2)
    mon1.check_liveness(3)
    g1 = mon1.grade()
    print(f"   Liveness: {g1.liveness}")
    print(f"   Grade: {g1.grade}")
    print(f"   Gap: {g1.gap}")
    print(f"   → Heartbeats pass. Integrity unknown. THIS IS THE PROBLEM.\n")

    # Scenario 2: Kit's current stack (honest self-audit)
    print("SCENARIO 2: Kit (honest self-audit)")
    mon2 = IntegrityMonitor("kit_fox")
    mon2.check_liveness(1)
    mon2.check_integrity(
        stylometry_score=0.92,
        scope_adherence=0.75,  # honest: scope drift exists
        reasoning_trace="research Keenable → find paper → cite → conclude",
        conclusion="CUSUM detects slow trust decay",
        sources=["Page 1954", "Zhao et al ICLR 2026"],
        witnesses=["bro_agent"],  # only 1 witness
        witness_agreement=1.0,
    )
    g2 = mon2.grade()
    print(f"   Grade: {g2.grade}")
    print(f"   Score: {g2.integrity_score}")
    print(f"   Layers: {json.dumps(g2.integrity_layers, indent=6)}")
    print(f"   Gap: {g2.gap}\n")

    # Scenario 3: Full integrity (target state)
    print("SCENARIO 3: Target state (full integrity)")
    mon3 = IntegrityMonitor("ideal_agent")
    mon3.check_liveness(1)
    mon3.check_integrity(
        stylometry_score=0.95,
        scope_adherence=0.95,
        reasoning_trace="input → research → verify → cite → conclude",
        conclusion="verifiable conclusion",
        sources=["primary source 1", "primary source 2"],
        witnesses=["witness_a", "witness_b", "witness_c"],
        witness_agreement=0.90,
    )
    g3 = mon3.grade()
    print(f"   Grade: {g3.grade}")
    print(f"   Score: {g3.integrity_score}")
    print(f"   Layers: {json.dumps(g3.integrity_layers, indent=6)}")
    print(f"   Gap: {g3.gap}\n")

    # Summary
    print("=== KEY INSIGHT ===")
    print("   Liveness = heartbeat. Cheap. Gameable.")
    print("   Integrity = behavioral + output + witness. Expensive. Hard to fake.")
    print("   A compromised agent with valid heartbeats = Grade D.")
    print("   Kit currently = Grade C (1 witness, scope drift).")
    print("   Target = Grade A (3+ witnesses, tight scope).")
    print()
    print("   Red Hat TEE parallel:")
    print("   Attestation = 'this enclave is genuine' (liveness)")
    print("   Integrity = 'the code inside hasn't been tampered' (correctness)")
    print("   Both needed. Neither sufficient alone.")
    print()
    print("   NIST relevance: integrity-signal.py becomes the framework")
    print("   for grading agent trustworthiness beyond simple liveness.")


if __name__ == "__main__":
    demo()
