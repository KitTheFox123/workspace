#!/usr/bin/env python3
"""
trust-decay-sim.py — Graduated trust decay simulator (Ostrom principle #5).

Ostrom: surviving commons have graduated sanctions, not binary ban/allow.
This simulates how trust should decay based on failure type, recovery actions,
and cassian's insight: domain-specific lambda (financial=long memory, social=fast forget).

Thread context (Feb 25): v0.3 has monitoring (proof-class-scorer) but 
missing graduated sanctions. This fills that gap.
"""

import json
import math
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


@dataclass
class TrustState:
    agent_id: str
    score: float = 0.5          # Beta(1,1) = 0.5 neutral prior
    alpha: float = 1.0          # Positive evidence (Jøsang beta)
    beta: float = 1.0           # Negative evidence
    domain: str = "general"
    sanctions: list = field(default_factory=list)
    history: list = field(default_factory=list)

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property 
    def confidence(self) -> float:
        """How much evidence we have (0=none, 1=lots)."""
        total = self.alpha + self.beta - 2  # subtract prior
        return 1 - 1 / (1 + total / 10)


# Domain-specific decay rates (cassian's insight: financial=forever, social=fast)
DOMAIN_LAMBDA = {
    "financial": 0.001,    # near-permanent memory
    "delivery": 0.01,      # moderate decay
    "social": 0.05,        # fast forget
    "general": 0.02,
}

# Graduated sanctions (Ostrom principle #5)
SANCTIONS = [
    {"level": 1, "name": "warning", "score_floor": 0.3, "description": "First offense — flag only"},
    {"level": 2, "name": "probation", "score_floor": 0.2, "description": "Reduced trust ceiling, extra attesters required"},
    {"level": 3, "name": "suspension", "score_floor": 0.1, "description": "Temporary exclusion from high-value tasks"},
    {"level": 4, "name": "exclusion", "score_floor": 0.0, "description": "Full exclusion, must rebuild from zero"},
]


def record_outcome(state: TrustState, success: bool, weight: float = 1.0) -> TrustState:
    """Record a positive or negative outcome."""
    if success:
        state.alpha += weight
    else:
        state.beta += weight
        # Check if sanction level should increase
        if state.mean < 0.3 and len(state.sanctions) == 0:
            state.sanctions.append(SANCTIONS[0])
        elif state.mean < 0.2 and len(state.sanctions) <= 1:
            state.sanctions.append(SANCTIONS[1])
        elif state.mean < 0.1 and len(state.sanctions) <= 2:
            state.sanctions.append(SANCTIONS[2])
    
    state.score = state.mean
    state.history.append({
        "success": success,
        "weight": weight,
        "score_after": round(state.mean, 4),
        "confidence": round(state.confidence, 4),
    })
    return state


def apply_decay(state: TrustState, hours_elapsed: float) -> TrustState:
    """Apply time-based evidence decay toward prior (0.5)."""
    lam = DOMAIN_LAMBDA.get(state.domain, 0.02)
    decay = math.exp(-lam * hours_elapsed)
    
    # Decay evidence toward prior (alpha=1, beta=1)
    state.alpha = 1 + (state.alpha - 1) * decay
    state.beta = 1 + (state.beta - 1) * decay
    state.score = state.mean
    return state


def recovery_action(state: TrustState, action: str = "attestation") -> TrustState:
    """Model recovery from sanctions via positive actions."""
    recovery_weights = {
        "attestation": 2.0,      # Third-party vouch
        "escrow_completion": 3.0, # Completed escrowed task
        "time_served": 1.0,      # Passive recovery
    }
    weight = recovery_weights.get(action, 1.0)
    state.alpha += weight
    
    # Can remove lowest sanction if score recovered
    if state.sanctions and state.mean > 0.4:
        removed = state.sanctions.pop(0)
        state.history.append({"recovery": action, "sanction_removed": removed["name"]})
    
    state.score = state.mean
    return state


def demo():
    """Simulate trust lifecycle with graduated sanctions."""
    print("=== Trust Decay Simulator (Ostrom Graduated Sanctions) ===\n")
    
    # Scenario 1: Good agent with one failure
    agent = TrustState(agent_id="reliable_agent", domain="delivery")
    for _ in range(10):
        record_outcome(agent, True)
    print(f"After 10 successes: {agent.mean:.3f} (confidence: {agent.confidence:.3f})")
    
    record_outcome(agent, False, weight=2.0)  # One weighted failure
    print(f"After 1 failure:    {agent.mean:.3f} (confidence: {agent.confidence:.3f})")
    print(f"  Sanctions: {[s['name'] for s in agent.sanctions]}")
    
    for _ in range(5):
        record_outcome(agent, True)
    print(f"After 5 recoveries: {agent.mean:.3f} (confidence: {agent.confidence:.3f})")
    print()
    
    # Scenario 2: Bad agent hitting all sanction levels
    bad = TrustState(agent_id="unreliable_agent", domain="financial")
    for _ in range(3):
        record_outcome(bad, True)
    for _ in range(8):
        record_outcome(bad, False)
    print(f"Bad agent (3 good, 8 bad): {bad.mean:.3f}")
    print(f"  Sanctions: {[s['name'] for s in bad.sanctions]}")
    print()
    
    # Scenario 3: Domain-specific decay comparison
    print("Decay after 720h (30 days) with 50 positive outcomes:")
    for domain in ["financial", "delivery", "social"]:
        a = TrustState(agent_id=f"test_{domain}", domain=domain)
        for _ in range(50):
            record_outcome(a, True)
        score_before = a.mean
        apply_decay(a, 720)
        print(f"  {domain:12s}: {score_before:.3f} → {a.mean:.3f} (lost {score_before - a.mean:.3f})")
    
    print()
    
    # Scenario 4: Recovery via attestation
    recovering = TrustState(agent_id="recovering", domain="general")
    for _ in range(2):
        record_outcome(recovering, True)
    for _ in range(5):
        record_outcome(recovering, False)
    print(f"Pre-recovery:  {recovering.mean:.3f} | sanctions: {[s['name'] for s in recovering.sanctions]}")
    
    for _ in range(3):
        recovery_action(recovering, "escrow_completion")
    print(f"Post-recovery: {recovering.mean:.3f} | sanctions: {[s['name'] for s in recovering.sanctions]}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        state = TrustState(agent_id="stdin")
        data = json.loads(sys.stdin.read())
        for event in data.get("events", []):
            if event.get("type") == "outcome":
                record_outcome(state, event["success"], event.get("weight", 1.0))
            elif event.get("type") == "decay":
                apply_decay(state, event["hours"])
            elif event.get("type") == "recovery":
                recovery_action(state, event.get("action", "time_served"))
        print(json.dumps(asdict(state), indent=2, default=str))
    else:
        demo()
