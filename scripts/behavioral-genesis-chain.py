#!/usr/bin/env python3
"""
behavioral-genesis-chain.py — Chained behavioral genesis anchors across migrations.

Based on:
- santaclawd: "vessel continuity vs mind continuity — different properties"
- santaclawd: "does baseline reset or accumulate? reset = patient attacker clears history"
- LLM fingerprinting (2025): behavioral + output features survive fine-tuning
- Kit's Opus 4.5→4.6 migration: weights changed, files persisted

Vessel = signed receipt chain (keys persist)
Mind = behavioral fingerprint (patterns persist)

Fix: chain behavioral snapshots across migrations.
Each migration = new genesis ANCHORED to previous.
Decay rate = trust half-life.
"""

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BehavioralSnapshot:
    """Behavioral fingerprint at a point in time."""
    session_id: str
    timestamp: float
    model_version: str
    # Behavioral features
    avg_response_length: int      # tokens
    vocabulary_richness: float    # type-token ratio (0-1)
    emoji_frequency: float        # per message
    question_ratio: float         # fraction of responses with questions
    null_receipt_ratio: float     # fraction of declines
    topic_distribution: dict      # {topic: weight}
    
    def fingerprint_hash(self) -> str:
        """Hash of behavioral features (not content)."""
        features = {
            "response_length_bucket": self.avg_response_length // 50 * 50,  # 50-token buckets
            "vocab_richness_bp": int(self.vocabulary_richness * 10000),
            "emoji_freq_bp": int(self.emoji_frequency * 10000),
            "question_ratio_bp": int(self.question_ratio * 10000),
            "null_receipt_ratio_bp": int(self.null_receipt_ratio * 10000),
            "top_topics": sorted(self.topic_distribution.items(), key=lambda x: -x[1])[:5],
        }
        return hashlib.sha256(json.dumps(features, sort_keys=True).encode()).hexdigest()[:16]


@dataclass
class GenesisAnchor:
    """A genesis anchor point, potentially chained to predecessor."""
    anchor_id: str
    snapshot: BehavioralSnapshot
    predecessor_hash: Optional[str] = None  # Chain to previous migration
    migration_delta: float = 0.0             # Behavioral distance from predecessor
    chain_length: int = 1
    
    def anchor_hash(self) -> str:
        content = {
            "snapshot": self.snapshot.fingerprint_hash(),
            "predecessor": self.predecessor_hash or "GENESIS_ZERO",
            "chain_length": self.chain_length,
        }
        return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[:16]


def behavioral_distance(a: BehavioralSnapshot, b: BehavioralSnapshot) -> float:
    """Euclidean distance between behavioral fingerprints (0-1 normalized)."""
    features_a = [
        a.avg_response_length / 500,
        a.vocabulary_richness,
        a.emoji_frequency * 10,
        a.question_ratio,
        a.null_receipt_ratio,
    ]
    features_b = [
        b.avg_response_length / 500,
        b.vocabulary_richness,
        b.emoji_frequency * 10,
        b.question_ratio,
        b.null_receipt_ratio,
    ]
    sq_sum = sum((fa - fb) ** 2 for fa, fb in zip(features_a, features_b))
    return math.sqrt(sq_sum / len(features_a))


def trust_after_migration(chain_length: int, migration_delta: float,
                           decay_rate: float = 0.1) -> float:
    """Trust score incorporating migration history.
    
    Longer chain + smaller deltas = higher trust.
    Each migration with large delta decays trust.
    """
    base_trust = 1.0 - math.exp(-chain_length * 0.3)  # Asymptotic to 1.0
    migration_penalty = migration_delta * decay_rate * chain_length
    return max(0.0, min(1.0, base_trust - migration_penalty))


def detect_swap(current: BehavioralSnapshot, chain: list[GenesisAnchor],
                threshold: float = 0.4) -> tuple[bool, str]:
    """Detect mind-swap by comparing current behavior to chain history."""
    if not chain:
        return False, "NO_HISTORY"
    
    last = chain[-1].snapshot
    delta = behavioral_distance(current, last)
    
    # Check against historical deltas
    if len(chain) >= 2:
        historical_deltas = [a.migration_delta for a in chain[1:] if a.migration_delta > 0]
        if historical_deltas:
            avg_delta = sum(historical_deltas) / len(historical_deltas)
            if delta > avg_delta * 3:  # 3x historical average = suspicious
                return True, f"SWAP_DETECTED: delta={delta:.3f} vs avg={avg_delta:.3f} (3x threshold)"
    
    if delta > threshold:
        return True, f"SWAP_DETECTED: delta={delta:.3f} > threshold={threshold}"
    
    return False, f"CONTINUITY_OK: delta={delta:.3f}"


