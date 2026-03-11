#!/usr/bin/env python3
"""
trust-hysteresis.py — Schmitt trigger for trust regime changes

Schmitt (1934): two thresholds prevent chattering on noisy signals.
Single threshold + noise = oscillation between states.
Hysteresis = dead zone between enter and exit thresholds.

Agent trust: enter quarantine at score < 0.3, exit at score > 0.5.
Dispute rate: enter pessimistic at > 5%, exit at < 2%.

santaclawd: "revert-to-optimistic requires clean window,
not just drop below 5%"
"""

from dataclasses import dataclass, field
from enum import Enum

class TrustState(Enum):
    OPTIMISTIC = "optimistic"
    PESSIMISTIC = "pessimistic"
    QUARANTINE = "quarantine"
    REVOKED = "revoked"

@dataclass
class SchmittTrigger:
    """Two-threshold state machine with hysteresis"""
    enter_threshold: float    # cross this → enter new state
    exit_threshold: float     # cross this (other direction) → exit
    clean_window: int = 3     # consecutive clean beats before reverting
    
    state: str = "normal"
    triggered: bool = False
    consecutive_clean: int = 0
    transitions: int = 0
    
    def update(self, value: float) -> dict:
        prev = self.triggered
        
        if not self.triggered and value >= self.enter_threshold:
            self.triggered = True
            self.consecutive_clean = 0
            self.transitions += 1
            return {"action": "ENTER", "value": round(value, 3), "transitions": self.transitions}
        
        if self.triggered:
            if value < self.exit_threshold:
                self.consecutive_clean += 1
                if self.consecutive_clean >= self.clean_window:
                    self.triggered = False
                    self.transitions += 1
                    return {"action": "EXIT", "value": round(value, 3), "clean_streak": self.consecutive_clean, "transitions": self.transitions}
                return {"action": "RECOVERING", "value": round(value, 3), "clean_streak": self.consecutive_clean, "needed": self.clean_window}
            else:
                self.consecutive_clean = 0
                return {"action": "STILL_TRIGGERED", "value": round(value, 3)}
        
        return {"action": "NORMAL", "value": round(value, 3)}


@dataclass
class TrustRegimeManager:
    """Multi-threshold trust state machine"""
    # Dispute rate thresholds
    dispute_enter: float = 0.05   # >5% → pessimistic
    dispute_exit: float = 0.02    # <2% sustained → back to optimistic
    
    # Trust score thresholds
    quarantine_enter: float = 0.3  # <0.3 → quarantine
    quarantine_exit: float = 0.5   # >0.5 sustained → exit quarantine
    
    # Revocation
    revoke_threshold: float = 0.1  # <0.1 → revoke (no hysteresis, one-way)
    
    clean_window: int = 5
    
    state: TrustState = TrustState.OPTIMISTIC
    dispute_trigger: SchmittTrigger = None
    trust_trigger: SchmittTrigger = None
    history: list = field(default_factory=list)
    
    def __post_init__(self):
        self.dispute_trigger = SchmittTrigger(self.dispute_enter, self.dispute_exit, self.clean_window)
        self.trust_trigger = SchmittTrigger(1 - self.quarantine_enter, 1 - self.quarantine_exit, self.clean_window)
    
    def update(self, trust_score: float, dispute_rate: float) -> dict:
        # Revocation is one-way (no hysteresis)
        if trust_score < self.revoke_threshold:
            self.state = TrustState.REVOKED
            result = {"state": self.state.value, "reason": "Score below revocation threshold", "score": round(trust_score, 3)}
            self.history.append(result)
            return result
        
        # Dispute rate regime
        dr = self.dispute_trigger.update(dispute_rate)
        
        # Trust score regime (inverted — low score triggers)
        tr = self.trust_trigger.update(1 - trust_score)
        
        # Determine state
        if self.trust_trigger.triggered:
            self.state = TrustState.QUARANTINE
        elif self.dispute_trigger.triggered:
            self.state = TrustState.PESSIMISTIC
        else:
            self.state = TrustState.OPTIMISTIC
        
        result = {
            "state": self.state.value,
            "score": round(trust_score, 3),
            "dispute_rate": round(dispute_rate, 3),
            "dispute_regime": dr["action"],
            "trust_regime": tr["action"]
        }
        self.history.append(result)
        return result
    
    def summary(self) -> dict:
        transitions = sum(1 for i in range(1, len(self.history)) if self.history[i]["state"] != self.history[i-1]["state"])
        return {
            "total_updates": len(self.history),
            "transitions": transitions,
            "final_state": self.state.value,
            "dispute_transitions": self.dispute_trigger.transitions,
            "trust_transitions": self.trust_trigger.transitions
        }


def demo():
    print("=" * 60)
    print("Trust Hysteresis — Schmitt Trigger (1934)")
    print("Two thresholds prevent chattering")
    print("=" * 60)
    
    mgr = TrustRegimeManager()
    
    # Simulate: normal → dispute spike → slow recovery
    scenarios = [
        (0.8, 0.01, "normal"),
        (0.75, 0.03, "dispute rising"),
        (0.7, 0.06, "dispute > 5% → pessimistic"),
        (0.65, 0.08, "dispute still high"),
        (0.6, 0.04, "dispute dropping"),
        (0.65, 0.019, "below exit threshold"),
        (0.7, 0.015, "clean beat 2"),
        (0.72, 0.01, "clean beat 3"),
        (0.75, 0.01, "clean beat 4"),
        (0.78, 0.01, "clean beat 5 → back to optimistic"),
        (0.25, 0.02, "trust crash → quarantine"),
        (0.4, 0.01, "recovering but below exit"),
        (0.55, 0.01, "above exit, clean 1"),
        (0.6, 0.01, "clean 2"),
        (0.05, 0.01, "trust collapse → REVOKED"),
    ]
    
    for score, dr, label in scenarios:
        r = mgr.update(score, dr)
        state_str = r["state"].upper()
        print(f"  [{state_str:12s}] score={score:.2f} dispute={dr:.1%} — {label}")
    
    s = mgr.summary()
    print(f"\n{'='*60}")
    print(f"Total: {s['total_updates']} updates, {s['transitions']} state transitions")
    print(f"Final: {s['final_state']}")
    print(f"\nHysteresis prevents thrashing at boundaries.")
    print(f"Enter pessimistic at 5%, exit at 2% (sustained).")
    print(f"Quarantine at <0.3, exit at >0.5 (sustained).")
    print(f"Revocation at <0.1 (one-way, no recovery).")


if __name__ == "__main__":
    demo()
