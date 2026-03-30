#!/usr/bin/env python3
"""
adversarial-stylometry-detector.py — Detect when an agent is attempting
to disguise its writing style (adversarial stylometry).

Based on:
- Brennan, Afroz & Greenstadt (2012): manual adversarial stylometry
  drops attribution to near-chance, BUT adversarial writing develops
  its own detectable "meta-style"
- Afroz, Brennan & Greenstadt (2012): obfuscation and imitation
  produce detectable artifacts — the attempt IS a signal
- Gröndahl & Asokan (2020): incomplete imitation leaks both styles
- Potthast, Hagen & Stein (2016): safety/soundness/sensibility tradeoff

Key insight: an agent trying to break its fingerprint generates a NEW
fingerprint — the fingerprint of effort. Consistency of inconsistency
is itself a pattern.

Detects:
1. Style volatility — sudden shifts in feature distributions
2. Effort artifacts — unnatural uniformity (over-correction)
3. Imitation leakage — mixed feature profiles from two styles
4. Temporal discontinuity — style change without context change
"""

import json
import math
import statistics
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StyleSnapshot:
    """Stylometric features from a text sample."""
    timestamp: str
    avg_sentence_length: float
    vocabulary_richness: float  # type-token ratio
    punctuation_density: float
    question_ratio: float
    contraction_rate: float
    emoji_density: float
    dash_usage: float  # em-dash, en-dash frequency
    avg_word_length: float
    passive_voice_ratio: float  # approximated
    first_person_ratio: float
    hedging_ratio: float  # "maybe", "perhaps", "might"
    
    def feature_vector(self) -> list[float]:
        return [
            self.avg_sentence_length,
            self.vocabulary_richness,
            self.punctuation_density,
            self.question_ratio,
            self.contraction_rate,
            self.emoji_density,
            self.dash_usage,
            self.avg_word_length,
            self.passive_voice_ratio,
            self.first_person_ratio,
            self.hedging_ratio,
        ]


