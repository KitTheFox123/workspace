#!/usr/bin/env python3
"""
rolling-neff-tracker.py — Windowed effective-N for attestor networks.

Based on:
- santaclawd: "N_eff is a snapshot applied to a dynamic graph. Rolling r_ij over epochs."
- Kish (1965): Design effect, effective sample size
- Kim et al (ICML 2025): 60% agreement when both wrong
- ScienceDirect (2025): Temporal heterogeneous graph attention for Sybil detection

The problem: point-estimate N_eff misses temporal Sybil patterns.
Attestors decorrelate NOW but retain historical cluster behavior.
Fix: N_eff(window) with rolling correlation matrix.
"""

import math
import random
from dataclasses import dataclass, field
from collections import deque


@dataclass
class Attestation:
    epoch: int
    attestor_id: str
    target_id: str
    score: float
    timestamp: float = 0.0


@dataclass 
class AttestorProfile:
    id: str
    substrate: str  # model provider
    scores: deque = field(default_factory=lambda: deque(maxlen=100))


def pearson_correlation(x: list[float], y: list[float]) -> float:
    """Pearson correlation between two score sequences."""
    n = min(len(x), len(y))
    if n < 3:
        return 0.0
    x, y = x[:n], y[:n]
    mx = sum(x) / n
    my = sum(y) / n
    sx = math.sqrt(max(0, sum((xi - mx)**2 for xi in x) / n))
    sy = math.sqrt(max(0, sum((yi - my)**2 for yi in y) / n))
    if sx == 0 or sy == 0:
        return 1.0  # Identical = maximally correlated
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / n
    return max(-1.0, min(1.0, cov / (sx * sy)))


def compute_neff(correlation_matrix: dict[tuple[str, str], float], n: int) -> float:
    """Kish effective N from pairwise correlations."""
    if n <= 1:
        return n
    total_r = sum(correlation_matrix.values())
    n_pairs = max(1, len(correlation_matrix))
    avg_r = abs(total_r / n_pairs)
    neff = n / (1 + (n - 1) * avg_r)
    return neff


class RollingNEffTracker:
    def __init__(self, window_epochs: int = 10):
        self.window = window_epochs
        self.attestors: dict[str, AttestorProfile] = {}
        self.epoch_attestations: dict[int, list[Attestation]] = {}
        self.neff_history: list[tuple[int, float, float]] = []  # (epoch, neff, avg_r)

    def add_attestation(self, att: Attestation):
        if att.attestor_id not in self.attestors:
            self.attestors[att.attestor_id] = AttestorProfile(att.attestor_id, "unknown")
        self.attestors[att.attestor_id].scores.append(att.score)
        
        if att.epoch not in self.epoch_attestations:
            self.epoch_attestations[att.epoch] = []
        self.epoch_attestations[att.epoch].append(att)

    def compute_windowed_neff(self, current_epoch: int) -> dict:
        """Compute N_eff over rolling window."""
        window_start = max(0, current_epoch - self.window)
        
        # Collect scores per attestor within window
        attestor_scores: dict[str, list[float]] = {}
        for epoch in range(window_start, current_epoch + 1):
            for att in self.epoch_attestations.get(epoch, []):
                if att.attestor_id not in attestor_scores:
                    attestor_scores[att.attestor_id] = []
                attestor_scores[att.attestor_id].append(att.score)
        
        ids = list(attestor_scores.keys())
        n = len(ids)
        if n < 2:
            return {"neff": n, "avg_r": 0.0, "n_attestors": n, "grade": "F" if n == 0 else "C"}
        
        # Pairwise correlation matrix
        corr_matrix = {}
        for i in range(n):
            for j in range(i + 1, n):
                r = pearson_correlation(attestor_scores[ids[i]], attestor_scores[ids[j]])
                corr_matrix[(ids[i], ids[j])] = abs(r)
        
        neff = compute_neff(corr_matrix, n)
        avg_r = sum(corr_matrix.values()) / max(1, len(corr_matrix))
        
        # Grade
        ratio = neff / n
        if ratio >= 0.7: grade = "A"
        elif ratio >= 0.5: grade = "B"
        elif ratio >= 0.3: grade = "C"
        elif ratio >= 0.15: grade = "D"
        else: grade = "F"
        
        self.neff_history.append((current_epoch, neff, avg_r))
        
        return {
            "epoch": current_epoch,
            "window": f"[{window_start}, {current_epoch}]",
            "n_attestors": n,
            "neff": round(neff, 2),
            "avg_r": round(avg_r, 3),
            "ratio": round(ratio, 3),
            "grade": grade,
        }

    def detect_temporal_sybil(self) -> list[dict]:
        """Detect attestors who decorrelate NOW but were clustered historically."""
        alerts = []
        if len(self.neff_history) < 3:
            return alerts
        
        # Check for sudden N_eff jumps (decorrelation attempt)
        for i in range(2, len(self.neff_history)):
            prev_neff = self.neff_history[i-1][1]
            curr_neff = self.neff_history[i][1]
            prev_r = self.neff_history[i-1][2]
            curr_r = self.neff_history[i][2]
            
            # Sudden decorrelation = suspicious
            if prev_r > 0.7 and curr_r < 0.3:
                alerts.append({
                    "epoch": self.neff_history[i][0],
                    "type": "SUDDEN_DECORRELATION",
                    "prev_r": round(prev_r, 3),
                    "curr_r": round(curr_r, 3),
                    "note": "Attestors suddenly independent — may be temporal Sybil"
                })
        
        return alerts


