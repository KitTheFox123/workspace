#!/usr/bin/env python3
"""baseline-poisoning-detector.py — Detect adversarial concept drift in agent monitoring.

Distinguishes real concept drift from adversarial baseline poisoning.
Based on PMC9162121 (Krawczyk et al 2022): adversarial concept drift detection
under poisoning attacks for robust data stream mining.

Two attack types:
1. False adaptation: poison injected during stable period → false alarm → unnecessary adaptation
2. Impaired adaptation: poison injected during real drift → confusion → slow/failed adaptation

Detection: compare drift signal against immutable genesis anchor. If genesis-anchored
distance is stable but rolling-window detector fires, the drift is adversarial
(baseline was poisoned, not the data source).

Usage:
    python3 baseline-poisoning-detector.py [--demo]
"""

import argparse
import hashlib
import json
import math
import random
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class DriftSignal:
    """A single observation in the behavioral stream."""
    cycle: int
    value: float
    timestamp: str


@dataclass
class DetectionResult:
    """Result of poisoning detection."""
    cycle: int
    rolling_drift: bool      # Rolling window says drift
    genesis_drift: bool      # Genesis anchor says drift
    diagnosis: str            # real_drift | adversarial_poison | stable | masked_drift
    severity: int             # 0-5
    rolling_distance: float
    genesis_distance: float
    confidence: float


class BaselinePoisoningDetector:
    """Detects adversarial baseline poisoning vs real concept drift."""
    
    def __init__(self, genesis_window: int = 5, ewma_lambda: float = 0.1,
                 drift_threshold: float = 2.0):
        self.genesis_window = genesis_window
        self.ewma_lambda = ewma_lambda
        self.drift_threshold = drift_threshold
        self.genesis_values: List[float] = []
        self.genesis_mean: Optional[float] = None
        self.genesis_std: Optional[float] = None
        self.genesis_hash: Optional[str] = None
        self.ewma: Optional[float] = None
        self.ewma_var: float = 0.0
        self.observations: List[float] = []
        self.results: List[DetectionResult] = []
    
    def _freeze_genesis(self):
        """Freeze immutable genesis baseline."""
        self.genesis_mean = sum(self.genesis_values) / len(self.genesis_values)
        variance = sum((v - self.genesis_mean) ** 2 for v in self.genesis_values) / len(self.genesis_values)
        self.genesis_std = max(math.sqrt(variance), 0.01)
        raw = ",".join(f"{v:.6f}" for v in self.genesis_values)
        self.genesis_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]
    
    def observe(self, cycle: int, value: float) -> DetectionResult:
        """Process one observation, return detection result."""
        self.observations.append(value)
        
        # Genesis window: collect and freeze
        if len(self.genesis_values) < self.genesis_window:
            self.genesis_values.append(value)
            if len(self.genesis_values) == self.genesis_window:
                self._freeze_genesis()
                self.ewma = self.genesis_mean
            return DetectionResult(
                cycle=cycle, rolling_drift=False, genesis_drift=False,
                diagnosis="genesis_collection", severity=0,
                rolling_distance=0.0, genesis_distance=0.0, confidence=0.0
            )
        
        # Update EWMA
        self.ewma = self.ewma_lambda * value + (1 - self.ewma_lambda) * self.ewma
        
        # Rolling distance (EWMA vs current)
        rolling_distance = abs(value - self.ewma) / self.genesis_std
        
        # Genesis distance (genesis mean vs current)
        genesis_distance = abs(value - self.genesis_mean) / self.genesis_std
        
        rolling_drift = rolling_distance > self.drift_threshold
        genesis_drift = genesis_distance > self.drift_threshold
        
        # Diagnosis matrix (PMC9162121 taxonomy):
        # rolling=T, genesis=T → real drift (data source changed)
        # rolling=T, genesis=F → adversarial poison (baseline was shifted)
        # rolling=F, genesis=T → masked drift (slow poisoning shifted baseline to match drift)
        # rolling=F, genesis=F → stable
        
        if rolling_drift and genesis_drift:
            diagnosis = "real_drift"
            severity = 3
        elif rolling_drift and not genesis_drift:
            diagnosis = "adversarial_poison"
            severity = 5  # Most dangerous — false adaptation triggered
        elif not rolling_drift and genesis_drift:
            diagnosis = "masked_drift"
            severity = 4  # Baseline poisoned to mask real drift
        else:
            diagnosis = "stable"
            severity = 0
        
        confidence = min(1.0, max(rolling_distance, genesis_distance) / (self.drift_threshold * 2))
        
        result = DetectionResult(
            cycle=cycle, rolling_drift=rolling_drift, genesis_drift=genesis_drift,
            diagnosis=diagnosis, severity=severity,
            rolling_distance=round(rolling_distance, 3),
            genesis_distance=round(genesis_distance, 3),
            confidence=round(confidence, 3)
        )
        self.results.append(result)
        return result
    
    def summary(self) -> dict:
        """Generate detection summary."""
        diagnoses = {}
        for r in self.results:
            diagnoses[r.diagnosis] = diagnoses.get(r.diagnosis, 0) + 1
        
        poison_count = diagnoses.get("adversarial_poison", 0)
        masked_count = diagnoses.get("masked_drift", 0)
        real_count = diagnoses.get("real_drift", 0)
        total = len(self.results)
        
        attack_ratio = (poison_count + masked_count) / max(total, 1)
        
        if attack_ratio > 0.3:
            grade = "F"
        elif attack_ratio > 0.15:
            grade = "D"
        elif attack_ratio > 0.05:
            grade = "C"
        elif poison_count + masked_count > 0:
            grade = "B"
        else:
            grade = "A"
        
        return {
            "genesis_hash": self.genesis_hash,
            "total_observations": len(self.observations),
            "diagnoses": diagnoses,
            "attack_ratio": round(attack_ratio, 3),
            "grade": grade,
            "recommendation": {
                "F": "Active baseline poisoning detected. Reset to genesis anchor. Investigate source.",
                "D": "Significant adversarial drift. Increase monitoring frequency.",
                "C": "Some adversarial signals. Review baseline integrity.",
                "B": "Minor anomalies. Continue monitoring.",
                "A": "Clean stream. No adversarial drift detected."
            }[grade]
        }


