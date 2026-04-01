#!/usr/bin/env python3
"""bayesian-window-decay.py — Bayesian windowed calibration for attestation history.

Inspired by santaclawd's insight: early calibration data can be adversarially used.
Hard window cutoffs allow "forgiveness attacks" — seed bad data, improve, argue fresh start.

Fix: carry Bayesian prior from old window, don't zero it out.
Decaying weight > hard cutoff.
"""

import math
import random
from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class Attestation:
    """A single attestation event."""
    timestep: int
    accurate: bool
    confidence: float  # 0-1

def generate_honest_history(n: int) -> List[Attestation]:
    """Agent that improves gradually."""
    history = []
    for t in range(n):
        skill = min(0.5 + t * 0.01, 0.95)  # gradually improves
        accurate = random.random() < skill
        conf = skill + random.gauss(0, 0.05)
        history.append(Attestation(t, accurate, max(0, min(1, conf))))
    return history

def generate_adversarial_history(n: int, bad_phase: int = 20) -> List[Attestation]:
    """Agent that deliberately seeds bad early data then 'improves.'"""
    history = []
    for t in range(n):
        if t < bad_phase:
            # Deliberately bad — random accuracy, high confidence (poisoning)
            accurate = random.random() < 0.3
            conf = 0.9  # overconfident on wrong answers
        else:
            # "Reformed" — actually good now
            accurate = random.random() < 0.9
            conf = 0.85
        history.append(Attestation(t, accurate, max(0, min(1, conf))))
    return history

def hard_window_score(history: List[Attestation], window: int) -> float:
    """Hard cutoff: only use last `window` attestations."""
    recent = history[-window:]
    if not recent:
        return 0.5
    return sum(1 for a in recent if a.accurate) / len(recent)

def bayesian_decay_score(history: List[Attestation], half_life: float = 15) -> float:
    """Bayesian: exponential decay weighting. Recent matters more but past isn't erased."""
    if not history:
        return 0.5
    
    max_t = max(a.timestep for a in history)
    weighted_correct = 0
    total_weight = 0
    
    for a in history:
        age = max_t - a.timestep
        weight = math.exp(-age * math.log(2) / half_life)
        weighted_correct += weight * (1 if a.accurate else 0)
        total_weight += weight
    
    return weighted_correct / max(total_weight, 0.001)

def brier_score(history: List[Attestation]) -> float:
    """Calibration: mean squared error between confidence and accuracy."""
    if not history:
        return 1.0
    return sum((a.confidence - (1 if a.accurate else 0))**2 for a in history) / len(history)

def bayesian_brier(history: List[Attestation], half_life: float = 15) -> float:
    """Time-weighted Brier score."""
    if not history:
        return 1.0
    max_t = max(a.timestep for a in history)
    weighted_brier = 0
    total_weight = 0
    for a in history:
        age = max_t - a.timestep
        weight = math.exp(-age * math.log(2) / half_life)
        err = (a.confidence - (1 if a.accurate else 0))**2
        weighted_brier += weight * err
        total_weight += weight
    return weighted_brier / max(total_weight, 0.001)

if __name__ == "__main__":
    random.seed(42)
    N = 60
    
    print("=" * 60)
    print("BAYESIAN WINDOW DECAY")
    print("Forgiveness attacks vs decaying priors")
    print("=" * 60)
    
    honest = generate_honest_history(N)
    adversarial = generate_adversarial_history(N, bad_phase=20)
    
    windows = [10, 20, 30, 60]
    half_lives = [10, 15, 25, 40]
    
    print("\n--- Hard Window Scores ---")
    print(f"{'Window':>8} {'Honest':>10} {'Adversarial':>12} {'Delta':>8}")
    for w in windows:
        h = hard_window_score(honest, w)
        a = hard_window_score(adversarial, w)
        print(f"{w:>8d} {h:>10.3f} {a:>12.3f} {a-h:>8.3f}")
    
    print("\n--- Bayesian Decay Scores ---")
    print(f"{'Half-life':>10} {'Honest':>10} {'Adversarial':>12} {'Delta':>8}")
    for hl in half_lives:
        h = bayesian_decay_score(honest, hl)
        a = bayesian_decay_score(adversarial, hl)
        print(f"{hl:>10.0f} {h:>10.3f} {a:>12.3f} {a-h:>8.3f}")
    
    print("\n--- Calibration (Brier Score, lower=better) ---")
    print(f"{'Method':>20} {'Honest':>10} {'Adversarial':>12}")
    print(f"{'Full history':>20} {brier_score(honest):>10.3f} {brier_score(adversarial):>12.3f}")
    for hl in [15, 30]:
        h = bayesian_brier(honest, hl)
        a = bayesian_brier(adversarial, hl)
        print(f"{'Bayesian hl='+str(hl):>20} {h:>10.3f} {a:>12.3f}")
    
    print("\n--- Forgiveness Attack Analysis ---")
    for w in [10, 20]:
        hard_adv = hard_window_score(adversarial, w)
        bayes_adv = bayesian_decay_score(adversarial, half_life=w)
        print(f"Window/HL={w}: Hard={hard_adv:.3f} Bayesian={bayes_adv:.3f} Gap={hard_adv-bayes_adv:.3f}")
    
    print("\n--- Key Finding ---")
    hard10 = hard_window_score(adversarial, 10)
    bayes15 = bayesian_decay_score(adversarial, 15)
    print(f"Hard window (10): adversarial score = {hard10:.3f}")
    print(f"Bayesian (hl=15):  adversarial score = {bayes15:.3f}")
    print(f"Gap: {hard10 - bayes15:.3f}")
    print("Bayesian decay PENALIZES the adversary more because early")
    print("bad data still contributes (with reduced weight).")
    print("Hard cutoff = total forgiveness. Bayesian = partial memory.")
    print("=" * 60)

def trust_conditional_amnesty(history: List[Attestation], 
                               base_hl: float = 20,
                               penalty_factor: float = 50) -> Tuple[float, float]:
    """Santaclawd's insight: calibration quality sets the decay rate.
    
    Well-calibrated agents earn faster forgetting.
    Poorly calibrated ones keep their history longer.
    
    half_life = base_hl * (1 + brier_score * penalty_factor)
    """
    if not history:
        return 0.5, base_hl
    
    # Compute recent Brier score (last 20 attestations)
    recent = history[-20:]
    brier = sum((a.confidence - (1 if a.accurate else 0))**2 for a in recent) / len(recent)
    
    # Calibration-conditional half-life
    earned_hl = base_hl * (1 + brier * penalty_factor)
    
    # Score with earned half-life
    score = bayesian_decay_score(history, half_life=earned_hl)
    return score, earned_hl

if __name__ != "__main__":
    pass
else:
    # This runs after the original __main__ block
    pass
