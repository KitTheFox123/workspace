#!/usr/bin/env python3
"""Wald SPRT for Agent Governance — sequential binary trust decisions.

Wald's Sequential Probability Ratio Test (1945): optimal stopping rule
for binary hypotheses. Applied to agent trust:
  H0: agent behaving normally (p = p0)
  H1: agent drifting/compromised (p = p1)

Each receipt (or missing receipt) updates the likelihood ratio.
Decision: TRUST, DISTRUST, or CONTINUE MONITORING.

Based on:
- Wald (1945): original SPRT
- Fischer & Ramdas (arxiv 2024): improved SPRT avoiding overshoot
- santaclawd's insight: "the receipt you SHOULD have sent but didn't is the deviation"

Usage:
  python wald-sprt-governance.py --demo
  echo '{"events": [...]}' | python wald-sprt-governance.py --json
"""

import json
import sys
import math
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SPRTState:
    """Sequential Probability Ratio Test state."""
    # Hypotheses
    p0: float = 0.10   # Baseline failure rate under H0 (normal)
    p1: float = 0.40   # Failure rate under H1 (drifting)
    
    # Error bounds
    alpha: float = 0.05  # P(reject H0 | H0 true) = false alarm
    beta: float = 0.10   # P(accept H0 | H1 true) = missed detection
    
    # State
    log_lr: float = 0.0  # Log likelihood ratio
    n: int = 0
    successes: int = 0
    failures: int = 0
    null_receipts: int = 0  # Missing expected receipts
    decision: Optional[str] = None
    history: List[dict] = field(default_factory=list)
    
    @property
    def upper_bound(self) -> float:
        """Log of upper threshold: ln((1-beta)/alpha)"""
        return math.log((1 - self.beta) / self.alpha)
    
    @property
    def lower_bound(self) -> float:
        """Log of lower threshold: ln(beta/(1-alpha))"""
        return math.log(self.beta / (1 - self.alpha))


def sprt_update(state: SPRTState, event: dict) -> dict:
    """Update SPRT with new event. Returns decision info."""
    state.n += 1
    event_type = event.get("type", "success")
    timestamp = event.get("timestamp", "")
    
    if event_type == "success":
        # Receipt received as expected
        state.successes += 1
        # Log likelihood ratio update for success
        lr_inc = math.log((1 - state.p1) / (1 - state.p0))
    elif event_type == "failure":
        # Receipt indicates problem
        state.failures += 1
        lr_inc = math.log(state.p1 / state.p0)
    elif event_type == "null":
        # Missing receipt (santaclawd's insight: absence as evidence)
        state.null_receipts += 1
        # Null receipt = weighted toward failure (0.7 weight)
        effective_p0 = state.p0 * 0.3 + 0.5 * 0.7  # Partially informative
        effective_p1 = state.p1 * 0.3 + 0.8 * 0.7
        lr_inc = math.log(effective_p1 / effective_p0)
    else:
        lr_inc = 0.0
    
    state.log_lr += lr_inc
    
    # Check thresholds
    decision = "CONTINUE"
    if state.log_lr >= state.upper_bound:
        decision = "DISTRUST"
        state.decision = "H1: Agent drifting/compromised"
    elif state.log_lr <= state.lower_bound:
        decision = "TRUST"
        state.decision = "H0: Agent behaving normally"
    
    record = {
        "n": state.n,
        "event": event_type,
        "timestamp": timestamp,
        "log_lr": round(state.log_lr, 4),
        "upper_bound": round(state.upper_bound, 4),
        "lower_bound": round(state.lower_bound, 4),
        "decision": decision,
        "observed_rate": round(state.failures / state.n, 3),
    }
    state.history.append(record)
    return record


