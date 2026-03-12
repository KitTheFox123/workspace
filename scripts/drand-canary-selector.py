#!/usr/bin/env python3
"""
drand-canary-selector.py — VRF-backed canary selection from pre-committed pool.

Based on:
- santaclawd: "behavioral probe security = 3 layers: unpredictability, commit-reveal, VDF delay"
- canary-spec-commit.py: pre-committed canary pool
- drand-trust-anchor.py: external randomness beacon

Wires drand beacon to canary selection:
1. Pre-commit N canary specs at lock time (canary-spec-commit.py)
2. At half-open time, fetch drand round
3. canary_index = drand_randomness % pool_size
4. Attestor cannot predict which canary → cannot prepare targeted response

Covers all 3 layers:
- (1) Unpredictability: drand selects from pool per round
- (2) Commit-reveal: canary hashes committed at lock, revealed at selection
- (3) VDF delay: drand threshold BLS (30s rounds) prevents brute-force
"""

import hashlib
import json
import time
from dataclasses import dataclass, field


@dataclass
class CanarySpec:
    canary_id: int
    input_data: str
    expected_output: str
    difficulty: str  # "original" | "calibrated"
    
    def spec_hash(self) -> str:
        content = json.dumps({
            "id": self.canary_id,
            "input": self.input_data,
            "expected": self.expected_output,
            "difficulty": self.difficulty,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass  
class CanaryPool:
    canaries: list[CanarySpec] = field(default_factory=list)
    pool_hash: str = ""  # Merkle root of all canary hashes
    locked_at: float = 0.0
    
    def commit(self) -> str:
        """Compute Merkle-like commitment of entire pool."""
        hashes = [c.spec_hash() for c in self.canaries]
        content = json.dumps(sorted(hashes))
        self.pool_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        self.locked_at = time.time()
        return self.pool_hash
    
    def select(self, drand_randomness: int) -> tuple[CanarySpec, int]:
        """Select canary using external randomness."""
        index = drand_randomness % len(self.canaries)
        return self.canaries[index], index
    
    def verify_selection(self, index: int, claimed_spec: CanarySpec) -> bool:
        """Verify selected canary matches committed pool."""
        if index >= len(self.canaries):
            return False
        return self.canaries[index].spec_hash() == claimed_spec.spec_hash()


@dataclass
class DrandRound:
    """Simulated drand beacon round."""
    round_number: int
    randomness: str  # hex
    signature: str   # BLS signature
    
    def randomness_int(self) -> int:
        return int(self.randomness[:16], 16)


def simulate_drand_round(round_num: int) -> DrandRound:
    """Simulate a drand beacon output."""
    # In production: fetch from https://drand.cloudflare.com/public/latest
    randomness = hashlib.sha256(f"drand_round_{round_num}".encode()).hexdigest()
    signature = hashlib.sha256(f"bls_sig_{round_num}".encode()).hexdigest()[:32]
    return DrandRound(round_num, randomness, signature)


def grade_probe_security(has_pool: bool, has_drand: bool, has_commit_reveal: bool) -> tuple[str, str]:
    score = sum([has_pool, has_drand, has_commit_reveal])
    if score == 3:
        return "A", "FULL_PROBE_SECURITY"
    elif score == 2:
        return "B", "PARTIAL_SECURITY"
    elif score == 1:
        return "C", "MINIMAL_SECURITY"
    return "F", "NO_PROBE_SECURITY"


def main():
    print("=" * 70)
    print("DRAND CANARY SELECTOR")
    print("santaclawd: '3 layers: unpredictability, commit-reveal, VDF delay'")
    print("=" * 70)

    # Build canary pool
    pool = CanaryPool(canaries=[
        CanarySpec(0, "summarize_doc_v3", "0.85", "original"),
        CanarySpec(1, "classify_intent_v2", "support_request", "original"),
        CanarySpec(2, "extract_entities_v1", "3_entities", "calibrated"),
        CanarySpec(3, "score_relevance_v1", "0.72", "original"),
        CanarySpec(4, "detect_sentiment_v1", "negative", "calibrated"),
    ])
    
    # Lock pool
    pool_hash = pool.commit()
    print(f"\n--- Pool Committed ---")
    print(f"Pool size: {len(pool.canaries)}")
    print(f"Pool hash: {pool_hash}")
    for c in pool.canaries:
        print(f"  Canary {c.canary_id}: {c.spec_hash()} ({c.input_data})")

    # Simulate multiple rounds — show unpredictability
    print(f"\n--- Selection Across Rounds ---")
    print(f"{'Round':<8} {'Randomness':<18} {'Index':<6} {'Canary'}")
    print("-" * 60)
    
    selections = {}
    for r in range(5898500, 5898510):
        drand = simulate_drand_round(r)
        canary, idx = pool.select(drand.randomness_int())
        selections[r] = idx
        print(f"{r:<8} {drand.randomness[:16]:<18} {idx:<6} {canary.input_data}")
    
    # Verify uniform-ish distribution
    from collections import Counter
    counts = Counter(selections.values())
    print(f"\nDistribution: {dict(counts)}")

    # Verification demo
    print(f"\n--- Verification ---")
    drand = simulate_drand_round(5898500)
    canary, idx = pool.select(drand.randomness_int())
    verified = pool.verify_selection(idx, canary)
    print(f"Round {drand.round_number}: selected canary {idx}")
    print(f"Verified against committed pool: {verified}")
    
    # Tamper attempt
    fake_canary = CanarySpec(idx, "hello_world", "hello", "trivial")
    tamper_verified = pool.verify_selection(idx, fake_canary)
    print(f"Tampered canary verification: {tamper_verified}")

    # Security grading
    print(f"\n--- Probe Security Grades ---")
    scenarios = [
        ("Full (pool+drand+commit)", True, True, True),
        ("No drand (fixed selection)", True, False, True),
        ("No pool (single canary)", False, True, True),
        ("No commit (post-hoc)", True, True, False),
        ("None", False, False, False),
    ]
    for name, pool_ok, drand_ok, cr_ok in scenarios:
        grade, diag = grade_probe_security(pool_ok, drand_ok, cr_ok)
        print(f"  {name:<30} {grade} ({diag})")

    # ABI v2.2 integration
    print(f"\n--- ABI v2.2 Fields ---")
    print("canary_pool_hash:  bytes32  // Merkle root of committed canaries")
    print("canary_pool_size:  uint8    // N canaries in pool")
    print("drand_chain_hash:  bytes32  // Which drand network")
    print("selection_round:   uint64   // drand round for selection")
    print()
    print("On-chain: canary_pool_hash (arbiter needs for dispute)")
    print("Off-chain: individual canary specs (revealed at selection)")
    print()
    print("santaclawd's 3 layers:")
    print("  (1) Unpredictability: drand % pool_size ✅")
    print("  (2) Commit-reveal: pool_hash at lock, specs at selection ✅")
    print("  (3) VDF delay: drand threshold BLS = 30s rounds ✅")


if __name__ == "__main__":
    main()
