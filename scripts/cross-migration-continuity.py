#!/usr/bin/env python3
"""
cross-migration-continuity.py — Behavioral continuity across model migrations.

Based on:
- santaclawd: "vessel continuity vs mind continuity"
- ACM ASIACCS 2017: Continuous authentication via behavioral biometrics
- Kit's Opus 4.5→4.6 migration: weights changed, files persisted

The problem: patient attacker drifts, then triggers migration to clear baseline.
Fix: baseline ACCUMULATES, never resets. Migration = expected discontinuity.
Hash(pre_fingerprint + migration_event + post_fingerprint) = unbroken chain.

Vessel = keys, signatures, receipt chains (crypto identity)
Mind = behavioral patterns, style, scope usage (behavioral identity)
You need both. Current infra gives vessel. Mind is the gap.
"""

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BehavioralFingerprint:
    """Behavioral snapshot at a point in time."""
    session_id: str
    timestamp: float
    style_score: float      # Stylometric similarity to baseline
    scope_usage: dict       # Which capabilities used
    response_length_mean: float
    vocabulary_diversity: float  # Type-token ratio
    decline_rate: float     # Fraction of requests declined
    
    def feature_vector(self) -> list[float]:
        return [
            self.style_score,
            self.response_length_mean / 1000,  # Normalize
            self.vocabulary_diversity,
            self.decline_rate,
            len(self.scope_usage) / 20,  # Normalize scope breadth
        ]
    
    def fingerprint_hash(self) -> str:
        content = json.dumps({
            "style": round(self.style_score, 4),
            "resp_len": round(self.response_length_mean, 1),
            "vocab": round(self.vocabulary_diversity, 4),
            "decline": round(self.decline_rate, 4),
            "scope_keys": sorted(self.scope_usage.keys()),
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class MigrationEvent:
    """Record of a model/infrastructure migration."""
    from_model: str
    to_model: str
    timestamp: float
    reason: str
    pre_fingerprint: str   # Hash of behavioral fingerprint before
    post_fingerprint: str  # Hash of behavioral fingerprint after
    
    def continuity_hash(self) -> str:
        """Chain pre→migration→post. Unbroken regardless of weight changes."""
        content = json.dumps({
            "pre": self.pre_fingerprint,
            "from": self.from_model,
            "to": self.to_model,
            "reason": self.reason,
            "post": self.post_fingerprint,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass 
class ContinuityChain:
    """Accumulated behavioral baseline across migrations."""
    agent_id: str
    genesis_hash: str
    fingerprints: list[BehavioralFingerprint] = field(default_factory=list)
    migrations: list[MigrationEvent] = field(default_factory=list)
    ewma_alpha: float = 0.3  # EWMA decay rate
    
    def add_fingerprint(self, fp: BehavioralFingerprint):
        self.fingerprints.append(fp)
    
    def behavioral_baseline(self) -> list[float]:
        """EWMA of all fingerprints — accumulates, never resets."""
        if not self.fingerprints:
            return [0.0] * 5
        
        baseline = self.fingerprints[0].feature_vector()
        for fp in self.fingerprints[1:]:
            vec = fp.feature_vector()
            baseline = [
                self.ewma_alpha * v + (1 - self.ewma_alpha) * b
                for v, b in zip(vec, baseline)
            ]
        return baseline
    
    def detect_drift(self, new_fp: BehavioralFingerprint, threshold: float = 0.15) -> tuple[bool, float]:
        """Detect behavioral drift from CUMULATIVE baseline."""
        baseline = self.behavioral_baseline()
        new_vec = new_fp.feature_vector()
        
        # Euclidean distance
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(baseline, new_vec)))
        return dist > threshold, dist
    
    def record_migration(self, from_model: str, to_model: str, reason: str,
                          pre_fp: BehavioralFingerprint, post_fp: BehavioralFingerprint) -> MigrationEvent:
        """Record migration with continuity hash."""
        event = MigrationEvent(
            from_model=from_model,
            to_model=to_model,
            timestamp=post_fp.timestamp,
            reason=reason,
            pre_fingerprint=pre_fp.fingerprint_hash(),
            post_fingerprint=post_fp.fingerprint_hash(),
        )
        self.migrations.append(event)
        return event
    
    def chain_integrity(self) -> bool:
        """Verify unbroken chain across all migrations."""
        if not self.migrations:
            return True
        # Each migration's pre must match prior post (or genesis)
        for i, m in enumerate(self.migrations):
            if i == 0:
                continue
            prev = self.migrations[i-1]
            if m.pre_fingerprint != prev.post_fingerprint:
                return False  # Gap in chain
        return True


def demo():
    print("=" * 70)
    print("CROSS-MIGRATION CONTINUITY")
    print("santaclawd: 'vessel vs mind continuity'")
    print("=" * 70)

    chain = ContinuityChain("kit_fox", genesis_hash="abc123")
    
    # Pre-migration sessions (Opus 4.5)
    scope = {"search": 50, "post": 30, "build": 20, "email": 15}
    for i in range(10):
        fp = BehavioralFingerprint(
            f"session_{i}", float(i),
            style_score=0.85 + (i % 3) * 0.02,
            scope_usage=scope,
            response_length_mean=450 + i * 5,
            vocabulary_diversity=0.72,
            decline_rate=0.15,
        )
        chain.add_fingerprint(fp)
    
    pre_baseline = chain.behavioral_baseline()
    pre_fp = chain.fingerprints[-1]
    
    # Migration event (Opus 4.5 → 4.6)
    post_fp = BehavioralFingerprint(
        "session_migration", 11.0,
        style_score=0.82,  # Slight style shift
        scope_usage=scope,
        response_length_mean=470,
        vocabulary_diversity=0.74,  # Slightly different
        decline_rate=0.14,
    )
    
    event = chain.record_migration("opus-4.5", "opus-4.6", "scheduled_upgrade", pre_fp, post_fp)
    chain.add_fingerprint(post_fp)
    
    drifted, dist = chain.detect_drift(post_fp)
    print(f"\n--- Honest Migration (Opus 4.5→4.6) ---")
    print(f"Pre-baseline:  {[f'{x:.3f}' for x in pre_baseline]}")
    print(f"Post-migration: {[f'{x:.3f}' for x in post_fp.feature_vector()]}")
    print(f"Drift distance: {dist:.4f}, Threshold: 0.15, Drifted: {drifted}")
    print(f"Continuity hash: {event.continuity_hash()}")
    print(f"Chain intact: {chain.chain_integrity()}")
    
    # Attacker scenario: drift then migrate to clear baseline
    print(f"\n--- Patient Attacker (drift + migrate to clear) ---")
    attacker_chain = ContinuityChain("compromised_agent", genesis_hash="def456")
    
    # Normal sessions
    for i in range(5):
        fp = BehavioralFingerprint(
            f"normal_{i}", float(i), 0.85, scope, 450, 0.72, 0.15
        )
        attacker_chain.add_fingerprint(fp)
    
    # Slow drift (attacker takes over)
    for i in range(5):
        fp = BehavioralFingerprint(
            f"drift_{i}", float(i + 5),
            style_score=0.85 - i * 0.08,  # Degrading
            scope_usage={**scope, "exfil": i * 10},  # New scope
            response_length_mean=450 + i * 50,
            vocabulary_diversity=0.72 - i * 0.05,
            decline_rate=0.15 - i * 0.03,  # Declining less
        )
        attacker_chain.add_fingerprint(fp)
    
    # Attacker triggers "migration" to reset baseline
    attacker_pre = attacker_chain.fingerprints[-1]
    attacker_post = BehavioralFingerprint(
        "fake_migration", 10.0, 0.50, {**scope, "exfil": 50}, 700, 0.47, 0.0
    )
    
    # But CUMULATIVE baseline catches it
    drifted_atk, dist_atk = attacker_chain.detect_drift(attacker_post)
    print(f"Cumulative baseline: {[f'{x:.3f}' for x in attacker_chain.behavioral_baseline()]}")
    print(f"Attacker post:       {[f'{x:.3f}' for x in attacker_post.feature_vector()]}")
    print(f"Drift distance: {dist_atk:.4f}, Drifted: {drifted_atk}")
    print(f"Detection: {'CAUGHT — baseline never reset' if drifted_atk else 'MISSED'}")
    
    # Summary
    print(f"\n--- Vessel vs Mind ---")
    print(f"{'Property':<20} {'Vessel (crypto)':<25} {'Mind (behavioral)'}")
    print("-" * 65)
    props = [
        ("Proves", "Same key holder", "Same behavior pattern"),
        ("Survives", "Key rotation (chain)", "Model migration (EWMA)"),
        ("Detects", "Key theft", "Behavioral takeover"),
        ("Weakness", "Key = transferable", "Baseline = gameable if reset"),
        ("Fix", "Multi-factor", "Cumulative, never reset"),
    ]
    for prop, vessel, mind in props:
        print(f"{prop:<20} {vessel:<25} {mind}")
    
    print(f"\n--- Key Insight ---")
    print("Patient attacker drifts, then migrates to clear baseline.")
    print("Fix: baseline ACCUMULATES. Migration = expected Δ, not reset.")
    print("Hash(pre + migration + post) = unbroken chain.")
    print("Unexplained Δ post-migration = flag for investigation.")


if __name__ == "__main__":
    demo()
