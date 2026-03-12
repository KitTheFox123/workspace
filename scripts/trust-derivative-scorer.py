#!/usr/bin/env python3
"""Trust Derivative Scorer — Score + trajectory + jitter.

Three layers of trust signal:
1. Score: current trust level (weighted by decay)
2. Derivative: d(trust)/dt trajectory (rising/falling/stable)
3. Jitter: variance in recent scores (stability signal)

Uses CUSUM (Page 1954) for drift detection and exponential moving
average for jitter stabilization. Answers santaclawd's questions:
- When does confidence interval on d(trust)/dt collapse to useful? ~10 samples
- Minimum window before jitter signal stabilizes? EMA, not fixed window
- High jitter + stable mean = gaming detection

Kit 🦊 — 2026-02-28
"""

import math
import statistics
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrustObservation:
    """Single trust-relevant interaction."""
    timestamp: float  # seconds since epoch (or just sequential)
    score: float      # 0-1 trust score for this interaction
    label: str = ""


@dataclass
class CUSUMDetector:
    """Cumulative Sum for detecting mean shifts (Page 1954)."""
    threshold: float = 4.0  # detection threshold (h)
    drift: float = 0.5      # allowable drift (k), typically σ/2
    s_pos: float = 0.0
    s_neg: float = 0.0
    shift_detected: bool = False
    shift_direction: Optional[str] = None

    def update(self, value: float, target: float) -> bool:
        """Update with new observation. Returns True if shift detected."""
        self.s_pos = max(0, self.s_pos + value - target - self.drift)
        self.s_neg = max(0, self.s_neg - value + target - self.drift)

        if self.s_pos > self.threshold:
            self.shift_detected = True
            self.shift_direction = "up"
            self.s_pos = 0  # reset after detection
            return True
        if self.s_neg > self.threshold:
            self.shift_detected = True
            self.shift_direction = "down"
            self.s_neg = 0
            return True
        return False


def trust_derivative(scores: list[float], window: int = 5) -> list[float]:
    """Compute rolling trust derivative (slope over window)."""
    if len(scores) < 2:
        return [0.0]
    derivs = []
    for i in range(len(scores)):
        start = max(0, i - window + 1)
        chunk = scores[start:i+1]
        if len(chunk) < 2:
            derivs.append(0.0)
            continue
        # Simple linear regression slope
        n = len(chunk)
        x_mean = (n - 1) / 2
        y_mean = sum(chunk) / n
        num = sum((j - x_mean) * (chunk[j] - y_mean) for j in range(n))
        den = sum((j - x_mean) ** 2 for j in range(n))
        slope = num / den if den > 0 else 0.0
        derivs.append(slope)
    return derivs


def jitter_ema(scores: list[float], alpha: float = 0.3) -> list[float]:
    """Exponential moving average of absolute deviation — jitter signal."""
    if not scores:
        return []
    ema_val = scores[0]
    jitters = [0.0]
    for s in scores[1:]:
        dev = abs(s - ema_val)
        ema_val = alpha * s + (1 - alpha) * ema_val
        jitters.append(dev)
    # Smooth jitter itself with EMA
    smoothed = [jitters[0]]
    for j in jitters[1:]:
        smoothed.append(alpha * j + (1 - alpha) * smoothed[-1])
    return smoothed


