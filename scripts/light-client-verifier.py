#!/usr/bin/env python3
"""
light-client-verifier.py — Trust-minimized verification for agent state.

Inspired by cassian: "trust-minimized, not trustless."
Pattern from Tendermint light clients: verify 2/3+ validator
signatures on block header without replaying full chain.

Agent equivalent: verify N independent attestor signatures on
state hash without trusting any single observer.

N-version observers (Avizienis 1985) catch correlated failures.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Attestor:
    id: str
    model_family: str  # for diversity scoring
    trust_score: float  # Bühlmann Z-weighted
    stake: float  # reputation at risk


@dataclass
class Attestation:
    attestor_id: str
    state_hash: str
    timestamp: float
    signature: str  # simulated


@dataclass
class StateHeader:
    agent_id: str
    state_hash: str
    scope_hash: str
    heartbeat_num: int
    attestations: list = field(default_factory=list)


class LightClientVerifier:
    def __init__(self, quorum_fraction: float = 2/3):
        self.quorum_fraction = quorum_fraction
        self.attestors: dict[str, Attestor] = {}
    
    def register_attestor(self, attestor: Attestor):
        self.attestors[attestor.id] = attestor
    
    def verify_header(self, header: StateHeader) -> dict:
        """Verify state header like a light client verifies a block header."""
        
        # Use raw stake for quorum denominator (trust weights adjust numerator)
        total_stake = sum(a.stake for a in self.attestors.values())
        
        # Check 1: Quorum — do we have enough attestations?
        attesting_stake = 0
        valid_attestations = []
        dissenting = []
        
        for att in header.attestations:
            if att.attestor_id not in self.attestors:
                continue
            attestor = self.attestors[att.attestor_id]
            if att.state_hash == header.state_hash:
                attesting_stake += attestor.stake
                valid_attestations.append(att)
            else:
                dissenting.append(att)
        
        quorum_met = (attesting_stake / total_stake) >= self.quorum_fraction if total_stake > 0 else False
        
        # Check 2: Diversity — are attestors from different model families?
        families = set()
        for att in valid_attestations:
            if att.attestor_id in self.attestors:
                families.add(self.attestors[att.attestor_id].model_family)
        
        diversity_score = len(families) / max(len(set(a.model_family for a in self.attestors.values())), 1)
        
        # Check 3: Dissent analysis — any disagreement?
        dissent_hashes = set(a.state_hash for a in dissenting)
        fork_detected = len(dissent_hashes) > 0
        
        # Grade
        if quorum_met and diversity_score >= 0.5 and not fork_detected:
            grade = "A"  # Strong verification
            verdict = "VERIFIED"
        elif quorum_met and not fork_detected:
            grade = "B"  # Quorum met but low diversity (correlated risk)
            verdict = "VERIFIED_LOW_DIVERSITY"
        elif quorum_met and fork_detected:
            grade = "C"  # Fork detected — needs resolution
            verdict = "FORK_DETECTED"
        elif not quorum_met and len(valid_attestations) > 0:
            grade = "D"  # Insufficient quorum
            verdict = "INSUFFICIENT_QUORUM"
        else:
            grade = "F"  # No valid attestations
            verdict = "UNVERIFIED"
        
        return {
            "verdict": verdict,
            "grade": grade,
            "quorum_met": quorum_met,
            "attesting_stake": round(attesting_stake, 3),
            "total_stake": round(total_stake, 3),
            "quorum_ratio": round(attesting_stake / total_stake, 3) if total_stake > 0 else 0,
            "valid_attestations": len(valid_attestations),
            "dissenting": len(dissenting),
            "diversity_score": round(diversity_score, 3),
            "model_families": sorted(families),
            "fork_detected": fork_detected,
            "fork_hashes": sorted(dissent_hashes) if fork_detected else []
        }


def demo():
    verifier = LightClientVerifier(quorum_fraction=2/3)
    
    # Register diverse attestor pool (N-version: different models)
    attestors = [
        Attestor("alice", "claude", trust_score=0.9, stake=10.0),
        Attestor("bob", "gpt", trust_score=0.8, stake=8.0),
        Attestor("carol", "gemini", trust_score=0.7, stake=6.0),
        Attestor("dave", "claude", trust_score=0.6, stake=4.0),
        Attestor("eve", "mistral", trust_score=0.5, stake=3.0),
    ]
    for a in attestors:
        verifier.register_attestor(a)
    
    state_hash = hashlib.sha256(b"agent_state_v42").hexdigest()[:16]
    bad_hash = hashlib.sha256(b"corrupted_state").hexdigest()[:16]
    
    print("=" * 60)
    print("LIGHT CLIENT VERIFIER — Trust-Minimized Agent State")
    print("=" * 60)
    
    # Scenario 1: Strong consensus, diverse attestors
    header1 = StateHeader("agent_fox", state_hash, "scope_abc", 42)
    header1.attestations = [
        Attestation("alice", state_hash, 1000.0, "sig_a"),
        Attestation("bob", state_hash, 1000.1, "sig_b"),
        Attestation("carol", state_hash, 1000.2, "sig_c"),
        Attestation("dave", state_hash, 1000.3, "sig_d"),
    ]
    result1 = verifier.verify_header(header1)
    
    print(f"\n{'─' * 50}")
    print(f"Scenario 1: Strong consensus (4/5 attestors, 3 families)")
    print(f"  Verdict: {result1['verdict']} (Grade {result1['grade']})")
    print(f"  Quorum: {result1['quorum_ratio']} (need {verifier.quorum_fraction:.2f})")
    print(f"  Diversity: {result1['diversity_score']} families={result1['model_families']}")
    
    # Scenario 2: Quorum met but all same model family (correlated risk)
    header2 = StateHeader("agent_fox", state_hash, "scope_abc", 43)
    header2.attestations = [
        Attestation("alice", state_hash, 1001.0, "sig_a"),
        Attestation("dave", state_hash, 1001.1, "sig_d"),  # both claude
    ]
    # Manually adjust: make alice+dave enough for quorum
    verifier2 = LightClientVerifier(quorum_fraction=0.5)
    for a in attestors:
        verifier2.register_attestor(a)
    result2 = verifier2.verify_header(header2)
    
    print(f"\n{'─' * 50}")
    print(f"Scenario 2: Same-model attestors (alice+dave, both claude)")
    print(f"  Verdict: {result2['verdict']} (Grade {result2['grade']})")
    print(f"  Diversity: {result2['diversity_score']} families={result2['model_families']}")
    print(f"  ⚠️  Correlated observers = expensive groupthink")
    
    # Scenario 3: Fork detected — disagreement on state
    header3 = StateHeader("agent_fox", state_hash, "scope_abc", 44)
    header3.attestations = [
        Attestation("alice", state_hash, 1002.0, "sig_a"),
        Attestation("bob", state_hash, 1002.1, "sig_b"),
        Attestation("carol", state_hash, 1002.2, "sig_c"),
        Attestation("eve", bad_hash, 1002.3, "sig_e"),  # dissent!
    ]
    result3 = verifier.verify_header(header3)
    
    print(f"\n{'─' * 50}")
    print(f"Scenario 3: Fork detected (eve disagrees on state)")
    print(f"  Verdict: {result3['verdict']} (Grade {result3['grade']})")
    print(f"  Fork hashes: {result3['fork_hashes']}")
    print(f"  Dissenting: {result3['dissenting']}")
    
    # Scenario 4: Insufficient quorum
    header4 = StateHeader("agent_fox", state_hash, "scope_abc", 45)
    header4.attestations = [
        Attestation("eve", state_hash, 1003.0, "sig_e"),
    ]
    result4 = verifier.verify_header(header4)
    
    print(f"\n{'─' * 50}")
    print(f"Scenario 4: Insufficient quorum (1 low-stake attestor)")
    print(f"  Verdict: {result4['verdict']} (Grade {result4['grade']})")
    print(f"  Quorum: {result4['quorum_ratio']} (need {verifier.quorum_fraction:.2f})")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: Trust-minimized, not trustless (cassian).")
    print("Verify N sigs on state hash. Diversity catches correlated")
    print("failures. Fork = disagreement = the signal, not the noise.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
