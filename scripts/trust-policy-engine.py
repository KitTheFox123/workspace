#!/usr/bin/env python3
"""
trust-policy-engine.py — DMARC-equivalent policy layer for agent trust stack.

Per santaclawd: "who decides what to do when 2-of-5 checks fail?"
DMARC maps DKIM+SPF → reject/quarantine/none.
This maps trust-stack axes → ALLOW/DEGRADE/QUARANTINE/REJECT.

Layer 6 in the trust stack:
  genesis → independence → monoculture → witness → revocation → POLICY
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Action(Enum):
    ALLOW = "ALLOW"           # Full permissions
    DEGRADE = "DEGRADE"       # Reduced scope, extra logging
    QUARANTINE = "QUARANTINE" # Sandboxed, human review
    REJECT = "REJECT"         # No interaction


class ReportMode(Enum):
    NONE = "none"       # No reporting
    AGGREGATE = "aggregate"  # Like DMARC rua (batch)
    FORENSIC = "forensic"    # Like DMARC ruf (per-failure)


@dataclass
class TrustSignal:
    axis: str       # maturity, health, consistency, independence, revocation_status
    grade: str      # A-F or I (insufficient)
    score: float    # 0.0-1.0
    confident: bool # enough data?


@dataclass
class PolicyRule:
    """A single policy rule: if condition met, take action."""
    name: str
    condition: str  # human-readable
    action: Action
    priority: int   # lower = higher priority
    
    def evaluate(self, signals: dict[str, TrustSignal]) -> Optional[Action]:
        raise NotImplementedError


class AnyAxisBelow(PolicyRule):
    """Trigger if ANY axis falls below threshold."""
    def __init__(self, name: str, threshold: float, action: Action, priority: int):
        super().__init__(name, f"any axis < {threshold}", action, priority)
        self.threshold = threshold
    
    def evaluate(self, signals: dict[str, TrustSignal]) -> Optional[Action]:
        for sig in signals.values():
            if sig.confident and sig.score < self.threshold:
                return self.action
        return None


class AxisBelow(PolicyRule):
    """Trigger if specific axis falls below threshold."""
    def __init__(self, name: str, axis: str, threshold: float, action: Action, priority: int):
        super().__init__(name, f"{axis} < {threshold}", action, priority)
        self.axis = axis
        self.threshold = threshold
    
    def evaluate(self, signals: dict[str, TrustSignal]) -> Optional[Action]:
        sig = signals.get(self.axis)
        if sig and sig.confident and sig.score < self.threshold:
            return self.action
        return None


class InsufficientData(PolicyRule):
    """Trigger if too many axes lack confidence."""
    def __init__(self, name: str, min_confident: int, action: Action, priority: int):
        super().__init__(name, f"<{min_confident} confident axes", action, priority)
        self.min_confident = min_confident
    
    def evaluate(self, signals: dict[str, TrustSignal]) -> Optional[Action]:
        confident_count = sum(1 for s in signals.values() if s.confident)
        if confident_count < self.min_confident:
            return self.action
        return None


@dataclass
class PolicyDecision:
    action: Action
    triggered_by: str
    signals: dict[str, TrustSignal]
    report_mode: ReportMode


class TrustPolicyEngine:
    """DMARC-equivalent: maps trust signals to actions."""
    
    def __init__(self, report_mode: ReportMode = ReportMode.AGGREGATE):
        self.rules: list[PolicyRule] = []
        self.report_mode = report_mode
        self._install_defaults()
    
    def _install_defaults(self):
        """Default policy: strict but fair."""
        # Priority 1: Hard rejections
        self.rules.append(AxisBelow("revoked", "revocation_status", 0.01, Action.REJECT, 1))
        self.rules.append(AnyAxisBelow("critical_failure", 0.10, Action.REJECT, 2))
        
        # Priority 3: Quarantine
        self.rules.append(AnyAxisBelow("low_trust", 0.30, Action.QUARANTINE, 3))
        self.rules.append(InsufficientData("insufficient_data", 3, Action.QUARANTINE, 4))
        
        # Priority 5: Degrade
        self.rules.append(AnyAxisBelow("degraded_trust", 0.50, Action.DEGRADE, 5))
        
        # Sort by priority
        self.rules.sort(key=lambda r: r.priority)
    
    def evaluate(self, signals: dict[str, TrustSignal]) -> PolicyDecision:
        for rule in self.rules:
            action = rule.evaluate(signals)
            if action:
                return PolicyDecision(
                    action=action,
                    triggered_by=rule.name,
                    signals=signals,
                    report_mode=self.report_mode
                )
        return PolicyDecision(
            action=Action.ALLOW,
            triggered_by="default_allow",
            signals=signals,
            report_mode=self.report_mode
        )


def demo():
    engine = TrustPolicyEngine()
    
    scenarios = {
        "trusted_veteran": {
            "maturity": TrustSignal("maturity", "A", 0.92, True),
            "health": TrustSignal("health", "A", 0.88, True),
            "consistency": TrustSignal("consistency", "A", 0.90, True),
            "independence": TrustSignal("independence", "A", 0.85, True),
            "revocation_status": TrustSignal("revocation_status", "A", 1.0, True),
        },
        "hiding_drift": {
            "maturity": TrustSignal("maturity", "A", 0.95, True),
            "health": TrustSignal("health", "F", 0.08, True),  # zero corrections
            "consistency": TrustSignal("consistency", "B", 0.75, True),
            "independence": TrustSignal("independence", "A", 0.90, True),
            "revocation_status": TrustSignal("revocation_status", "A", 1.0, True),
        },
        "new_agent": {
            "maturity": TrustSignal("maturity", "I", 0.10, False),
            "health": TrustSignal("health", "I", 0.50, False),
            "consistency": TrustSignal("consistency", "I", 0.50, False),
        },
        "forked_agent": {
            "maturity": TrustSignal("maturity", "A", 0.90, True),
            "health": TrustSignal("health", "B", 0.70, True),
            "consistency": TrustSignal("consistency", "F", 0.05, True),  # fork detected
            "independence": TrustSignal("independence", "B", 0.72, True),
            "revocation_status": TrustSignal("revocation_status", "A", 1.0, True),
        },
        "revoked": {
            "maturity": TrustSignal("maturity", "A", 0.95, True),
            "health": TrustSignal("health", "A", 0.88, True),
            "consistency": TrustSignal("consistency", "A", 0.90, True),
            "independence": TrustSignal("independence", "A", 0.85, True),
            "revocation_status": TrustSignal("revocation_status", "F", 0.0, True),
        },
    }
    
    for name, signals in scenarios.items():
        decision = engine.evaluate(signals)
        axes = " | ".join(f"{k}={v.score:.2f}" for k, v in signals.items())
        print(f"\n{name}: {decision.action.value} (triggered: {decision.triggered_by})")
        print(f"  {axes}")


if __name__ == "__main__":
    demo()