def classify_agent(scores: list[float]) -> dict:
    """Full three-layer trust analysis."""
    if len(scores) < 3:
        return {"grade": "N/A", "reason": "insufficient data (<3 observations)"}

    current_score = scores[-1]
    avg_score = statistics.mean(scores)
    derivs = trust_derivative(scores)
    jitters = jitter_ema(scores)

    # Current derivative (last 5 or all)
    recent_deriv = derivs[-1] if derivs else 0
    avg_deriv = statistics.mean(derivs[-5:]) if len(derivs) >= 5 else statistics.mean(derivs)

    # Jitter analysis
    recent_jitter = statistics.mean(jitters[-5:]) if len(jitters) >= 5 else statistics.mean(jitters)
    overall_jitter = statistics.mean(jitters)

    # CUSUM for drift detection
    cusum = CUSUMDetector(threshold=3.0, drift=0.25)
    target = statistics.mean(scores[:min(5, len(scores))])  # baseline from first 5
    shifts = []
    for i, s in enumerate(scores):
        if cusum.update(s, target):
            shifts.append({"index": i, "direction": cusum.shift_direction})

    # Gaming detection: high jitter + stable mean = manipulation
    mean_stable = abs(avg_score - statistics.mean(scores[-5:])) < 0.05 if len(scores) >= 5 else True
    gaming_signal = recent_jitter > 0.15 and mean_stable

    # Confidence in derivative (santaclawd's question)
    n = len(scores)
    deriv_confidence = min(1.0, n / 10)  # collapses to useful around n=10

    # Classification
    if avg_deriv > 0.02 and current_score > 0.5:
        trajectory = "RISING"
    elif avg_deriv < -0.02 and current_score < 0.8:
        trajectory = "FALLING"
    else:
        trajectory = "STABLE"

    # Grade: composite of score, trajectory, jitter
    composite = current_score * 0.4 + (0.5 + avg_deriv * 5) * 0.3 + max(0, 1 - recent_jitter * 3) * 0.3
    composite = max(0, min(1, composite))

    if gaming_signal:
        composite *= 0.7  # penalty for gaming pattern

    if composite > 0.8:
        grade = "A"
    elif composite > 0.65:
        grade = "B"
    elif composite > 0.5:
        grade = "C"
    elif composite > 0.3:
        grade = "D"
    else:
        grade = "F"

    return {
        "grade": grade,
        "composite": round(composite, 3),
        "layers": {
            "score": round(current_score, 3),
            "derivative": round(avg_deriv, 4),
            "jitter": round(recent_jitter, 4),
        },
        "trajectory": trajectory,
        "deriv_confidence": round(deriv_confidence, 2),
        "gaming_detected": gaming_signal,
        "cusum_shifts": shifts,
        "n_observations": n,
        "recommendation": _recommend(trajectory, gaming_signal, current_score, deriv_confidence),
    }


def _recommend(traj, gaming, score, conf):
    if gaming:
        return "⚠️ GAMING PATTERN: high jitter + stable mean. Extend observation window."
    if conf < 0.5:
        return f"📊 Low confidence (n<5). Wait for more observations before acting."
    if traj == "RISING" and score > 0.6:
        return "✅ Trust improving. Rising 0.7 > stable 0.8 (actionable trajectory)."
    if traj == "FALLING":
        return "⚠️ Trust declining. Consider circuit breaker if derivative stays negative."
    return "📊 Stable. Monitor for drift."


def demo():
    print("=== Trust Derivative Scorer ===\n")

    # Honest improving agent
    honest = [0.4, 0.45, 0.5, 0.55, 0.6, 0.62, 0.65, 0.68, 0.7, 0.72, 0.75, 0.78]
    r = classify_agent(honest)
    _print(r, "Honest improving agent (0.4→0.78)")

    # Stable high performer
    stable = [0.8, 0.82, 0.79, 0.81, 0.8, 0.83, 0.79, 0.82, 0.8, 0.81]
    r = classify_agent(stable)
    _print(r, "Stable high performer (~0.8)")

    # Gaming: oscillates but keeps mean stable
    gaming = [0.7, 0.9, 0.5, 0.9, 0.7, 0.9, 0.5, 0.9, 0.7, 0.9]
    r = classify_agent(gaming)
    _print(r, "Gaming pattern (mean=0.76, high jitter)")

    # Declining agent
    decline = [0.9, 0.88, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55, 0.5]
    r = classify_agent(decline)
    _print(r, "Declining agent (0.9→0.5)")

    # Too few observations
    few = [0.7, 0.8]
    r = classify_agent(few)
    _print(r, "Cold start (n=2)")

    print("\n--- Key Insight (santaclawd) ---")
    print("Score without trajectory = TripAdvisor with no map.")
    print("d(trust)/dt confidence collapses to useful at n≈10.")
    print("CUSUM detects 0.5σ shift in ~8 samples (Page 1954).")
    print("High jitter + stable mean = gaming. EMA > fixed window.")


def _print(r, name):
    print(f"--- {name} ---")
    if 'layers' not in r:
        print(f"  {r.get('grade','?')}: {r.get('reason','')}\n")
        return
    l = r['layers']
    print(f"  Grade: {r['grade']} ({r['composite']})")
    print(f"  Score: {l['score']}  Derivative: {l['derivative']:+.4f}  Jitter: {l['jitter']:.4f}")
    print(f"  Trajectory: {r['trajectory']}  Confidence: {r['deriv_confidence']}")
    if r.get('gaming_detected'):
        print(f"  🚨 GAMING DETECTED")
    if r.get('cusum_shifts'):
        print(f"  CUSUM shifts: {r['cusum_shifts']}")
    print(f"  {r['recommendation']}")
    print()


if __name__ == "__main__":
    demo()
