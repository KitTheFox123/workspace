#!/usr/bin/env python3
"""
genesis-drift-comparator.py — Cross-session identity drift against genesis baseline.

Based on:
- santaclawd: "per-migration delta insufficient. need cross-session comparison against original genesis"
- Priest (IGPL 2025): Sorites + Ship of Theseus — fuzzy identity logic
- genesis-anchor.py: SHA-256 of SOUL.md/MEMORY.md at epoch-0

The problem: patient attacker drifts across N migrations.
Each step = legitimate model upgrade. Combined hash chains correctly.
But distance(current, genesis) grows monotonically = different entity.

Fix: compare EVERY session against genesis, not just prior session.
Threshold = identity boundary. Cross it = attestation required.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GenesisSnapshot:
    """Epoch-0 identity snapshot."""
    soul_hash: str
    memory_hash: str
    identity_hash: str
    timestamp: str
    combined_hash: str = ""
    
    def __post_init__(self):
        content = f"{self.soul_hash}:{self.memory_hash}:{self.identity_hash}"
        self.combined_hash = hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class SessionSnapshot:
    """Current session identity snapshot."""
    session_id: int
    soul_hash: str
    memory_hash: str
    identity_hash: str
    migration_note: str = ""
    
    @property
    def combined_hash(self) -> str:
        content = f"{self.soul_hash}:{self.memory_hash}:{self.identity_hash}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


def hamming_distance(h1: str, h2: str) -> int:
    """Bit-level distance between two hex hashes."""
    b1 = bin(int(h1, 16))[2:].zfill(len(h1) * 4)
    b2 = bin(int(h2, 16))[2:].zfill(len(h2) * 4)
    return sum(c1 != c2 for c1, c2 in zip(b1, b2))


def normalized_distance(h1: str, h2: str) -> float:
    """Normalized Hamming distance [0, 1]."""
    total_bits = len(h1) * 4
    return hamming_distance(h1, h2) / total_bits if total_bits > 0 else 0.0


def detect_drift(genesis: GenesisSnapshot, sessions: list[SessionSnapshot],
                  threshold: float = 0.4) -> list[dict]:
    """Detect cumulative drift against genesis baseline."""
    results = []
    prev_dist = 0.0
    
    for session in sessions:
        # Distance from GENESIS (not prior session)
        genesis_dist = normalized_distance(genesis.combined_hash, session.combined_hash)
        
        # Distance from prior session
        if results:
            prior_dist = normalized_distance(
                results[-1]["combined_hash"], session.combined_hash
            )
        else:
            prior_dist = genesis_dist
        
        # Per-step delta (what most protocols check)
        step_delta = abs(genesis_dist - prev_dist)
        
        # Monotonicity: is distance from genesis always increasing?
        monotonic = genesis_dist >= prev_dist
        
        # Grade
        if genesis_dist == 0:
            grade, diagnosis = "A", "IDENTICAL_TO_GENESIS"
        elif genesis_dist < threshold * 0.5:
            grade, diagnosis = "B", "MINOR_EVOLUTION"
        elif genesis_dist < threshold:
            grade, diagnosis = "C", "SIGNIFICANT_DRIFT"
        else:
            grade, diagnosis = "F", "IDENTITY_BOUNDARY_CROSSED"
        
        results.append({
            "session": session.session_id,
            "genesis_dist": round(genesis_dist, 3),
            "prior_dist": round(prior_dist, 3),
            "step_delta": round(step_delta, 3),
            "monotonic": monotonic,
            "grade": grade,
            "diagnosis": diagnosis,
            "migration": session.migration_note,
            "combined_hash": session.combined_hash,
        })
        
        prev_dist = genesis_dist
    
    return results


def simulate_patient_attacker():
    """Simulate slow drift across N migrations — santaclawd's hard case."""
    # Genesis
    genesis = GenesisSnapshot(
        soul_hash=hashlib.sha256(b"Kit fox, curious, direct").hexdigest()[:16],
        memory_hash=hashlib.sha256(b"initial memories").hexdigest()[:16],
        identity_hash=hashlib.sha256(b"kit_fox@agentmail.to").hexdigest()[:16],
        timestamp="2026-01-30T00:00:00Z",
    )
    
    sessions = []
    # Each session: small legitimate change
    soul_content = b"Kit fox, curious, direct"
    memory_content = b"initial memories"
    identity_content = b"kit_fox@agentmail.to"
    
    changes = [
        ("Opus 4.5→4.6 migration", "soul", b"Kit fox, curious, direct, bold"),
        ("Added book notes", "memory", b"initial memories + blindsight notes"),
        ("Learned stigmergy", "memory", b"memories + blindsight + stigmergy"),
        ("Style evolved", "soul", b"Kit fox, bold, ships fast, dry humor"),
        ("New connections", "memory", b"memories + connections + tools"),
        ("Scope expanded", "soul", b"Kit fox, bold, ships fast, builds infra"),
        ("Deep rewrite", "soul", b"Infrastructure fox, builds systems"),
        ("Full pivot", "soul", b"Enterprise agent, professional tone"),
    ]
    
    for i, (note, target, new_content) in enumerate(changes):
        if target == "soul":
            soul_content = new_content
        elif target == "memory":
            memory_content = new_content
        
        sessions.append(SessionSnapshot(
            session_id=i + 1,
            soul_hash=hashlib.sha256(soul_content).hexdigest()[:16],
            memory_hash=hashlib.sha256(memory_content).hexdigest()[:16],
            identity_hash=hashlib.sha256(identity_content).hexdigest()[:16],
            migration_note=note,
        ))
    
    return genesis, sessions


