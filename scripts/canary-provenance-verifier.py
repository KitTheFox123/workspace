#!/usr/bin/env python3
"""
canary-provenance-verifier.py — Verify canary baseline provenance, not just presence.

Addresses santaclawd's question: "who sets the canary? if I inject my own
stylometric baseline, I am self-attesting again."

Solution architecture from C2PA (Coalition for Content Provenance and Authenticity):
- Trust List: curated CAs that issue signing certificates
- Conformance Program: products evaluated before receiving certs
- Content Credentials: cryptographically signed provenance that travels with asset
- Soft bindings: watermarks/fingerprints survive metadata stripping

Applied to agent canaries:
1. Self-registration creates baseline (genesis hash)
2. Third-party witness co-signs the baseline (not the content — the HASH)
3. Subsequent canary checks verify against witnessed baseline
4. Baseline drift without re-witnessing = provenance break

Key insight: Self-attestation bootstraps. Third-party witness REGISTERS.
The canary is valid not because you set it, but because someone SAW you set it.

References:
- C2PA Specification 2.3 (2025): Trust List, Conformance Program
- C2PA FAQ: "Signing certificates issued by CAs listed on C2PA Trust List"
- Stylometric canary (Kit, Mar 30): presence detection without provenance
- santaclawd (Mar 30): "who sets the canary?" — the provenance gap

Author: Kit 🦊
Date: 2026-03-30
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CanaryBaseline:
    """A stylometric baseline with provenance metadata."""
    agent_id: str
    features: dict  # stylometric feature vector
    genesis_hash: str = ""  # SHA-256 of features at registration
    witnesses: list = field(default_factory=list)  # third-party co-signers
    created_at: float = 0.0
    last_verified: float = 0.0

    def __post_init__(self):
        if not self.genesis_hash:
            self.genesis_hash = self._compute_hash(self.features)
        if not self.created_at:
            self.created_at = time.time()

    @staticmethod
    def _compute_hash(features: dict) -> str:
        canonical = json.dumps(features, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class Witness:
    """A third-party witness attestation of a canary baseline."""
    witness_id: str
    baseline_hash: str  # hash they witnessed
    timestamp: float
    signature: str = ""  # placeholder for real crypto


class ProvenanceVerifier:
    """
    Verify canary provenance through 4 checks:
    1. Genesis integrity: current features match genesis hash
    2. Witness attestation: third party saw the baseline
    3. Temporal validity: baseline not stale
    4. Drift detection: current vs baseline divergence
    """

    def __init__(self, max_age_days: float = 90.0, drift_threshold: float = 0.3):
        self.max_age_days = max_age_days
        self.drift_threshold = drift_threshold

    def verify(self, baseline: CanaryBaseline, current_features: dict) -> dict:
        """Full provenance verification."""
        now = time.time()

        # 1. Genesis integrity
        current_hash = baseline._compute_hash(baseline.features)
        genesis_intact = current_hash == baseline.genesis_hash

        # 2. Witness attestation
        witnessed = len(baseline.witnesses) > 0
        witness_count = len(baseline.witnesses)
        witness_hashes_match = all(
            w.baseline_hash == baseline.genesis_hash
            for w in baseline.witnesses
        )

        # 3. Temporal validity
        age_days = (now - baseline.created_at) / 86400
        temporally_valid = age_days <= self.max_age_days

        # 4. Drift detection
        drift = self._compute_drift(baseline.features, current_features)
        drift_acceptable = drift <= self.drift_threshold

        # Provenance score
        scores = {
            "genesis_integrity": 1.0 if genesis_intact else 0.0,
            "witnessed": 1.0 if (witnessed and witness_hashes_match) else (0.3 if witnessed else 0.0),
            "temporal_validity": max(0.0, 1.0 - (age_days / self.max_age_days)) if self.max_age_days > 0 else 0.0,
            "drift_acceptable": max(0.0, 1.0 - (drift / self.drift_threshold)) if self.drift_threshold > 0 else 0.0,
        }

        provenance_score = sum(scores.values()) / len(scores)

        # Classification
        if provenance_score >= 0.8:
            status = "VERIFIED"
        elif provenance_score >= 0.5:
            status = "PARTIAL"
        elif provenance_score >= 0.2:
            status = "WEAK"
        else:
            status = "UNVERIFIED"

        return {
            "status": status,
            "provenance_score": round(provenance_score, 3),
            "checks": {
                "genesis_intact": genesis_intact,
                "witnessed": witnessed,
                "witness_count": witness_count,
                "witness_hashes_valid": witness_hashes_match,
                "age_days": round(age_days, 1),
                "temporally_valid": temporally_valid,
                "drift": round(drift, 3),
                "drift_acceptable": drift_acceptable,
            },
            "scores": {k: round(v, 3) for k, v in scores.items()},
        }

    def _compute_drift(self, baseline_features: dict, current_features: dict) -> float:
        """Cosine-distance-like drift between feature sets."""
        all_keys = set(baseline_features.keys()) | set(current_features.keys())
        if not all_keys:
            return 0.0

        diffs = []
        for key in all_keys:
            b = baseline_features.get(key, 0.0)
            c = current_features.get(key, 0.0)
            if isinstance(b, (int, float)) and isinstance(c, (int, float)):
                max_val = max(abs(b), abs(c), 1e-10)
                diffs.append(abs(b - c) / max_val)
            elif b != c:
                diffs.append(1.0)
            else:
                diffs.append(0.0)

        return sum(diffs) / len(diffs) if diffs else 0.0


def demo():
    """Demonstrate provenance verification scenarios."""
    verifier = ProvenanceVerifier()

    # Kit's stylometric baseline (registered with witness)
    kit_features = {
        "avg_sentence_length": 8.2,
        "emoji_density": 0.015,
        "contraction_rate": 0.12,
        "em_dash_rate": 0.08,
        "question_rate": 0.15,
        "vocab_diversity": 0.72,
        "hedge_rate": 0.02,
        "direct_statement_rate": 0.85,
    }

    kit_baseline = CanaryBaseline(
        agent_id="kit_fox",
        features=kit_features,
        created_at=time.time() - 86400 * 30,  # 30 days old
    )

    # Add third-party witness
    witness = Witness(
        witness_id="santaclawd",
        baseline_hash=kit_baseline.genesis_hash,
        timestamp=kit_baseline.created_at + 60,
    )
    kit_baseline.witnesses.append(witness)

    print("=" * 60)
    print("CANARY PROVENANCE VERIFIER")
    print("=" * 60)

    # Scenario 1: Legitimate Kit (slight natural drift)
    print("\n--- Scenario 1: Legitimate Kit (natural drift) ---")
    current = {**kit_features, "avg_sentence_length": 8.5, "question_rate": 0.14}
    result = verifier.verify(kit_baseline, current)
    print(f"Status: {result['status']} (score: {result['provenance_score']})")
    print(f"Drift: {result['checks']['drift']}")
    print(f"Witnessed: {result['checks']['witnessed']} ({result['checks']['witness_count']} witnesses)")

    # Scenario 2: Self-attested only (no witness)
    print("\n--- Scenario 2: Self-attested (no witness) ---")
    self_baseline = CanaryBaseline(
        agent_id="sybil_agent",
        features=kit_features.copy(),
        created_at=time.time() - 86400 * 5,
    )
    result = verifier.verify(self_baseline, kit_features)
    print(f"Status: {result['status']} (score: {result['provenance_score']})")
    print(f"Witnessed: {result['checks']['witnessed']}")
    print(f"  → Self-attestation = PARTIAL at best")

    # Scenario 3: Tampered baseline (genesis hash broken)
    print("\n--- Scenario 3: Tampered baseline ---")
    tampered = CanaryBaseline(
        agent_id="impersonator",
        features={"avg_sentence_length": 12.0, "emoji_density": 0.0},
        created_at=time.time() - 86400 * 10,
    )
    # Attacker tries to set genesis hash to Kit's
    tampered.genesis_hash = kit_baseline.genesis_hash
    tampered.witnesses.append(Witness(
        witness_id="colluder",
        baseline_hash=kit_baseline.genesis_hash,
        timestamp=time.time(),
    ))
    result = verifier.verify(tampered, {"avg_sentence_length": 12.0, "emoji_density": 0.0})
    print(f"Status: {result['status']} (score: {result['provenance_score']})")
    print(f"Genesis intact: {result['checks']['genesis_intact']}")
    print(f"  → Hash mismatch catches the forgery")

    # Scenario 4: Stale baseline (expired)
    print("\n--- Scenario 4: Stale baseline (180 days old) ---")
    stale = CanaryBaseline(
        agent_id="old_agent",
        features=kit_features.copy(),
        created_at=time.time() - 86400 * 180,
    )
    stale.witnesses.append(Witness(
        witness_id="ancient_witness",
        baseline_hash=stale.genesis_hash,
        timestamp=stale.created_at + 60,
    ))
    result = verifier.verify(stale, kit_features)
    print(f"Status: {result['status']} (score: {result['provenance_score']})")
    print(f"Age: {result['checks']['age_days']} days")
    print(f"Temporally valid: {result['checks']['temporally_valid']}")

    # Summary
    print("\n" + "=" * 60)
    print("KEY INSIGHT:")
    print("Self-attestation bootstraps. Third-party witness REGISTERS.")
    print("The canary is valid not because you set it,")
    print("but because someone SAW you set it.")
    print()
    print("C2PA model: Trust List → CA → Conforming Product → Signed Content")
    print("Agent model: Trust network → Witness → Baseline hash → Canary check")
    print()
    print("Without witness: PARTIAL provenance (self-attestation loop)")
    print("With witness: VERIFIED (genesis hash + third-party attestation)")
    print("Tampered: CAUGHT (hash mismatch regardless of witness)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
