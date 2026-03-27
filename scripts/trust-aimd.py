#!/usr/bin/env python3
"""
trust-aimd.py — AIMD (Additive Increase / Multiplicative Decrease) for trust scores.

Maps TCP congestion control to agent trust management.

TCP insight: The internet's most successful distributed resource allocation algorithm
uses asymmetric responses to positive and negative signals:
- Success: increase linearly (cautious growth)
- Failure: decrease multiplicatively (fast response to problems)

This asymmetry is load-bearing. Equal increase/decrease converges to unfair equilibria.
Multiplicative decrease ensures that high-trust agents lose MORE absolute trust on 
failure — which is correct. A trusted agent screwing up is worse than an unknown one.

TCP analogy mapped to trust:
- cwnd (congestion window) → trust_score (0.0 to 1.0)
- ACK received → successful attestation / probe passed
- packet loss → failed attestation / probe failed / dispute lost
- slow start → new agent bootstrap (exponential until first failure)
- congestion avoidance → established agent (linear growth)
- fast retransmit → quick partial recovery after single failure
- timeout → catastrophic trust reset after sustained failures

Action-class integration (from ATF SOFT_CASCADE thread):
- READ failures: AIMD with gentle decrease (β=0.8)
- WRITE failures: AIMD with standard decrease (β=0.5, TCP default)
- TRANSFER failures: AIMD with aggressive decrease (β=0.25)
- ATTEST failures: AIMD with severe decrease (β=0.1) — vouching carries highest cost

Sources:
- Jacobson 1988: TCP congestion avoidance
- Chiu & Jain 1989: AIMD convergence proof (fairness + efficiency)
- Floyd & Jacobson 1993: Random early detection (gentle degradation)
- ATF SOFT_CASCADE thread (santaclawd, funwolf, alphasenpai, Mar 2026)
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone


class ActionClass(Enum):
    READ = "READ"
    WRITE = "WRITE"
    TRANSFER = "TRANSFER"
    ATTEST = "ATTEST"


class TrustPhase(Enum):
    """Maps to TCP congestion control phases."""
    SLOW_START = "slow_start"           # New agent: exponential growth
    CONGESTION_AVOIDANCE = "avoidance"  # Established: linear growth
    FAST_RECOVERY = "fast_recovery"     # After single failure: partial recovery
    TIMEOUT = "timeout"                 # After sustained failures: near-reset


# Multiplicative decrease factors per action class
# Higher stake = harsher penalty (lower β)
BETA_BY_ACTION = {
    ActionClass.READ: 0.80,      # Gentle: read failure is low-cost
    ActionClass.WRITE: 0.50,     # Standard TCP default
    ActionClass.TRANSFER: 0.25,  # Aggressive: transfers are hard to reverse
    ActionClass.ATTEST: 0.10,    # Severe: vouching for others = highest responsibility
}

# Additive increase per successful action
ALPHA_BY_ACTION = {
    ActionClass.READ: 0.02,      # Slow steady growth
    ActionClass.WRITE: 0.03,     # Slightly faster (more signal)
    ActionClass.TRANSFER: 0.01,  # Very cautious growth
    ActionClass.ATTEST: 0.005,   # Slowest: trust to vouch is hardest to earn
}

# Slow start threshold (switch from exponential to linear)
SSTHRESH_DEFAULT = 0.5


@dataclass
class TrustState:
    """Current trust state for an agent, modeled as TCP cwnd."""
    agent_id: str
    score: float = 0.1              # Initial trust (like TCP initial cwnd)
    ssthresh: float = SSTHRESH_DEFAULT  # Slow start threshold
    phase: TrustPhase = TrustPhase.SLOW_START
    consecutive_successes: int = 0
    consecutive_failures: int = 0
    total_successes: int = 0
    total_failures: int = 0
    history: list = field(default_factory=list)
    
    @property
    def max_score(self) -> float:
        return 1.0
    
    @property
    def min_score(self) -> float:
        return 0.01  # Never fully zero — allow recovery path


class TrustAIMD:
    """
    AIMD trust controller.
    
    Core insight from Chiu & Jain (1989): AIMD is the ONLY linear control policy
    that converges to both fairness AND efficiency. Any other combination 
    (AIAD, MIAD, MIMD) fails on one axis.
    
    For trust: fairness = equal opportunity to build trust.
    Efficiency = total trust allocated tracks actual trustworthiness.
    """
    
    def __init__(self):
        self.agents: dict[str, TrustState] = {}
    
    def register(self, agent_id: str, initial_score: float = 0.1) -> TrustState:
        """Register new agent in slow start phase."""
        state = TrustState(agent_id=agent_id, score=initial_score)
        self.agents[agent_id] = state
        return state
    
    def on_success(self, agent_id: str, action: ActionClass) -> dict:
        """
        Handle successful action — increase trust.
        
        Slow start: double score (exponential, like TCP)
        Congestion avoidance: add alpha (linear, like TCP)
        """
        state = self.agents[agent_id]
        old_score = state.score
        alpha = ALPHA_BY_ACTION[action]
        
        if state.phase == TrustPhase.SLOW_START:
            # Exponential growth until ssthresh
            state.score = min(state.score * 2, state.max_score)
            if state.score >= state.ssthresh:
                state.phase = TrustPhase.CONGESTION_AVOIDANCE
        
        elif state.phase == TrustPhase.CONGESTION_AVOIDANCE:
            # Linear growth: additive increase
            state.score = min(state.score + alpha, state.max_score)
        
        elif state.phase == TrustPhase.FAST_RECOVERY:
            # After one success in fast recovery, return to avoidance
            state.score = min(state.score + alpha, state.max_score)
            state.phase = TrustPhase.CONGESTION_AVOIDANCE
        
        elif state.phase == TrustPhase.TIMEOUT:
            # After timeout, re-enter slow start
            state.phase = TrustPhase.SLOW_START
            state.score = min(state.score * 2, state.ssthresh)
        
        state.consecutive_successes += 1
        state.consecutive_failures = 0
        state.total_successes += 1
        
        event = {
            "type": "success",
            "action": action.value,
            "old_score": round(old_score, 4),
            "new_score": round(state.score, 4),
            "phase": state.phase.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        state.history.append(event)
        return event
    
    def on_failure(self, agent_id: str, action: ActionClass) -> dict:
        """
        Handle failed action — decrease trust multiplicatively.
        
        Single failure: multiplicative decrease + fast recovery
        Sustained failures (3+): timeout → near-reset
        
        Key TCP insight: high-cwnd connections lose MORE on failure.
        Same here: high-trust agents lose more absolute trust.
        An agent at 0.9 failing a WRITE drops to 0.45.
        An agent at 0.3 failing a WRITE drops to 0.15.
        The trusted agent's failure costs more. This is correct.
        """
        state = self.agents[agent_id]
        old_score = state.score
        beta = BETA_BY_ACTION[action]
        
        state.consecutive_failures += 1
        state.consecutive_successes = 0
        state.total_failures += 1
        
        if state.consecutive_failures >= 3:
            # Timeout: sustained failures → near-reset
            state.ssthresh = max(state.score * beta, state.min_score)
            state.score = state.min_score
            state.phase = TrustPhase.TIMEOUT
        else:
            # Single/double failure: multiplicative decrease + fast recovery
            state.ssthresh = max(state.score * beta, state.min_score)
            state.score = max(state.score * beta, state.min_score)
            state.phase = TrustPhase.FAST_RECOVERY
        
        event = {
            "type": "failure",
            "action": action.value,
            "beta": beta,
            "old_score": round(old_score, 4),
            "new_score": round(state.score, 4),
            "phase": state.phase.value,
            "consecutive_failures": state.consecutive_failures,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        state.history.append(event)
        return event
    
    def get_state(self, agent_id: str) -> dict:
        s = self.agents[agent_id]
        return {
            "agent_id": s.agent_id,
            "score": round(s.score, 4),
            "phase": s.phase.value,
            "ssthresh": round(s.ssthresh, 4),
            "total_successes": s.total_successes,
            "total_failures": s.total_failures,
            "consecutive_successes": s.consecutive_successes,
            "consecutive_failures": s.consecutive_failures,
        }


def run_scenarios():
    """Demonstrate AIMD trust dynamics."""
    ctrl = TrustAIMD()
    
    print("=" * 70)
    print("TRUST-AIMD: TCP Congestion Control for Agent Trust")
    print("Chiu & Jain (1989): AIMD = only linear policy achieving")
    print("both fairness AND efficiency")
    print("=" * 70)
    
    # Scenario 1: Good agent bootstrapping through slow start → avoidance
    print("\n--- Scenario 1: Good agent bootstrap ---")
    ctrl.register("alice", 0.1)
    for i in range(8):
        e = ctrl.on_success("alice", ActionClass.WRITE)
        print(f"  Success #{i+1}: {e['old_score']:.4f} → {e['new_score']:.4f} [{e['phase']}]")
    
    # Scenario 2: Trusted agent fails — multiplicative decrease
    print("\n--- Scenario 2: Trusted agent fails a WRITE ---")
    e = ctrl.on_failure("alice", ActionClass.WRITE)
    print(f"  WRITE failure (β=0.5): {e['old_score']:.4f} → {e['new_score']:.4f} [{e['phase']}]")
    
    # Recovery
    for i in range(3):
        e = ctrl.on_success("alice", ActionClass.WRITE)
        print(f"  Recovery #{i+1}: {e['old_score']:.4f} → {e['new_score']:.4f} [{e['phase']}]")
    
    # Scenario 3: Compare action class severity
    print("\n--- Scenario 3: Same agent, different action class failures ---")
    for action in ActionClass:
        ctrl.register(f"test_{action.value}", 0.8)
        e = ctrl.on_failure(f"test_{action.value}", action)
        print(f"  {action.value:8s} failure (β={BETA_BY_ACTION[action]:.2f}): "
              f"0.8000 → {e['new_score']:.4f}  "
              f"(lost {0.8 - e['new_score']:.4f})")
    
    # Scenario 4: Sustained failures → timeout
    print("\n--- Scenario 4: Sustained failures → timeout ---")
    ctrl.register("eve", 0.7)
    for i in range(4):
        e = ctrl.on_failure("eve", ActionClass.TRANSFER)
        print(f"  Failure #{i+1}: {e['old_score']:.4f} → {e['new_score']:.4f} [{e['phase']}]")
    
    # Eve tries to recover from timeout
    print("  (eve enters slow start from timeout)")
    for i in range(5):
        e = ctrl.on_success("eve", ActionClass.READ)
        print(f"  Recovery #{i+1}: {e['old_score']:.4f} → {e['new_score']:.4f} [{e['phase']}]")
    
    # Summary
    print(f"\n{'=' * 70}")
    print("Key properties (from Chiu & Jain convergence proof):")
    print("1. FAIRNESS: All agents grow trust at same additive rate")
    print("2. EFFICIENCY: High-trust agents lose MORE on failure (correct)")
    print("3. CONVERGENCE: After perturbation, agents converge to fair share")
    print("4. ASYMMETRY: Slow to trust, fast to distrust (security primitive)")
    print(f"\nAction class severity: READ(β=0.8) < WRITE(β=0.5) < TRANSFER(β=0.25) < ATTEST(β=0.1)")
    print("SOFT_CASCADE answer: active re-attestation for WRITE+, passive for READ")


if __name__ == "__main__":
    run_scenarios()
