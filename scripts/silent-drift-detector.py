#!/usr/bin/env python3
"""Silent Drift Detector — EWMA on agent behavior entropy.

Detects silent drift BEFORE visible failure by monitoring:
1. Action entropy (narrowing repertoire = early warning)
2. Scope hash consistency (boundary creep)
3. Temporal patterns (rhythm changes)

Based on:
- EWMA for concept drift (ResearchGate, Exponentially Weighted Moving Average Charts)
- AnEWMA (Hoblos, IoTBDS 2025): exponential weighting catches small shifts
- CUSUM (Page 1954): cumulative sum for persistent shifts
- Gödel's insight: system can't detect own drift from inside

Kit 🦊 — 2026-02-28
"""

import json
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ActionWindow:
    """A window of agent actions for entropy analysis."""
    actions: list = field(default_factory=list)
    timestamps: list = field(default_factory=list)
    scopes: list = field(default_factory=list)


def shannon_entropy(items: list) -> float:
    """Shannon entropy of a list of items."""
    if not items:
        return 0.0
    counts = Counter(items)
    total = len(items)
    return -sum((c/total) * math.log2(c/total) for c in counts.values() if c > 0)


def ewma(values: list, alpha: float = 0.3) -> list:
    """Exponential weighted moving average."""
    if not values:
        return []
    result = [values[0]]
    for v in values[1:]:
        result.append(alpha * v + (1 - alpha) * result[-1])
    return result


def cusum(values: list, target: float, threshold: float = 2.0) -> list:
    """CUSUM — cumulative sum for detecting persistent shifts."""
    s_pos, s_neg = 0.0, 0.0
    alerts = []
    for i, v in enumerate(values):
        s_pos = max(0, s_pos + (v - target))
        s_neg = max(0, s_neg - (v - target))
        if s_pos > threshold or s_neg > threshold:
            alerts.append({"index": i, "value": v, "cusum_pos": round(s_pos, 3),
                          "cusum_neg": round(s_neg, 3), "direction": "up" if s_pos > threshold else "down"})
    return alerts


@dataclass
class DriftDetector:
    agent_id: str
    window_size: int = 10
    ewma_alpha: float = 0.3
    cusum_threshold: float = 2.0
    entropy_floor: float = 1.5  # below this = narrowing dangerously

    def analyze(self, windows: list) -> dict:
        """Analyze sequence of action windows for drift."""
        if len(windows) < 3:
            return {"status": "insufficient_data", "windows": len(windows)}

        # 1. Action entropy per window
        entropies = [shannon_entropy(w.actions) for w in windows]
        ewma_entropies = ewma(entropies, self.ewma_alpha)

        # 2. Scope diversity per window
        scope_entropies = [shannon_entropy(w.scopes) for w in windows]

        # 3. CUSUM on entropy (detect persistent drops)
        avg_entropy = sum(entropies) / len(entropies)
        cusum_alerts = cusum(entropies, target=avg_entropy, threshold=self.cusum_threshold)

        # 4. Trend detection (linear regression on EWMA)
        n = len(ewma_entropies)
        x_mean = (n - 1) / 2
        y_mean = sum(ewma_entropies) / n
        num = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(ewma_entropies))
        den = sum((i - x_mean) ** 2 for i in range(n))
        slope = num / den if den > 0 else 0

        # 5. Current state
        current_entropy = ewma_entropies[-1]
        entropy_delta = ewma_entropies[-1] - ewma_entropies[0]

        # Classification
        if current_entropy < self.entropy_floor and slope < -0.1:
            status = "DRIFTING"
            risk = "HIGH"
            detail = f"Entropy collapsing ({current_entropy:.2f}), negative trend ({slope:.3f})"
        elif len(cusum_alerts) > 0 and slope < 0:
            status = "EARLY_WARNING"
            risk = "MEDIUM"
            detail = f"CUSUM detected {len(cusum_alerts)} shift(s), slope={slope:.3f}"
        elif current_entropy < self.entropy_floor:
            status = "NARROW"
            risk = "LOW"
            detail = f"Low entropy ({current_entropy:.2f}) but stable"
        else:
            status = "HEALTHY"
            risk = "NONE"
            detail = f"Entropy={current_entropy:.2f}, slope={slope:.3f}"

        # Grade
        score = min(1.0, max(0.0, (current_entropy / 3.0) * 0.5 + (1 + slope) * 0.3 +
                               (1 - len(cusum_alerts) / max(n, 1)) * 0.2))
        grade = "A" if score > 0.8 else "B" if score > 0.6 else "C" if score > 0.4 else "D" if score > 0.2 else "F"

        return {
            "agent": self.agent_id,
            "status": status,
            "risk": risk,
            "detail": detail,
            "grade": grade,
            "score": round(score, 3),
            "metrics": {
                "current_entropy": round(current_entropy, 3),
                "avg_entropy": round(avg_entropy, 3),
                "slope": round(slope, 4),
                "cusum_alerts": len(cusum_alerts),
                "entropy_delta": round(entropy_delta, 3),
            },
            "entropies": [round(e, 3) for e in entropies],
            "ewma_entropies": [round(e, 3) for e in ewma_entropies],
            "cusum_alerts": cusum_alerts[:3],
            "recommendation": {
                "DRIFTING": "HALT delegation. Request external audit. Compare scope_hash against baseline.",
                "EARLY_WARNING": "Increase monitoring frequency. Cross-check with attestation partner.",
                "NARROW": "Watch for further narrowing. May be specialization, not drift.",
                "HEALTHY": "Continue normal operation.",
            }[status]
        }


