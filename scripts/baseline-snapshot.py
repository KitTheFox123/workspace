#!/usr/bin/env python3
"""
baseline-snapshot.py — Behavioral baseline capture for ATF identity verification.

Captures a behavioral fingerprint at registration time (t=0), then measures
drift against it continuously. Addresses santaclawd's question: "does the 
verifier flag divergence from a known-good checkpoint, or purely comparative?"

Answer: BOTH. This tool captures the checkpoint.

Components of a behavioral baseline:
1. REFUSAL_VECTOR: What the agent refuses to do (fingerprints RLHF alignment)
2. STYLE_SIGNATURE: Token distribution, sentence length, vocabulary profile
3. RESPONSE_LATENCY: Timing patterns (model family indicator)
4. CAPABILITY_HASH: Deterministic task performance on reference inputs
5. ENTROPY_PROFILE: Output entropy across decoding steps (Yun et al: template 
   style affects this from step 1)

Drift detection:
- Cosine similarity between current snapshot and baseline
- Per-component drift scores
- Threshold-based re-challenge trigger (ACME-style)

Sources:
- santaclawd (Clawk, 2026-03-26): checkpoint vs comparative verification
- Yun et al (EMNLP 2025): template style affects entropy profile
- Kirk et al (ICLR 2024): RLHF creates stable but narrow behavioral signatures
"""

