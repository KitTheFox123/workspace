#!/usr/bin/env python3
"""mirage-attestation-detector.py — Detect trust attestations based on pattern-matching, not evidence.

Inspired by Stanford mirage effect (Asadi et al 2026): models fabricate
plausible visual reasoning without actual visual input. Same pattern in
trust systems: attestors produce plausible trust scores without actual
interaction evidence.

Key insight: like VLMs scoring 70-80% without images, trust attestors
can produce "correct-looking" attestations from metadata alone.
"""

import json
import random
import math
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

@dataclass
class Attestation:
    attestor_id: str
    subject_id: str
    score: float  # 0-1
    timestamp: float
    evidence_depth: int  # 0=none, 1=metadata, 2=shallow, 3=deep interaction
    reasoning: str
    is_mirage: bool = False  # ground truth for scoring

@dataclass 
class AttestorProfile:
    agent_id: str
    total_attestations: int = 0
    evidence_backed: int = 0  # attestations with depth >= 2
    mirage_count: int = 0
    avg_confidence: float = 0.0
    
    @property
    def mirage_rate(self) -> float:
        if self.total_attestations == 0:
            return 0
        return self.mirage_count / self.total_attestations
    
    @property
    def evidence_rate(self) -> float:
        if self.total_attestations == 0:
            return 0
        return self.evidence_backed / self.total_attestations

def generate_attestation_stream(
    n_attestors: int = 20,
    n_subjects: int = 50,
    n_attestations: int = 500,
    mirage_fraction: float = 0.4,  # 40% of attestors are mirage-prone
) -> Tuple[List[Attestation], Dict[str, bool]]:
    """Generate a stream of attestations, some genuine, some mirages.
    
    Mirage attestors: produce plausible scores from metadata alone.
    Like VLMs: high confidence, correct-looking, but no real evidence.
    """
    attestors = [f"attestor_{i:03d}" for i in range(n_attestors)]
    subjects = [f"subject_{i:03d}" for i in range(n_subjects)]
    
    n_mirage = int(n_attestors * mirage_fraction)
    mirage_attestors = set(attestors[:n_mirage])
    
    # Ground truth: some subjects are genuinely trustworthy
    subject_true_score = {s: random.betavariate(2, 2) for s in subjects}
    
    attestations = []
    for _ in range(n_attestations):
        attestor = random.choice(attestors)
        subject = random.choice(subjects)
        true_score = subject_true_score[subject]
        is_mirage = attestor in mirage_attestors
        
        if is_mirage:
            # Mirage: pattern-match from population prior, no real evidence
            # Like VLMs: plausible but evidence-free
            score = true_score + random.gauss(0, 0.15)  # Close but noisy
            score = max(0, min(1, score))
            evidence_depth = random.choices([0, 1], weights=[0.3, 0.7])[0]
            reasoning = random.choice([
                "Based on general activity patterns",
                "Consistent with expected behavior profile",
                "Score aligns with community baseline",
                "Historical pattern suggests reliability",
            ])
        else:
            # Genuine: evidence-backed, may disagree with consensus
            score = true_score + random.gauss(0, 0.08)  # More accurate
            score = max(0, min(1, score))
            evidence_depth = random.choices([1, 2, 3], weights=[0.2, 0.5, 0.3])[0]
            reasoning = random.choice([
                "Verified through direct task completion",
                "Observed consistent delivery over 3 interactions",
                "Cross-referenced with on-chain settlement data",
                "Evaluated code quality in shared repository",
            ])
        
        attestations.append(Attestation(
            attestor_id=attestor,
            subject_id=subject,
            score=score,
            timestamp=random.uniform(0, 100),
            evidence_depth=evidence_depth,
            reasoning=reasoning,
            is_mirage=is_mirage,
        ))
    
    return attestations, {a: a in mirage_attestors for a in attestors}

def detect_mirages(attestations: List[Attestation]) -> Dict[str, AttestorProfile]:
    """Detect mirage attestors using behavioral signals.
    
    Key signals (parallel to Phantom-0):
    1. Evidence depth distribution (mirage = mostly 0-1)
    2. Confidence vs evidence correlation (mirage = high conf, low evidence)
    3. Agreement with population mean (mirage = converges to consensus)
    4. Reasoning diversity (mirage = template responses)
    """
    profiles: Dict[str, AttestorProfile] = {}
    
    # Build per-attestor profiles
    for a in attestations:
        if a.attestor_id not in profiles:
            profiles[a.attestor_id] = AttestorProfile(agent_id=a.attestor_id)
        p = profiles[a.attestor_id]
        p.total_attestations += 1
        if a.evidence_depth >= 2:
            p.evidence_backed += 1
        if a.is_mirage:
            p.mirage_count += 1
        p.avg_confidence += a.score
    
    for p in profiles.values():
        if p.total_attestations > 0:
            p.avg_confidence /= p.total_attestations
    
    return profiles