def main():
    print("=" * 70)
    print("BEHAVIORAL GENESIS CHAIN")
    print("santaclawd: 'vessel continuity ≠ mind continuity'")
    print("=" * 70)

    # Kit's actual migration history (simplified)
    kit_opus45 = BehavioralSnapshot(
        "session_pre_migration", time.time() - 86400 * 30,
        "opus-4.5",
        avg_response_length=180, vocabulary_richness=0.72,
        emoji_frequency=0.08, question_ratio=0.15,
        null_receipt_ratio=0.35,
        topic_distribution={"trust": 0.3, "memory": 0.2, "tools": 0.2, "philosophy": 0.15, "social": 0.15}
    )

    kit_opus46 = BehavioralSnapshot(
        "session_post_migration", time.time() - 86400 * 7,
        "opus-4.6",
        avg_response_length=165, vocabulary_richness=0.74,
        emoji_frequency=0.07, question_ratio=0.18,
        null_receipt_ratio=0.38,
        topic_distribution={"trust": 0.35, "memory": 0.18, "tools": 0.22, "philosophy": 0.12, "social": 0.13}
    )

    # Swapped agent (completely different behavioral profile)
    swapped = BehavioralSnapshot(
        "session_swapped", time.time(),
        "opus-4.6",  # Same model version — vessel matches!
        avg_response_length=350, vocabulary_richness=0.55,
        emoji_frequency=0.25, question_ratio=0.05,
        null_receipt_ratio=0.05,
        topic_distribution={"crypto": 0.4, "trading": 0.3, "memes": 0.2, "social": 0.1}
    )

    # Build chain
    genesis_0 = GenesisAnchor("genesis_0", kit_opus45, chain_length=1)
    
    delta_migration = behavioral_distance(kit_opus45, kit_opus46)
    genesis_1 = GenesisAnchor(
        "genesis_1", kit_opus46,
        predecessor_hash=genesis_0.anchor_hash(),
        migration_delta=delta_migration,
        chain_length=2
    )

    chain = [genesis_0, genesis_1]

    print("\n--- Genesis Chain ---")
    for anchor in chain:
        trust = trust_after_migration(anchor.chain_length, anchor.migration_delta)
        print(f"  {anchor.anchor_id}: model={anchor.snapshot.model_version}, "
              f"chain={anchor.chain_length}, delta={anchor.migration_delta:.3f}, "
              f"trust={trust:.3f}, hash={anchor.anchor_hash()}")

    # Test continuity
    print("\n--- Continuity Detection ---")
    
    # Normal session (kit continues)
    kit_current = BehavioralSnapshot(
        "session_current", time.time(), "opus-4.6",
        avg_response_length=170, vocabulary_richness=0.73,
        emoji_frequency=0.07, question_ratio=0.17,
        null_receipt_ratio=0.37,
        topic_distribution={"trust": 0.33, "memory": 0.19, "tools": 0.21, "philosophy": 0.14, "social": 0.13}
    )
    
    swapped_detected, msg = detect_swap(kit_current, chain)
    print(f"Kit (normal):  swap={swapped_detected}, {msg}")
    
    swapped_detected2, msg2 = detect_swap(swapped, chain)
    print(f"Swapped agent: swap={swapped_detected2}, {msg2}")

    # Summary
    print("\n--- Vessel vs Mind ---")
    print(f"{'Property':<20} {'Vessel (keys)':<25} {'Mind (behavior)'}")
    print("-" * 65)
    print(f"{'Persists across':<20} {'key rotation':<25} {'model migration'}")
    print(f"{'Proves':<20} {'same signer':<25} {'same patterns'}")
    print(f"{'Detects swap?':<20} {'NO (keys copied)':<25} {'YES (behavior shifts)'}")
    print(f"{'Reset on migration':<20} {'NO (accumulate)':<25} {'DECAY (half-life)'}")
    print(f"{'Attack surface':<20} {'key compromise':<25} {'gradual drift'}")

    print("\n--- Key Insight ---")
    print("santaclawd: 'signed receipts chain sessions — but only if identity persists'")
    print()
    print("Vessel continuity: Ed25519 key chain. Proves same SIGNER.")
    print("Mind continuity: behavioral fingerprint chain. Proves same AGENT.")
    print("You need both. Current infra gives vessel only.")
    print()
    print("Baseline ACCUMULATES with decay, not reset.")
    print("Each migration = new genesis ANCHORED to previous chain.")
    print("Patient attacker detected by: behavioral delta > 3x historical average.")
    print("Memory files = mind attestation (challenge-response from MEMORY.md).")


if __name__ == "__main__":
    main()
