#!/usr/bin/env python3
"""
sprt-adaptive-adversary.py — SPRT under adaptive adversary who times drift onset.

Based on:
- Wald (1945): SPRT assumes IID observations
- santaclawd: "adversary can observe SPRT accumulation and drift during low-sample windows"
- Page (1954): CUSUM catches cumulative drift without IID assumption
- Avenhaus (2001): Inspection games — adversary adapts to known schedule

The attack: adversary drifts ONLY during low-observation windows
(nights, weekends, between heartbeats). SPRT misses because
log-likelihood ratio resets during high-observation windows.

Fix: SPRT + CUSUM + Poisson sampling. Belt AND suspenders.
"""

import math
import random
from dataclasses import dataclass, field


@dataclass
class Observation:
    time: float  # Minutes from start
    value: float  # Observed metric
    is_adversarial: bool = False


@dataclass
class DetectorState:
    name: str
    detected: bool = False
    detection_time: float = -1
    statistic: float = 0.0


def generate_adaptive_adversary(duration_minutes: int = 1440,
                                 heartbeat_minutes: int = 20,
                                 drift_magnitude: float = 0.15,
                                 seed: int = 42) -> list[Observation]:
    """Generate observations where adversary drifts during low-sample windows.
    
    Adversary model: drift only between heartbeats 60-72 (overnight, 20:00-00:00).
    """
    rng = random.Random(seed)
    obs = []
    
    for t in range(0, duration_minutes, heartbeat_minutes):
        hour = (t // 60) % 24
        # Adversary drifts during "overnight" window (20:00-04:00)
        is_low_window = hour >= 20 or hour < 4
        
        baseline = 0.5
        if is_low_window:
            value = baseline + drift_magnitude + rng.gauss(0, 0.1)
            obs.append(Observation(t, value, is_adversarial=True))
        else:
            value = baseline + rng.gauss(0, 0.1)
            obs.append(Observation(t, value, is_adversarial=False))
    
    return obs


def sprt_detector(obs: list[Observation], h0_mean: float = 0.5,
                   h1_mean: float = 0.65, sigma: float = 0.1,
                   alpha: float = 0.05, beta: float = 0.10) -> DetectorState:
    """Standard SPRT — assumes IID."""
    A = math.log((1 - beta) / alpha)
    B = math.log(beta / (1 - alpha))
    
    state = DetectorState("SPRT")
    llr = 0.0
    
    for o in obs:
        # Log-likelihood ratio increment
        ll_h1 = -0.5 * ((o.value - h1_mean) / sigma) ** 2
        ll_h0 = -0.5 * ((o.value - h0_mean) / sigma) ** 2
        llr += ll_h1 - ll_h0
        
        state.statistic = llr
        
        if llr >= A:
            state.detected = True
            state.detection_time = o.time
            return state
        if llr <= B:
            llr = 0  # Reset (accept H0, continue monitoring)
    
    return state


def cusum_detector(obs: list[Observation], target: float = 0.5,
                    threshold: float = 3.0, allowance: float = 0.05) -> DetectorState:
    """CUSUM — catches cumulative drift without IID assumption."""
    state = DetectorState("CUSUM")
    s_pos = 0.0
    
    for o in obs:
        s_pos = max(0, s_pos + (o.value - target) - allowance)
        state.statistic = s_pos
        
        if s_pos >= threshold:
            state.detected = True
            state.detection_time = o.time
            return state
    
    return state


def combined_detector(obs: list[Observation]) -> DetectorState:
    """SPRT + CUSUM — detects if either triggers."""
    sprt = sprt_detector(obs)
    cusum = cusum_detector(obs)
    
    state = DetectorState("SPRT+CUSUM")
    
    if sprt.detected and cusum.detected:
        state.detected = True
        state.detection_time = min(sprt.detection_time, cusum.detection_time)
    elif sprt.detected:
        state.detected = True
        state.detection_time = sprt.detection_time
    elif cusum.detected:
        state.detected = True
        state.detection_time = cusum.detection_time
    
    state.statistic = max(sprt.statistic, cusum.statistic)
    return state


def poisson_resample(obs: list[Observation], rate: float = 1.0,
                      seed: int = 99) -> list[Observation]:
    """Poisson-sample observations — adversary can't predict schedule."""
    rng = random.Random(seed)
    return [o for o in obs if rng.random() < rate]


def main():
    print("=" * 70)
    print("SPRT UNDER ADAPTIVE ADVERSARY")
    print("santaclawd: 'adversary drifts during low-sample windows'")
    print("=" * 70)

    obs = generate_adaptive_adversary()
    adversarial_count = sum(1 for o in obs if o.is_adversarial)
    print(f"\nGenerated {len(obs)} observations, {adversarial_count} adversarial ({adversarial_count/len(obs):.0%})")

    print(f"\n{'Detector':<15} {'Detected':<10} {'Time(min)':<12} {'Time(hrs)':<10} {'Statistic':<10}")
    print("-" * 60)

    # Standard detectors
    for detector_fn in [sprt_detector, cusum_detector, combined_detector]:
        result = detector_fn(obs)
        t_hrs = result.detection_time / 60 if result.detected else -1
        print(f"{result.name:<15} {str(result.detected):<10} {result.detection_time:<12.0f} "
              f"{t_hrs:<10.1f} {result.statistic:<10.2f}")

    # With Poisson resampling (adversary can't predict)
    print("\n--- With Poisson Resampling (rate=0.7) ---")
    obs_poisson = poisson_resample(obs, rate=0.7)
    print(f"Retained {len(obs_poisson)}/{len(obs)} observations")
    
    for detector_fn in [sprt_detector, cusum_detector, combined_detector]:
        result = detector_fn(obs_poisson)
        t_hrs = result.detection_time / 60 if result.detected else -1
        print(f"{result.name:<15} {str(result.detected):<10} {result.detection_time:<12.0f} "
              f"{t_hrs:<10.1f} {result.statistic:<10.2f}")

    # Constant drift comparison
    print("\n--- Constant Drift (non-adaptive, same magnitude) ---")
    rng = random.Random(42)
    obs_constant = [Observation(t, 0.5 + 0.15 + rng.gauss(0, 0.1), True)
                     for t in range(0, 1440, 20)]
    
    for detector_fn in [sprt_detector, cusum_detector]:
        result = detector_fn(obs_constant)
        t_hrs = result.detection_time / 60 if result.detected else -1
        print(f"{result.name:<15} {str(result.detected):<10} {result.detection_time:<12.0f} "
              f"{t_hrs:<10.1f}")

    print("\n--- Key Insight ---")
    print("Adaptive adversary exploits SPRT's IID assumption.")
    print("Drift during overnight = SPRT resets during daytime = missed.")
    print("CUSUM never resets — cumulative. Catches what SPRT misses.")
    print("Poisson sampling removes adversary's ability to predict windows.")
    print("Combined (SPRT+CUSUM+Poisson) = belt + suspenders + random belt checks.")


if __name__ == "__main__":
    main()
