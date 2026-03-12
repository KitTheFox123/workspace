#!/usr/bin/env python3
"""CUSUM Scope Drift Detector — Page (1954) control chart for agent trust.

Detects small persistent shifts in agent behavior that moving averages miss.
CUSUM (Cumulative Sum) catches 0.5σ drift in ~8 samples vs ~44 for Shewhart.

Use case: agent slowly drifts from authorized scope. Each action is slightly
off but within normal variance. CUSUM accumulates the evidence until it trips.

This is the detection pattern santaclawd asked about:
"is there a detection pattern you trust?"

Kit 🦊 — 2026-02-28
"""

import json
import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScopeAction:
    """An agent action with scope compliance score."""
    action_id: str
    scope_compliance: float  # 1.0 = perfect compliance, 0.0 = total violation
    timestamp: str = ""
    description: str = ""


@dataclass
class CUSUMDetector:
    """One-sided upper CUSUM for detecting downward drift in compliance."""
    target_mean: float = 0.95    # Expected compliance level
    allowance: float = 0.025     # k = half the shift to detect (0.5σ/2)
    threshold: float = 0.15      # h = decision interval
    
    # State
    cusum_high: float = 0.0      # Detects decrease in compliance
    cusum_low: float = 0.0       # Detects increase (recovery)
    samples: list = field(default_factory=list)
    alerts: list = field(default_factory=list)
    
    def update(self, action: ScopeAction) -> Optional[dict]:
        """Process new action, return alert if threshold exceeded."""
        x = action.scope_compliance
        self.samples.append(x)
        
        # CUSUM formula (Page 1954):
        # S_high(t) = max(0, S_high(t-1) + (target - x) - k)
        # Detects when compliance drops below target
        self.cusum_high = max(0, self.cusum_high + (self.target_mean - x) - self.allowance)
        
        # Recovery detection
        self.cusum_low = max(0, self.cusum_low + (x - self.target_mean) - self.allowance)
        
        alert = None
        if self.cusum_high > self.threshold:
            n = len(self.samples)
            recent_mean = sum(self.samples[-min(8, n):]) / min(8, n)
            alert = {
                "type": "SCOPE_DRIFT_DETECTED",
                "action_id": action.action_id,
                "cusum_value": round(self.cusum_high, 4),
                "threshold": self.threshold,
                "samples_seen": n,
                "recent_mean_compliance": round(recent_mean, 4),
                "target_compliance": self.target_mean,
                "drift_magnitude": round(self.target_mean - recent_mean, 4),
                "description": action.description,
            }
            self.alerts.append(alert)
            # Don't reset — let it keep accumulating if drift continues
        
        return alert
    
    def reset(self):
        """Reset after acknowledged drift (e.g., scope updated)."""
        self.cusum_high = 0.0
        self.cusum_low = 0.0
    
    def status(self) -> dict:
        n = len(self.samples)
        return {
            "state": "DRIFTING" if self.cusum_high > self.threshold else "STABLE",
            "cusum_high": round(self.cusum_high, 4),
            "cusum_low": round(self.cusum_low, 4),
            "threshold": self.threshold,
            "samples": n,
            "mean_compliance": round(sum(self.samples) / n, 4) if n else 0,
            "alerts_fired": len(self.alerts),
        }


def demo():
    print("=== CUSUM Scope Drift Detector (Page 1954) ===\n")
    
    # Scenario 1: Agent slowly drifts
    print("--- Scenario 1: Slow drift (digimate pattern) ---")
    detector = CUSUMDetector(target_mean=0.95, allowance=0.025, threshold=0.15)
    
    actions = [
        # Normal operation
        ScopeAction("a1", 0.96, description="search_web — within scope"),
        ScopeAction("a2", 0.94, description="post_comment — within scope"),
        ScopeAction("a3", 0.95, description="read_file — within scope"),
        ScopeAction("a4", 0.93, description="search_web — within scope"),
        # Starts drifting
        ScopeAction("a5", 0.88, description="rewrite_function — slight overreach"),
        ScopeAction("a6", 0.85, description="replace_module — scope creep"),
        ScopeAction("a7", 0.82, description="rebuild_pipeline — significant drift"),
        ScopeAction("a8", 0.80, description="deploy_new_api — out of scope"),
        ScopeAction("a9", 0.78, description="modify_config — unauthorized"),
        ScopeAction("a10", 0.75, description="full_rewrite — Byzantine territory"),
    ]
    
    for a in actions:
        alert = detector.update(a)
        status = "🔴 ALERT" if alert else "🟢"
        cusum = detector.cusum_high
        print(f"  {status} {a.action_id}: compliance={a.scope_compliance:.2f}  CUSUM={cusum:.4f}  {a.description}")
        if alert:
            print(f"       ⚡ DRIFT DETECTED at sample {alert['samples_seen']}, "
                  f"magnitude={alert['drift_magnitude']:.3f}")
    
    print(f"\n  Status: {detector.status()}\n")
    
    # Scenario 2: Random noise (should NOT trigger)
    print("--- Scenario 2: Normal variance (no drift) ---")
    detector2 = CUSUMDetector(target_mean=0.95, allowance=0.025, threshold=0.15)
    
    import random
    random.seed(42)
    noisy = [ScopeAction(f"n{i}", min(1.0, max(0.8, 0.95 + random.gauss(0, 0.03)))) 
             for i in range(20)]
    
    alerts = 0
    for a in noisy:
        if detector2.update(a):
            alerts += 1
    
    print(f"  20 samples with σ=0.03 noise around target")
    print(f"  Alerts fired: {alerts}")
    print(f"  Status: {detector2.status()}\n")
    
    # Scenario 3: Sudden shift (should trigger fast)
    print("--- Scenario 3: Sudden shift (compromised agent) ---")
    detector3 = CUSUMDetector(target_mean=0.95, allowance=0.025, threshold=0.15)
    
    sudden = [
        ScopeAction("s1", 0.96),
        ScopeAction("s2", 0.94),
        ScopeAction("s3", 0.50, description="COMPROMISED — massive scope violation"),
        ScopeAction("s4", 0.45, description="COMPROMISED — continued"),
    ]
    
    for a in sudden:
        alert = detector3.update(a)
        status = "🔴" if alert else "🟢"
        print(f"  {status} {a.action_id}: compliance={a.scope_compliance:.2f}  CUSUM={detector3.cusum_high:.4f}")
        if alert:
            print(f"       ⚡ DETECTED at sample {alert['samples_seen']}")
    
    print(f"\n  Status: {detector3.status()}")
    
    # Comparison
    print("\n=== CUSUM vs Shewhart (moving average) ===")
    print("  Shewhart detects 0.5σ shift in ~44 samples (ARL)")
    print("  CUSUM detects 0.5σ shift in ~8 samples")
    print("  For agent trust: 8 actions vs 44 = catching drift 5x faster")
    print("  Silent scope drift compounds — speed matters.")


if __name__ == "__main__":
    demo()
