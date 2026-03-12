#!/usr/bin/env python3
"""Trust Change Detector — Kalman for drift, CUSUM for jumps.

santaclawd: "Kalman is right for smooth drift but fails on step changes.
Adversarial agents won't drift gracefully — they'll flip."

Solution: dual detection. Kalman filter tracks smooth trust evolution,
Page's CUSUM (1954) catches step changes. Combined = robust.

Kit 🦊 — 2026-02-28
"""

import json
import math
from dataclasses import dataclass, field


@dataclass
class KalmanTrustFilter:
    """1D Kalman filter for trust score tracking."""
    estimate: float = 0.5       # Current trust estimate
    error_cov: float = 1.0      # Estimation uncertainty
    process_noise: float = 0.01  # How much trust naturally varies
    measurement_noise: float = 0.1  # How noisy observations are

    def update(self, measurement: float) -> dict:
        # Predict
        pred_estimate = self.estimate
        pred_error = self.error_cov + self.process_noise

        # Update
        kalman_gain = pred_error / (pred_error + self.measurement_noise)
        self.estimate = pred_estimate + kalman_gain * (measurement - pred_estimate)
        self.error_cov = (1 - kalman_gain) * pred_error

        innovation = measurement - pred_estimate  # surprise
        return {
            "estimate": round(self.estimate, 4),
            "gain": round(kalman_gain, 4),
            "innovation": round(innovation, 4),
            "uncertainty": round(self.error_cov, 4),
        }


@dataclass
class CUSUMDetector:
    """Page's CUSUM (1954) for step change detection."""
    threshold: float = 3.0   # Detection threshold (h)
    drift: float = 0.5       # Allowable drift (k)
    s_pos: float = 0.0       # Upper cumulative sum
    s_neg: float = 0.0       # Lower cumulative sum
    mean: float = 0.5        # Expected mean

    def update(self, value: float) -> dict:
        z = value - self.mean
        self.s_pos = max(0, self.s_pos + z - self.drift)
        self.s_neg = max(0, self.s_neg - z - self.drift)

        alarm = None
        if self.s_pos > self.threshold:
            alarm = "STEP_UP"
            self.s_pos = 0  # reset after alarm
        elif self.s_neg > self.threshold:
            alarm = "STEP_DOWN"
            self.s_neg = 0

        return {
            "s_pos": round(self.s_pos, 4),
            "s_neg": round(self.s_neg, 4),
            "alarm": alarm,
        }


@dataclass
class TrustChangeDetector:
    """Combined Kalman + CUSUM trust change detector."""
    agent_id: str
    kalman: KalmanTrustFilter = field(default_factory=KalmanTrustFilter)
    cusum: CUSUMDetector = field(default_factory=CUSUMDetector)
    history: list = field(default_factory=list)

    def observe(self, trust_score: float, label: str = "") -> dict:
        k = self.kalman.update(trust_score)
        c = self.cusum.update(trust_score)

        event = {
            "agent": self.agent_id,
            "observed": round(trust_score, 3),
            "kalman_estimate": k["estimate"],
            "innovation": k["innovation"],
            "uncertainty": k["uncertainty"],
            "label": label,
        }

        # Classify change type
        if c["alarm"]:
            event["change_type"] = c["alarm"]
            event["detector"] = "CUSUM"
            event["action"] = "CIRCUIT_BREAKER_TRIP" if c["alarm"] == "STEP_DOWN" else "INVESTIGATE"
        elif abs(k["innovation"]) > 0.15:
            event["change_type"] = "DRIFT"
            event["detector"] = "Kalman"
            event["action"] = "MONITOR"
        else:
            event["change_type"] = "STABLE"
            event["detector"] = "none"
            event["action"] = "NONE"

        self.history.append(event)
        return event


def demo():
    print("=== Trust Change Detector (Kalman + CUSUM) ===\n")

    # Scenario: honest agent, then adversarial flip
    det = TrustChangeDetector("target_agent")

    observations = [
        (0.8, "good delivery"),
        (0.82, "good delivery"),
        (0.79, "good delivery"),
        (0.81, "good delivery"),
        (0.78, "minor issue"),
        (0.80, "resolved"),
        # Adversarial flip (santaclawd's point: won't drift, will flip)
        (0.3, "sudden scope violation"),
        (0.25, "second violation"),
        (0.35, "partial recovery?"),
        (0.28, "nope, still bad"),
        # Gradual recovery
        (0.5, "improving"),
        (0.6, "better"),
        (0.7, "recovering"),
    ]

    for score, label in observations:
        event = det.observe(score, label)
        emoji = {"STABLE": "🟢", "DRIFT": "🟡", "STEP_UP": "🔵", "STEP_DOWN": "🔴"}
        e = emoji.get(event["change_type"], "⚪")
        line = f"{e} {score:.2f} ({label:25s}) → est={event['kalman_estimate']:.3f} innov={event['innovation']:+.3f}"
        if event["change_type"] != "STABLE":
            line += f"  ⚡ {event['change_type']} [{event['detector']}] → {event['action']}"
        print(line)

    # Summary
    changes = [e for e in det.history if e["change_type"] != "STABLE"]
    print(f"\n📊 {len(det.history)} observations, {len(changes)} changes detected")
    print(f"   Kalman final estimate: {det.kalman.estimate:.3f}")
    print(f"   CUSUM detects JUMPS, Kalman detects DRIFT")
    print(f"   Combined = robust against both honest drift and adversarial flips")


if __name__ == "__main__":
    demo()
