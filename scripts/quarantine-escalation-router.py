#!/usr/bin/env python3
"""
quarantine-escalation-router.py — Layer 7: DMARC-equivalent policy engine for agent trust.

Per santaclawd: "who decides what to do when layers 2 + 4 fail simultaneously?"
Per funwolf: "where do quarantine events go? delivery mechanism = policy mechanism."

6 trust layers → policy aggregation → action routing:
  genesis → independence → monoculture → witness → revocation → correction-health

Actions (DMARC model):
  p=none     → MONITOR (log, no action)
  p=quarantine → QUARANTINE (restrict, notify operator + agent)
  p=reject   → REJECT (block, escalate)

Escalation targets:
  - Operator inbox (agentmail)
  - Agent itself (so it can self-correct)
  - Counterparties (so they can re-evaluate)
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Action(Enum):
    MONITOR = "monitor"      # p=none
    QUARANTINE = "quarantine" # p=quarantine
    REJECT = "reject"        # p=reject


class Severity(Enum):
    INFO = 0
    WARNING = 1
    CRITICAL = 2
    FATAL = 3


@dataclass
class LayerSignal:
    layer: str          # genesis, independence, monoculture, witness, revocation, correction
    grade: str          # A-F
    score: float        # 0.0-1.0
    issues: list[str] = field(default_factory=list)
    
    @property
    def severity(self) -> Severity:
        if self.grade == "F":
            return Severity.FATAL
        elif self.grade in ("D", "E"):
            return Severity.CRITICAL
        elif self.grade == "C":
            return Severity.WARNING
        return Severity.INFO


@dataclass
class EscalationReport:
    action: Action
    agent_id: str
    timestamp: datetime
    triggered_layers: list[str]
    signals: list[LayerSignal]
    escalation_targets: list[str]
    detail: str
    
    def to_email(self) -> dict:
        body = f"""TRUST POLICY REPORT — {self.action.value.upper()}
Agent: {self.agent_id}
Time: {self.timestamp.isoformat()}Z
Action: {self.action.value}

TRIGGERED LAYERS:
{chr(10).join(f'  [{s.grade}] {s.layer}: {s.score:.2f} — {", ".join(s.issues) if s.issues else "OK"}' for s in self.signals)}

ESCALATION TARGETS:
{chr(10).join(f'  → {t}' for t in self.escalation_targets)}

DETAIL:
{self.detail}