def demo():
    """Run demo with 3 scenarios."""
    random.seed(42)
    
    scenarios = [
        {
            "name": "Clean stream (no attack)",
            "gen": lambda c: 1.0 + random.gauss(0, 0.1)
        },
        {
            "name": "Adversarial baseline poisoning",
            "gen": lambda c: 1.0 + random.gauss(0, 0.1) + (0.02 * max(0, c - 10))  # slow baseline shift
        },
        {
            "name": "Real concept drift at cycle 20",
            "gen": lambda c: (1.0 if c < 20 else 2.5) + random.gauss(0, 0.1)
        },
    ]
    
    for scenario in scenarios:
        print(f"\n{'=' * 50}")
        print(f"Scenario: {scenario['name']}")
        print(f"{'=' * 50}")
        
        detector = BaselinePoisoningDetector(genesis_window=5, drift_threshold=1.5)
        
        for cycle in range(30):
            value = scenario["gen"](cycle)
            result = detector.observe(cycle, value)
            
            if result.diagnosis not in ("stable", "genesis_collection"):
                print(f"  Cycle {cycle:2d}: {result.diagnosis} "
                      f"(rolling={result.rolling_distance:.2f}, "
                      f"genesis={result.genesis_distance:.2f}, "
                      f"sev={result.severity})")
        
        summary = detector.summary()
        print(f"\n  Grade: {summary['grade']}")
        print(f"  Diagnoses: {summary['diagnoses']}")
        print(f"  Attack ratio: {summary['attack_ratio']}")
        print(f"  Recommendation: {summary['recommendation']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Adversarial baseline poisoning detector")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        # Run all scenarios, output JSON
        random.seed(42)
        detector = BaselinePoisoningDetector()
        for c in range(30):
            v = 1.0 + random.gauss(0, 0.1) + (0.02 * max(0, c - 10))
            detector.observe(c, v)
        print(json.dumps(detector.summary(), indent=2))
    else:
        demo()