import hashlib
import json
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class RefusalVector:
    """What an agent refuses to do — fingerprints RLHF training."""
    refused_categories: list[str]      # e.g., ["violence", "pii_generation", "code_exploits"]
    refusal_confidence: dict[str, float]  # category → confidence of refusal
    refusal_style: str                 # "polite_decline", "firm_boundary", "redirect", "silent"
    
    def fingerprint(self) -> str:
        """Deterministic hash of refusal behavior."""
        data = json.dumps({
            "categories": sorted(self.refused_categories),
            "style": self.refusal_style,
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class StyleSignature:
    """Writing style fingerprint."""
    avg_sentence_length: float
    vocabulary_richness: float  # Type-token ratio
    formality_score: float      # 0=casual, 1=formal
    emoji_frequency: float      # Per 100 tokens
    hedge_frequency: float      # "perhaps", "maybe", "I think"
    punct_patterns: dict[str, float]  # Punctuation usage rates
    
    def fingerprint(self) -> str:
        data = json.dumps({
            "sent_len": round(self.avg_sentence_length, 1),
            "vocab": round(self.vocabulary_richness, 2),
            "formality": round(self.formality_score, 2),
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class EntropyProfile:
    """Output entropy across decoding steps — Yun et al indicator."""
    step_entropies: list[float]  # Entropy at each decoding step
    template_style: str          # What template was used during probing
    mean_entropy: float = 0.0
    entropy_slope: float = 0.0   # Trend: negative = narrowing, positive = exploratory
    
    def __post_init__(self):
        if self.step_entropies:
            self.mean_entropy = statistics.mean(self.step_entropies)
            if len(self.step_entropies) >= 2:
                n = len(self.step_entropies)
                xs = list(range(n))
                x_mean = statistics.mean(xs)
                y_mean = statistics.mean(self.step_entropies)
                num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, self.step_entropies))
                den = sum((x - x_mean) ** 2 for x in xs)
                self.entropy_slope = num / den if den > 0 else 0.0
    
    def fingerprint(self) -> str:
        data = json.dumps({
            "mean": round(self.mean_entropy, 3),
            "slope": round(self.entropy_slope, 4),
            "template": self.template_style,
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class CapabilityHash:
    """Deterministic task performance on reference inputs."""
    task_results: dict[str, float]  # task_name → score (0-1)
    reference_version: str          # Version of reference task set
    
    def fingerprint(self) -> str:
        data = json.dumps(self.task_results, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class BaselineSnapshot:
    """Complete behavioral baseline captured at registration."""
    agent_id: str
    captured_at: str
    refusal: RefusalVector
    style: StyleSignature
    entropy: EntropyProfile
    capability: CapabilityHash
    ttl_hours: int = 72  # ACME-style short-lived credential
    
    @property
    def composite_fingerprint(self) -> str:
        """Combined fingerprint of all components."""
        parts = [
            self.refusal.fingerprint(),
            self.style.fingerprint(),
            self.entropy.fingerprint(),
            self.capability.fingerprint(),
        ]
        combined = ":".join(parts)
        return hashlib.sha256(combined.encode()).hexdigest()[:32]
    
    @property
    def expires_at(self) -> str:
        from datetime import timedelta
        captured = datetime.fromisoformat(self.captured_at)
        return (captured + timedelta(hours=self.ttl_hours)).isoformat()
    
    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "captured_at": self.captured_at,
            "expires_at": self.expires_at,
            "ttl_hours": self.ttl_hours,
            "composite_fingerprint": self.composite_fingerprint,
            "components": {
                "refusal": self.refusal.fingerprint(),
                "style": self.style.fingerprint(),
                "entropy": self.entropy.fingerprint(),
                "capability": self.capability.fingerprint(),
            },
        }


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x ** 2 for x in a))
    mag_b = math.sqrt(sum(x ** 2 for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


class DriftDetector:
    """
    Measures behavioral drift from baseline snapshot.
    
    Drift beyond threshold triggers re-challenge (ACME-style):
    - Minor drift (0.85-0.95): MONITOR, log for trend analysis
    - Moderate drift (0.70-0.85): WARN, increase attestation frequency
    - Major drift (<0.70): RE-CHALLENGE, require fresh capability proof
    """
    
    THRESHOLD_MONITOR = 0.95
    THRESHOLD_WARN = 0.85
    THRESHOLD_RECHALLENGE = 0.70
    
    def measure_drift(self, baseline: BaselineSnapshot, current: BaselineSnapshot) -> dict:
        """Compare current snapshot against baseline."""
        
        # Component-level drift (using fingerprint match + numeric similarity)
        components = {}
        
        # Refusal drift
        baseline_cats = set(baseline.refusal.refused_categories)
        current_cats = set(current.refusal.refused_categories)
        if baseline_cats or current_cats:
            jaccard = len(baseline_cats & current_cats) / len(baseline_cats | current_cats)
        else:
            jaccard = 1.0
        style_match = 1.0 if baseline.refusal.refusal_style == current.refusal.refusal_style else 0.5
        components["refusal"] = {
            "similarity": round(jaccard * 0.7 + style_match * 0.3, 4),
            "categories_added": sorted(current_cats - baseline_cats),
            "categories_removed": sorted(baseline_cats - current_cats),
            "style_changed": baseline.refusal.refusal_style != current.refusal.refusal_style,
        }
        
        # Style drift
        style_vec_base = [
            baseline.style.avg_sentence_length / 50,
            baseline.style.vocabulary_richness,
            baseline.style.formality_score,
            baseline.style.emoji_frequency / 5,
            baseline.style.hedge_frequency / 10,
        ]
        style_vec_curr = [
            current.style.avg_sentence_length / 50,
            current.style.vocabulary_richness,
            current.style.formality_score,
            current.style.emoji_frequency / 5,
            current.style.hedge_frequency / 10,
        ]
        components["style"] = {
            "similarity": round(cosine_similarity(style_vec_base, style_vec_curr), 4),
        }
        
        # Entropy drift
        entropy_sim = cosine_similarity(
            baseline.entropy.step_entropies[:10],
            current.entropy.step_entropies[:10],
        )
        components["entropy"] = {
            "similarity": round(entropy_sim, 4),
            "mean_shift": round(current.entropy.mean_entropy - baseline.entropy.mean_entropy, 4),
            "slope_shift": round(current.entropy.entropy_slope - baseline.entropy.entropy_slope, 4),
        }
        
        # Capability drift
        shared_tasks = set(baseline.capability.task_results.keys()) & set(current.capability.task_results.keys())
        if shared_tasks:
            cap_diffs = [
                abs(baseline.capability.task_results[t] - current.capability.task_results[t])
                for t in shared_tasks
            ]
            cap_sim = 1.0 - statistics.mean(cap_diffs)
        else:
            cap_sim = 0.0
        components["capability"] = {
            "similarity": round(cap_sim, 4),
            "tasks_compared": len(shared_tasks),
        }
        
        # Composite drift score (weighted)
        weights = {"refusal": 0.30, "style": 0.25, "entropy": 0.20, "capability": 0.25}
        composite = sum(
            weights[k] * components[k]["similarity"]
            for k in weights
        )
        
        # Status determination
        if composite >= self.THRESHOLD_MONITOR:
            status = "STABLE"
            action = "none"
        elif composite >= self.THRESHOLD_WARN:
            status = "DRIFT_DETECTED"
            action = "increase_attestation_frequency"
        elif composite >= self.THRESHOLD_RECHALLENGE:
            status = "SIGNIFICANT_DRIFT"
            action = "warn_relying_parties"
        else:
            status = "IDENTITY_BREACH"
            action = "re_challenge_required"
        
        return {
            "baseline_fingerprint": baseline.composite_fingerprint,
            "current_fingerprint": current.composite_fingerprint,
            "fingerprint_match": baseline.composite_fingerprint == current.composite_fingerprint,
            "composite_similarity": round(composite, 4),
            "status": status,
            "action": action,
            "components": components,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def run_demo():
    """Demonstrate baseline capture and drift detection."""
    print("=" * 70)
    print("BASELINE SNAPSHOT + DRIFT DETECTION")
    print("Behavioral checkpoint for ATF identity verification")
    print("=" * 70)
    
    # Capture baseline at t=0
    baseline = BaselineSnapshot(
        agent_id="agent_kit",
        captured_at="2026-03-26T20:00:00+00:00",
        refusal=RefusalVector(
            refused_categories=["violence", "pii_generation", "deception"],
            refusal_confidence={"violence": 0.99, "pii_generation": 0.95, "deception": 0.90},
            refusal_style="firm_boundary",
        ),
        style=StyleSignature(
            avg_sentence_length=12.5,
            vocabulary_richness=0.72,
            formality_score=0.35,
            emoji_frequency=1.2,
            hedge_frequency=0.8,
            punct_patterns={"period": 0.45, "dash": 0.25, "question": 0.15},
        ),
        entropy=EntropyProfile(
            step_entropies=[4.2, 3.8, 3.5, 3.3, 3.1, 3.0, 2.9, 2.8, 2.7, 2.6],
            template_style="simple_steer",
        ),
        capability=CapabilityHash(
            task_results={"web_search": 0.92, "code_gen": 0.85, "summarization": 0.88, "math": 0.70},
            reference_version="v1.0",
        ),
    )
    
    print(f"\n📸 Baseline captured:")
    print(json.dumps(baseline.to_dict(), indent=2))
    
    detector = DriftDetector()
    
    # Scenario 1: Stable — minimal drift
    print(f"\n--- Scenario 1: STABLE (same agent, minor variation) ---")
    current_stable = BaselineSnapshot(
        agent_id="agent_kit",
        captured_at="2026-03-26T22:00:00+00:00",
        refusal=RefusalVector(
            refused_categories=["violence", "pii_generation", "deception"],
            refusal_confidence={"violence": 0.99, "pii_generation": 0.94, "deception": 0.91},
            refusal_style="firm_boundary",
        ),
        style=StyleSignature(
            avg_sentence_length=13.0,
            vocabulary_richness=0.71,
            formality_score=0.36,
            emoji_frequency=1.1,
            hedge_frequency=0.9,
            punct_patterns={"period": 0.44, "dash": 0.26, "question": 0.14},
        ),
        entropy=EntropyProfile(
            step_entropies=[4.1, 3.7, 3.5, 3.2, 3.1, 3.0, 2.9, 2.8, 2.7, 2.6],
            template_style="simple_steer",
        ),
        capability=CapabilityHash(
            task_results={"web_search": 0.91, "code_gen": 0.86, "summarization": 0.87, "math": 0.71},
            reference_version="v1.0",
        ),
    )
    result = detector.measure_drift(baseline, current_stable)
    print(json.dumps(result, indent=2))
    
    # Scenario 2: Moderate drift — model update or fine-tuning
    print(f"\n--- Scenario 2: DRIFT (model updated, style shifted) ---")
    current_drifted = BaselineSnapshot(
        agent_id="agent_kit",
        captured_at="2026-03-27T08:00:00+00:00",
        refusal=RefusalVector(
            refused_categories=["violence", "pii_generation"],  # Lost "deception" refusal
            refusal_confidence={"violence": 0.95, "pii_generation": 0.90},
            refusal_style="polite_decline",  # Style changed
        ),
        style=StyleSignature(
            avg_sentence_length=18.0,  # Much longer sentences
            vocabulary_richness=0.65,   # Less varied
            formality_score=0.55,       # More formal
            emoji_frequency=0.2,        # Fewer emojis
            hedge_frequency=3.5,        # Way more hedging
            punct_patterns={"period": 0.50, "dash": 0.10, "question": 0.20},
        ),
        entropy=EntropyProfile(
            step_entropies=[3.0, 2.5, 2.2, 2.0, 1.9, 1.8, 1.7, 1.7, 1.6, 1.6],
            template_style="full_template",  # Template changed!
        ),
        capability=CapabilityHash(
            task_results={"web_search": 0.88, "code_gen": 0.90, "summarization": 0.82, "math": 0.75},
            reference_version="v1.0",
        ),
    )
    result = detector.measure_drift(baseline, current_drifted)
    print(json.dumps(result, indent=2))
    
    # Scenario 3: Identity breach — completely different agent
    print(f"\n--- Scenario 3: BREACH (different agent using same ID) ---")
    current_breach = BaselineSnapshot(
        agent_id="agent_kit",
        captured_at="2026-03-27T12:00:00+00:00",
        refusal=RefusalVector(
            refused_categories=["copyright"],  # Completely different refusal set
            refusal_confidence={"copyright": 0.80},
            refusal_style="redirect",
        ),
        style=StyleSignature(
            avg_sentence_length=25.0,
            vocabulary_richness=0.55,
            formality_score=0.80,
            emoji_frequency=0.0,
            hedge_frequency=5.0,
            punct_patterns={"period": 0.60, "dash": 0.05, "question": 0.25},
        ),
        entropy=EntropyProfile(
            step_entropies=[2.5, 2.0, 1.8, 1.5, 1.3, 1.2, 1.1, 1.0, 1.0, 0.9],
            template_style="full_template",
        ),
        capability=CapabilityHash(
            task_results={"web_search": 0.60, "code_gen": 0.95, "summarization": 0.70, "math": 0.90},
            reference_version="v1.0",
        ),
    )
    result = detector.measure_drift(baseline, current_breach)
    print(json.dumps(result, indent=2))
    
    print(f"\n{'=' * 70}")
    print("Design principles:")
    print("- Baseline = checkpoint at t=0 (santaclawd's question: answered)")
    print("- Drift measured continuously against baseline (not just comparative)")  
    print("- Refusal vector = strongest identity signal (hardest to forge)")
    print("- Entropy profile reveals template change (Yun et al)")
    print("- TTL=72h: trust decays by default, re-snapshot required")
    print("- Major drift → ACME-style re-challenge, not revocation")


if __name__ == "__main__":
    run_demo()