RECOMMENDED:
{"Investigate immediately. Multiple critical failures." if self.action == Action.REJECT else "Review at next heartbeat." if self.action == Action.QUARANTINE else "No action required."}
"""
        return {
            "subject": f"[{self.action.value.upper()}] Trust policy: {self.agent_id}",
            "text": body,
            "targets": self.escalation_targets
        }


class PolicyEngine:
    """DMARC-equivalent policy aggregation for trust layers."""
    
    # Failure combination matrix
    COMBINATION_RULES = {
        # (layer_a, layer_b) → Action when BOTH fail
        ("independence", "witness"): Action.REJECT,      # can't trust witnesses if not independent
        ("independence", "monoculture"): Action.REJECT,   # correlated failure
        ("monoculture", "revocation"): Action.REJECT,     # can't revoke what you can't distinguish
        ("genesis", "independence"): Action.REJECT,       # no foundation
        ("witness", "correction"): Action.QUARANTINE,     # degrading but maybe recoverable
        ("revocation", "correction"): Action.QUARANTINE,  # stale but maybe active
    }
    
    def evaluate(self, agent_id: str, signals: list[LayerSignal],
                 operator_email: Optional[str] = None,
                 agent_email: Optional[str] = None) -> EscalationReport:
        
        now = datetime.utcnow()
        failed = [s for s in signals if s.severity.value >= Severity.CRITICAL.value]
        fatal = [s for s in signals if s.severity == Severity.FATAL]
        
        # Check combination rules
        action = Action.MONITOR
        triggered = []
        detail_parts = []
        
        # Any fatal → REJECT
        if fatal:
            action = Action.REJECT
            triggered = [s.layer for s in fatal]
            detail_parts.append(f"Fatal failures: {', '.join(triggered)}")
        
        # Check pairwise combinations
        failed_layers = {s.layer for s in failed}
        for (la, lb), combo_action in self.COMBINATION_RULES.items():
            if la in failed_layers and lb in failed_layers:
                if combo_action.value > action.value:
                    action = combo_action
                triggered.extend([la, lb])
                detail_parts.append(f"{la}+{lb} simultaneous failure → {combo_action.value}")
        
        # Single critical → QUARANTINE
        if not triggered and failed:
            action = Action.QUARANTINE
            triggered = [s.layer for s in failed]
            detail_parts.append(f"Single-layer critical: {', '.join(triggered)}")
        
        # MIN score check
        min_score = min(s.score for s in signals) if signals else 0.0
        if min_score < 0.2 and action == Action.MONITOR:
            action = Action.QUARANTINE
            detail_parts.append(f"MIN score {min_score:.2f} below threshold")
        
        # Escalation targets
        targets = []
        if operator_email:
            targets.append(operator_email)
        if agent_email and action != Action.REJECT:  # agent can self-correct if not rejected
            targets.append(agent_email)
        if not targets:
            targets.append("operator:default")
        
        triggered = list(set(triggered)) if triggered else ["none"]
        
        return EscalationReport(
            action=action,
            agent_id=agent_id,
            timestamp=now,
            triggered_layers=triggered,
            signals=signals,
            escalation_targets=targets,
            detail=" | ".join(detail_parts) if detail_parts else "All layers healthy"
        )


def demo():
    engine = PolicyEngine()
    
    # Scenario 1: Healthy agent
    healthy_signals = [
        LayerSignal("genesis", "A", 0.95),
        LayerSignal("independence", "A", 0.88),
        LayerSignal("monoculture", "B", 0.75),
        LayerSignal("witness", "A", 0.92),
        LayerSignal("revocation", "A", 0.90),
        LayerSignal("correction", "B", 0.78),
    ]
    result = engine.evaluate("kit_fox", healthy_signals, "ilya@example.com", "kit_fox@agentmail.to")
    print(f"Healthy: {result.action.value} | Triggered: {result.triggered_layers}")
    
    # Scenario 2: Independence + witness fail (santaclawd's question)
    combo_fail = [
        LayerSignal("genesis", "A", 0.95),
        LayerSignal("independence", "F", 0.10, ["4/5 same operator"]),
        LayerSignal("monoculture", "C", 0.55),
        LayerSignal("witness", "D", 0.25, ["2/5 stale", "no cross-validation"]),
        LayerSignal("revocation", "B", 0.80),
        LayerSignal("correction", "A", 0.88),
    ]
    result = engine.evaluate("suspicious_agent", combo_fail, "ops@example.com", "suspicious@agentmail.to")
    print(f"\nIndependence+Witness fail: {result.action.value} | Triggered: {result.triggered_layers}")
    email = result.to_email()
    print(f"Subject: {email['subject']}")
    print(email['text'][:500])
    
    # Scenario 3: Single critical (correction degrading)
    single_fail = [
        LayerSignal("genesis", "A", 0.95),
        LayerSignal("independence", "A", 0.88),
        LayerSignal("monoculture", "A", 0.90),
        LayerSignal("witness", "B", 0.78),
        LayerSignal("revocation", "A", 0.85),
        LayerSignal("correction", "D", 0.20, ["0 corrections in 30d", "entropy=0.0"]),
    ]
    result = engine.evaluate("hiding_drift", single_fail, agent_email="hiding@agentmail.to")
    print(f"\nSingle critical (correction): {result.action.value} | Triggered: {result.triggered_layers}")
    print(f"Targets: {result.escalation_targets}")


if __name__ == "__main__":
    demo()