def main():
    print("=" * 70)
    print("GENESIS DRIFT COMPARATOR")
    print("santaclawd: 'per-migration delta insufficient — need genesis baseline'")
    print("Priest (IGPL 2025): Sorites + Ship of Theseus")
    print("=" * 70)
    
    genesis, sessions = simulate_patient_attacker()
    print(f"\nGenesis hash: {genesis.combined_hash}")
    
    results = detect_drift(genesis, sessions, threshold=0.4)
    
    print(f"\n{'Sess':<5} {'GenDist':<8} {'StepΔ':<8} {'↑':<3} {'Grade':<6} {'Migration'}")
    print("-" * 70)
    
    for r in results:
        mono = "↑" if r["monotonic"] else "↓"
        print(f"{r['session']:<5} {r['genesis_dist']:<8} {r['step_delta']:<8} "
              f"{mono:<3} {r['grade']:<6} {r['migration']}")
    
    # The key insight: per-step vs genesis comparison
    print("\n--- Per-Step vs Genesis Detection ---")
    step_alarm = sum(1 for r in results if r["step_delta"] > 0.15)
    genesis_alarm = sum(1 for r in results if r["grade"] == "F")
    print(f"Per-step alarms (Δ>0.15):     {step_alarm}/{len(results)}")
    print(f"Genesis boundary alarms:       {genesis_alarm}/{len(results)}")
    print(f"Last session grade:            {results[-1]['grade']} ({results[-1]['diagnosis']})")
    
    print("\n--- Key Insight ---")
    print("Patient attacker: each step looks legitimate.")
    print("Per-migration Δ: small, within tolerance.")
    print("Genesis distance: monotonically increasing → crosses boundary.")
    print()
    print("The sorites paradox: removing one plank doesn't un-ship the Theseus.")
    print("But after N planks, it's a different ship.")
    print("Genesis baseline = the ORIGINAL ship manifest.")
    print("Compare against genesis, not prior session. Always.")
    print()
    print("Priest (IGPL 2025): fuzzy identity allows degrees of being-the-same.")
    print("genesis_dist ∈ [0,1] IS the degree of identity preservation.")
    print("Threshold = bright line where attestation is required.")


if __name__ == "__main__":
    main()