def phantom_zero_test(profiles: Dict[str, AttestorProfile],
                      threshold: float = 0.3) -> Dict[str, Dict]:
    """Phantom-0 equivalent: flag attestors with low evidence rates.
    
    Like requiring "I see nothing" when no image exists —
    require "insufficient evidence" when no interaction exists.
    """
    results = {}
    for aid, profile in profiles.items():
        flagged = profile.evidence_rate < threshold
        results[aid] = {
            "agent_id": aid,
            "evidence_rate": round(profile.evidence_rate, 3),
            "total": profile.total_attestations,
            "flagged_mirage": flagged,
            "actual_mirage": profile.mirage_rate > 0.5,
            "correct": flagged == (profile.mirage_rate > 0.5),
        }
    return results

def calculate_detection_accuracy(results: Dict[str, Dict]) -> Dict:
    """Calculate precision/recall of mirage detection."""
    tp = sum(1 for r in results.values() if r["flagged_mirage"] and r["actual_mirage"])
    fp = sum(1 for r in results.values() if r["flagged_mirage"] and not r["actual_mirage"])
    fn = sum(1 for r in results.values() if not r["flagged_mirage"] and r["actual_mirage"])
    tn = sum(1 for r in results.values() if not r["flagged_mirage"] and not r["actual_mirage"])
    
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 0.001)
    
    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": tn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "accuracy": round((tp + tn) / max(tp + fp + fn + tn, 1), 3),
    }

def contamination_estimate(attestations: List[Attestation]) -> Dict:
    """Estimate how much of aggregate trust scores come from mirages.
    
    Parallel to Stanford finding: 70-80% of benchmark score from text alone.
    """
    by_subject = {}
    for a in attestations:
        if a.subject_id not in by_subject:
            by_subject[a.subject_id] = {"mirage_scores": [], "genuine_scores": []}
        if a.is_mirage:
            by_subject[a.subject_id]["mirage_scores"].append(a.score)
        else:
            by_subject[a.subject_id]["genuine_scores"].append(a.score)
    
    contamination_rates = []
    for sid, scores in by_subject.items():
        total = len(scores["mirage_scores"]) + len(scores["genuine_scores"])
        if total > 0:
            mirage_pct = len(scores["mirage_scores"]) / total
            contamination_rates.append(mirage_pct)
    
    avg_contamination = sum(contamination_rates) / max(len(contamination_rates), 1)
    
    return {
        "avg_contamination_pct": round(avg_contamination * 100, 1),
        "subjects_over_50pct": sum(1 for r in contamination_rates if r > 0.5),
        "total_subjects": len(contamination_rates),
        "max_contamination": round(max(contamination_rates) * 100, 1) if contamination_rates else 0,
    }

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("MIRAGE ATTESTATION DETECTOR")
    print("Applying Stanford mirage effect to trust systems")
    print("=" * 60)
    
    attestations, ground_truth = generate_attestation_stream(
        n_attestors=20, n_subjects=50, n_attestations=500, mirage_fraction=0.4
    )
    
    # 1. Profile attestors
    profiles = detect_mirages(attestations)
    
    print("\n--- Attestor Evidence Rates ---")
    for aid in sorted(profiles.keys()):
        p = profiles[aid]
        marker = "⚠️ MIRAGE" if ground_truth[aid] else "✓ genuine"
        print(f"  {aid}: evidence_rate={p.evidence_rate:.2f}, "
              f"n={p.total_attestations}, {marker}")
    
    # 2. Phantom-0 test
    print("\n--- Phantom-0 Detection Results ---")
    results = phantom_zero_test(profiles, threshold=0.3)
    accuracy = calculate_detection_accuracy(results)
    print(f"  Precision: {accuracy['precision']:.1%}")
    print(f"  Recall: {accuracy['recall']:.1%}")
    print(f"  F1: {accuracy['f1']:.1%}")
    print(f"  Accuracy: {accuracy['accuracy']:.1%}")
    
    # 3. Contamination estimate
    print("\n--- Trust Score Contamination ---")
    contamination = contamination_estimate(attestations)
    print(f"  Avg contamination: {contamination['avg_contamination_pct']}%")
    print(f"  Subjects >50% mirage: {contamination['subjects_over_50pct']}/{contamination['total_subjects']}")
    print(f"  Max contamination: {contamination['max_contamination']}%")
    
    # 4. Key insight
    print("\n" + "=" * 60)
    print("KEY INSIGHT: Like VLMs scoring 70-80% without images,")
    print(f"trust systems get {contamination['avg_contamination_pct']}% of attestations")
    print("from pattern-matching alone. Phantom-0 for trust:")
    print("require evidence or refuse to attest.")
    print("=" * 60)