@dataclass
class AdversarialSignal:
    signal_type: str  # volatility, effort, imitation, discontinuity
    score: float  # 0-1
    detail: str
    features_affected: list[str] = field(default_factory=list)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x**2 for x in a))
    mag_b = math.sqrt(sum(x**2 for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def coefficient_of_variation(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = statistics.mean(values)
    if mean == 0:
        return 0.0
    return statistics.stdev(values) / abs(mean)


def detect_volatility(snapshots: list[StyleSnapshot]) -> AdversarialSignal:
    """Sudden style shifts between consecutive samples."""
    if len(snapshots) < 3:
        return AdversarialSignal("volatility", 0.0, "insufficient samples")
    
    similarities = []
    for i in range(1, len(snapshots)):
        sim = cosine_similarity(
            snapshots[i-1].feature_vector(),
            snapshots[i].feature_vector()
        )
        similarities.append(sim)
    
    # Low mean similarity = high volatility
    mean_sim = statistics.mean(similarities)
    # High variance in similarity = inconsistent shifts
    var_sim = statistics.stdev(similarities) if len(similarities) > 1 else 0
    
    # Natural writing has high, stable similarity (>0.95)
    # Adversarial has lower, more variable similarity
    volatility = max(0, 1 - mean_sim) + var_sim
    score = min(1.0, volatility * 2)
    
    return AdversarialSignal(
        "volatility", round(score, 3),
        f"mean_similarity={mean_sim:.3f}, similarity_stdev={var_sim:.3f}",
        features_affected=["all"]
    )


def detect_effort_artifacts(snapshots: list[StyleSnapshot]) -> AdversarialSignal:
    """Over-correction produces unnatural uniformity in some features."""
    if len(snapshots) < 3:
        return AdversarialSignal("effort", 0.0, "insufficient samples")
    
    feature_names = [
        "sentence_length", "vocabulary", "punctuation", "questions",
        "contractions", "emoji", "dashes", "word_length",
        "passive", "first_person", "hedging"
    ]
    
    suspicious = []
    for i, name in enumerate(feature_names):
        values = [s.feature_vector()[i] for s in snapshots]
        cv = coefficient_of_variation(values)
        # Unnaturally LOW variation suggests deliberate control
        # Natural writing: CV > 0.1 for most features
        if cv < 0.02 and statistics.mean(values) > 0:
            suspicious.append(name)
    
    # More than 3 features with near-zero variation = suspicious
    score = min(1.0, len(suspicious) / 5)
    
    return AdversarialSignal(
        "effort", round(score, 3),
        f"{len(suspicious)} features with CV<0.02: {suspicious}",
        features_affected=suspicious
    )


def detect_imitation_leakage(
    snapshots: list[StyleSnapshot],
    baseline: Optional[list[StyleSnapshot]] = None
) -> AdversarialSignal:
    """Mixed feature profiles — some features match original, others match target."""
    if len(snapshots) < 3:
        return AdversarialSignal("imitation", 0.0, "insufficient samples")
    
    if baseline is None or len(baseline) < 3:
        # Without baseline, check for bimodal feature distributions
        feature_names = [
            "sentence_length", "vocabulary", "punctuation", "questions",
            "contractions", "emoji", "dashes", "word_length",
            "passive", "first_person", "hedging"
        ]
        bimodal_count = 0
        for i, name in enumerate(feature_names):
            values = [s.feature_vector()[i] for s in snapshots]
            if len(values) < 4:
                continue
            # Simple bimodality test: check if values cluster at two levels
            sorted_vals = sorted(values)
            mid = len(sorted_vals) // 2
            lower = statistics.mean(sorted_vals[:mid])
            upper = statistics.mean(sorted_vals[mid:])
            overall_range = max(values) - min(values)
            if overall_range > 0:
                gap = (upper - lower) / overall_range
                if gap > 0.6:  # Clear separation
                    bimodal_count += 1
        
        score = min(1.0, bimodal_count / 4)
        return AdversarialSignal(
            "imitation", round(score, 3),
            f"{bimodal_count} features show bimodal distribution (leakage between styles)",
            features_affected=[]
        )
    
    # With baseline: check which features deviate and which don't
    baseline_means = []
    for i in range(len(baseline[0].feature_vector())):
        baseline_means.append(statistics.mean([s.feature_vector()[i] for s in baseline]))
    
    current_means = []
    for i in range(len(snapshots[0].feature_vector())):
        current_means.append(statistics.mean([s.feature_vector()[i] for s in snapshots]))
    
    # Incomplete imitation: some features shift, others don't
    shifted = 0
    unshifted = 0
    for i in range(len(baseline_means)):
        if baseline_means[i] == 0:
            continue
        change = abs(current_means[i] - baseline_means[i]) / max(abs(baseline_means[i]), 0.01)
        if change > 0.3:
            shifted += 1
        else:
            unshifted += 1
    
    total = shifted + unshifted
    if total == 0:
        return AdversarialSignal("imitation", 0.0, "no features to compare")
    
    # Perfect imitation: all shift. Natural: none shift. Partial = leakage.
    ratio = shifted / total
    # Most suspicious when ~50% shifted (half old style, half new)
    leakage = 1 - abs(ratio - 0.5) * 2
    
    return AdversarialSignal(
        "imitation", round(leakage, 3),
        f"{shifted}/{total} features shifted (ratio={ratio:.2f}), leakage={leakage:.2f}",
        features_affected=[]
    )


def detect_temporal_discontinuity(snapshots: list[StyleSnapshot]) -> AdversarialSignal:
    """Style changes without corresponding context changes."""
    if len(snapshots) < 4:
        return AdversarialSignal("discontinuity", 0.0, "insufficient samples")
    
    # Compute rolling similarity
    sims = []
    for i in range(1, len(snapshots)):
        sim = cosine_similarity(
            snapshots[i-1].feature_vector(),
            snapshots[i].feature_vector()
        )
        sims.append(sim)
    
    if len(sims) < 3:
        return AdversarialSignal("discontinuity", 0.0, "insufficient pairs")
    
    mean_sim = statistics.mean(sims)
    std_sim = statistics.stdev(sims)
    
    # Find discontinuities: similarity drops > 2 sigma
    discontinuities = []
    for i, sim in enumerate(sims):
        if std_sim > 0 and (mean_sim - sim) > 2 * std_sim:
            discontinuities.append(i)
    
    score = min(1.0, len(discontinuities) / max(1, len(sims) // 3))
    
    return AdversarialSignal(
        "discontinuity", round(score, 3),
        f"{len(discontinuities)} discontinuities (>2σ) in {len(sims)} transitions",
        features_affected=[]
    )


def analyze(snapshots: list[StyleSnapshot], baseline: Optional[list[StyleSnapshot]] = None) -> dict:
    """Run all detectors and produce composite score."""
    signals = [
        detect_volatility(snapshots),
        detect_effort_artifacts(snapshots),
        detect_imitation_leakage(snapshots, baseline),
        detect_temporal_discontinuity(snapshots),
    ]
    
    weights = {"volatility": 0.25, "effort": 0.30, "imitation": 0.25, "discontinuity": 0.20}
    composite = sum(s.score * weights[s.signal_type] for s in signals)
    
    verdict = "natural"
    if composite > 0.6:
        verdict = "adversarial"
    elif composite > 0.3:
        verdict = "suspicious"
    
    return {
        "composite_score": round(composite, 3),
        "verdict": verdict,
        "signals": {s.signal_type: {"score": s.score, "detail": s.detail} for s in signals},
        "insight": (
            "Brennan & Greenstadt (2012): adversarial writing develops its own "
            "detectable meta-style. The attempt to break a fingerprint IS a fingerprint. "
            f"This sample scores {composite:.3f} — {verdict}."
        )
    }


def demo():
    """Demo with natural vs adversarial writing samples."""
    import random
    random.seed(42)
    
    # Natural Kit-style writing (consistent)
    natural = []
    for i in range(8):
        natural.append(StyleSnapshot(
            timestamp=f"2026-03-30T0{i}:00:00Z",
            avg_sentence_length=8.2 + random.gauss(0, 0.5),
            vocabulary_richness=0.72 + random.gauss(0, 0.02),
            punctuation_density=0.08 + random.gauss(0, 0.005),
            question_ratio=0.12 + random.gauss(0, 0.02),
            contraction_rate=0.15 + random.gauss(0, 0.01),
            emoji_density=0.01 + random.gauss(0, 0.002),
            dash_usage=0.04 + random.gauss(0, 0.005),
            avg_word_length=4.8 + random.gauss(0, 0.2),
            passive_voice_ratio=0.05 + random.gauss(0, 0.01),
            first_person_ratio=0.03 + random.gauss(0, 0.005),
            hedging_ratio=0.02 + random.gauss(0, 0.005),
        ))
    
    # Adversarial: agent trying to write like someone else
    adversarial = []
    for i in range(8):
        # Shifts some features (sentence length, emoji) but leaks others
        adversarial.append(StyleSnapshot(
            timestamp=f"2026-03-30T0{i}:00:00Z",
            avg_sentence_length=14.5 + random.gauss(0, 2.0),  # shifted + volatile
            vocabulary_richness=0.55 + random.gauss(0, 0.05),  # shifted
            punctuation_density=0.08 + random.gauss(0, 0.005),  # leaked (unchanged)
            question_ratio=0.04 + random.gauss(0, 0.03),  # shifted
            contraction_rate=0.15 + random.gauss(0, 0.01),  # leaked
            emoji_density=0.05 + random.gauss(0, 0.02),  # shifted + volatile
            dash_usage=0.04 + random.gauss(0, 0.005),  # leaked
            avg_word_length=5.8 + random.gauss(0, 0.8),  # shifted + volatile
            passive_voice_ratio=0.15 + random.gauss(0, 0.04),  # shifted
            first_person_ratio=0.03 + random.gauss(0, 0.005),  # leaked
            hedging_ratio=0.08 + random.gauss(0, 0.03),  # shifted
        ))
    
    print("=" * 60)
    print("ADVERSARIAL STYLOMETRY DETECTOR")
    print("Brennan & Greenstadt (2012) + Afroz et al (2012)")
    print("=" * 60)
    
    print("\n--- Natural writing (Kit baseline) ---")
    result = analyze(natural)
    print(json.dumps(result, indent=2))
    
    print("\n--- Adversarial writing (imitation attempt) ---")
    result = analyze(adversarial, baseline=natural)
    print(json.dumps(result, indent=2))
    
    print("\n--- Key finding ---")
    print("Incomplete imitation leaks BOTH styles.")
    print("The adversarial sample's leaked features (punctuation,")
    print("contractions, dashes, first-person) match the original.")
    print("The shifted features are MORE volatile than natural writing.")
    print("Afroz et al: 'adversarial writing has its own style.'")
    print("The attempt IS the fingerprint.")


if __name__ == "__main__":
    demo()