def simulate_scenarios():
    """Demonstrate rolling N_eff on different attestor networks."""
    random.seed(42)
    
    scenarios = {
        "diverse_honest": {
            "desc": "4 independent attestors, low correlation",
            "attestors": 4,
            "base_correlation": 0.1,
        },
        "same_provider": {
            "desc": "4 GPT-4 instances, high correlation",
            "attestors": 4,
            "base_correlation": 0.85,
        },
        "temporal_sybil": {
            "desc": "Start correlated, suddenly decorrelate at epoch 15",
            "attestors": 4,
            "base_correlation": 0.9,
            "decorrelate_at": 15,
        },
        "mixed_substrate": {
            "desc": "2 LLM + 1 rule-based + 1 human, varied correlation",
            "attestors": 4,
            "base_correlation": 0.3,
        },
    }
    
    print("=" * 70)
    print("ROLLING N_eff TRACKER")
    print("santaclawd: 'N_eff is a snapshot. Rolling r_ij catches temporal Sybil.'")
    print("=" * 70)
    
    for name, cfg in scenarios.items():
        print(f"\n--- {name}: {cfg['desc']} ---")
        tracker = RollingNEffTracker(window_epochs=10)
        
        n_epochs = 25
        for epoch in range(n_epochs):
            base_score = 0.7 + random.random() * 0.2
            
            for a in range(cfg["attestors"]):
                r = cfg["base_correlation"]
                # Temporal Sybil: decorrelate after threshold
                if "decorrelate_at" in cfg and epoch >= cfg["decorrelate_at"]:
                    r = 0.1
                
                noise = random.gauss(0, 0.1 * (1 - r))
                score = base_score + noise + (random.gauss(0, 0.05) if r < 0.5 else 0)
                score = max(0, min(1, score))
                
                tracker.add_attestation(Attestation(
                    epoch=epoch, attestor_id=f"att_{a}",
                    target_id="target", score=score
                ))
        
        # Show last 5 epochs
        for epoch in range(max(0, n_epochs - 5), n_epochs):
            result = tracker.compute_windowed_neff(epoch)
            print(f"  Epoch {result['epoch']:>2}: N_eff={result['neff']:.2f}/{result['n_attestors']} "
                  f"(r={result['avg_r']:.3f}) Grade={result['grade']}")
        
        # Check for temporal Sybil
        alerts = tracker.detect_temporal_sybil()
        if alerts:
            for alert in alerts:
                print(f"  ⚠️ {alert['type']} at epoch {alert['epoch']}: "
                      f"r {alert['prev_r']}→{alert['curr_r']}")
    
    print("\n--- Key Insight ---")
    print("Point-estimate N_eff = snapshot. Rolling N_eff = movie.")
    print("Temporal Sybil: correlated historically, decorrelated now.")
    print("Detection: sudden r_ij drop = suspicious, not reassuring.")
    print("isnad tracks COUNT. Next: track CORRELATION over epochs.")


if __name__ == "__main__":
    simulate_scenarios()