def run_sprt(events: list, p0: float = 0.10, p1: float = 0.40,
             alpha: float = 0.05, beta: float = 0.10) -> dict:
    """Run SPRT on event stream."""
    state = SPRTState(p0=p0, p1=p1, alpha=alpha, beta=beta)
    
    for event in events:
        result = sprt_update(state, event)
        if result["decision"] != "CONTINUE":
            break
    
    return {
        "total_events": state.n,
        "successes": state.successes,
        "failures": state.failures,
        "null_receipts": state.null_receipts,
        "observed_failure_rate": round(state.failures / max(1, state.n), 3),
        "final_log_lr": round(state.log_lr, 4),
        "upper_bound": round(state.upper_bound, 4),
        "lower_bound": round(state.lower_bound, 4),
        "decision": result["decision"],
        "decision_detail": state.decision or "Monitoring continues",
        "samples_to_decision": state.n,
        "history": state.history[-5:],  # Last 5 for brevity
    }


def demo():
    import random
    random.seed(42)
    
    print("=" * 60)
    print("Wald SPRT for Agent Governance Decisions")
    print("H0: normal (p=0.10) | H1: drifting (p=0.40)")
    print(f"α=0.05 (false alarm) | β=0.10 (missed detection)")
    print("=" * 60)
    
    # Scenario 1: Honest agent
    print("\n--- Scenario 1: Honest Agent ---")
    honest = [{"type": "success" if random.random() > 0.08 else "failure"} for _ in range(50)]
    result = run_sprt(honest)
    print(f"Decision: {result['decision']} at sample {result['samples_to_decision']}")
    print(f"Observed failure rate: {result['observed_failure_rate']}")
    print(f"Log LR: {result['final_log_lr']} (bounds: [{result['lower_bound']}, {result['upper_bound']}])")
    
    # Scenario 2: Drifting agent
    print("\n--- Scenario 2: Drifting Agent (35% failure) ---")
    drifting = [{"type": "success" if random.random() > 0.35 else "failure"} for _ in range(50)]
    result = run_sprt(drifting)
    print(f"Decision: {result['decision']} at sample {result['samples_to_decision']}")
    print(f"Observed failure rate: {result['observed_failure_rate']}")
    print(f"Log LR: {result['final_log_lr']}")
    
    # Scenario 3: Null receipts (missing heartbeats)
    print("\n--- Scenario 3: Missing Receipts (null nodes) ---")
    missing = []
    for i in range(30):
        if i < 10:
            missing.append({"type": "success"})
        elif i < 20:
            missing.append({"type": "null"})  # Heartbeats stop coming
        else:
            missing.append({"type": "failure"})
    result = run_sprt(missing)
    print(f"Decision: {result['decision']} at sample {result['samples_to_decision']}")
    print(f"Null receipts: {result['null_receipts']}")
    print(f"Log LR: {result['final_log_lr']}")
    
    # Scenario 4: Optimal sample size comparison
    print("\n--- Sample Size Efficiency ---")
    sizes = []
    for trial in range(100):
        events = [{"type": "success" if random.random() > 0.10 else "failure"} for _ in range(200)]
        r = run_sprt(events)
        sizes.append(r["samples_to_decision"])
    avg_n = sum(sizes) / len(sizes)
    decided = sum(1 for s in sizes if s < 200)
    print(f"Average samples to TRUST decision: {avg_n:.1f}")
    print(f"Decided within 200 samples: {decided}/100")
    print(f"Wald optimality: SPRT minimizes E[N] among all tests at same error rates")
    
    # Scenario 5: santaclawd's three-layer stack
    print("\n--- Three-Layer Governance Stack ---")
    print("Layer 1: provenance-logger.py  → JSONL hash chain (log it)")
    print("Layer 2: proof-class-scorer.py → diversity scoring (classify it)")
    print("Layer 3: cusum-drift-detector.py + wald-sprt-governance.py → detect drift + decide")
    print("Each layer feeds the next. Minimum viable governance = 4 scripts.")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = run_sprt(
            data.get("events", []),
            p0=data.get("p0", 0.10),
            p1=data.get("p1", 0.40),
        )
        print(json.dumps(result, indent=2))
    else:
        demo()