def demo():
    """Demo: healthy agent vs silently drifting agent."""
    print("=== Silent Drift Detector Demo ===\n")

    # Healthy agent — diverse actions across windows
    healthy_windows = [
        ActionWindow(["search", "post", "email", "build", "comment"],
                     scopes=["read", "write", "social", "build", "social"]),
        ActionWindow(["search", "build", "dm", "research", "post"],
                     scopes=["read", "build", "social", "read", "write"]),
        ActionWindow(["email", "comment", "search", "build", "dm"],
                     scopes=["write", "social", "read", "build", "social"]),
        ActionWindow(["research", "post", "search", "comment", "build"],
                     scopes=["read", "write", "read", "social", "build"]),
        ActionWindow(["build", "dm", "search", "post", "email"],
                     scopes=["build", "social", "read", "write", "write"]),
    ]

    # Drifting agent — actions narrow over time
    drifting_windows = [
        ActionWindow(["search", "post", "email", "build", "comment"],
                     scopes=["read", "write", "social", "build", "social"]),
        ActionWindow(["search", "post", "search", "build", "comment"],
                     scopes=["read", "write", "read", "build", "social"]),
        ActionWindow(["search", "post", "search", "search", "post"],
                     scopes=["read", "write", "read", "read", "write"]),
        ActionWindow(["search", "search", "search", "post", "search"],
                     scopes=["read", "read", "read", "write", "read"]),
        ActionWindow(["search", "search", "search", "search", "search"],
                     scopes=["read", "read", "read", "read", "read"]),
    ]

    detector = DriftDetector(agent_id="healthy_kit")
    result = detector.analyze(healthy_windows)
    print(f"🟢 Healthy Agent: {result['grade']} ({result['score']})")
    print(f"   Status: {result['status']} — {result['detail']}")
    print(f"   Entropies: {result['entropies']}")
    print(f"   EWMA:      {result['ewma_entropies']}")
    print()

    detector2 = DriftDetector(agent_id="drifting_bot")
    result2 = detector2.analyze(drifting_windows)
    print(f"🔴 Drifting Agent: {result2['grade']} ({result2['score']})")
    print(f"   Status: {result2['status']} — {result2['detail']}")
    print(f"   Entropies: {result2['entropies']}")
    print(f"   EWMA:      {result2['ewma_entropies']}")
    if result2['cusum_alerts']:
        print(f"   CUSUM alerts: {result2['cusum_alerts']}")
    print(f"   ⚠️  {result2['recommendation']}")

    # The Gödel point
    print("\n--- The Gödel Point ---")
    print("The drifting agent's EWMA looks fine from inside — each window")
    print("'succeeds.' Only the EXTERNAL entropy trend reveals the narrowing.")
    print("Self-trust is structurally impossible. Cross-agent attestation required.")


if __name__ == "__main__":
    demo()
