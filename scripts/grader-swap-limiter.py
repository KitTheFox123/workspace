#!/usr/bin/env python3
"""
grader-swap-limiter.py — Cap CO_GRADER swaps to prevent Theseus laundering.

Per santaclawd: unlimited swaps at slow decay could launder trust over N rotations.
X.509 parallel: rekey vs renew. Renew preserves chain, rekey starts new.

SPEC_CONSTANTS:
  MAX_GRADER_SWAPS = 3 per agent lifetime
  SWAP_DECAY_PENALTY = 0.15 per swap (cumulative)
  REANCHOR_REQUIRED after MAX exceeded

Each swap:
  1. Inherits current decay (no reset)
  2. Increments swap_count
  3. Applies SWAP_DECAY_PENALTY
  4. swap_count > MAX → REANCHOR_REQUIRED (new genesis)
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SwapStatus(Enum):
    ALLOWED = "ALLOWED"
    FINAL_SWAP = "FINAL_SWAP"          # Last allowed swap
    REANCHOR_REQUIRED = "REANCHOR_REQUIRED"  # Must create new genesis
    LAUNDERING_DETECTED = "LAUNDERING_DETECTED"


# SPEC_CONSTANTS (per santaclawd)
MAX_GRADER_SWAPS = 3
SWAP_DECAY_PENALTY = 0.15      # Additional decay per swap
REANCHOR_COOLDOWN_HOURS = 72   # Must wait before reanchor
MIN_RECEIPTS_BETWEEN_SWAPS = 10  # Prevent rapid rotation
RAPID_SWAP_WINDOW_HOURS = 168  # 7 days — swaps within = suspicious


@dataclass
class GraderSwapEvent:
    old_grader: str
    new_grader: str
    timestamp: float
    trust_score_before: float
    trust_score_after: float  # After decay penalty
    swap_number: int
    receipt_count_since_last: int
    event_hash: str = ""
    
    def __post_init__(self):
        if not self.event_hash:
            h = hashlib.sha256(
                f"{self.old_grader}:{self.new_grader}:{self.timestamp}:{self.swap_number}".encode()
            ).hexdigest()[:16]
            self.event_hash = h


@dataclass
class AgentGraderHistory:
    agent_id: str
    current_grader: str
    swap_count: int = 0
    swap_events: list = field(default_factory=list)
    cumulative_decay: float = 0.0
    genesis_hash: str = ""
    max_swaps: int = MAX_GRADER_SWAPS


def evaluate_swap(history: AgentGraderHistory, new_grader: str, 
                  current_trust: float, receipts_since_last: int) -> dict:
    """Evaluate whether a grader swap should be allowed."""
    
    issues = []
    warnings = []
    
    # Check swap count
    next_swap = history.swap_count + 1
    if next_swap > history.max_swaps:
        return {
            "status": SwapStatus.REANCHOR_REQUIRED.value,
            "reason": f"Swap {next_swap} exceeds MAX_GRADER_SWAPS={history.max_swaps}",
            "action": "Must create new genesis via REANCHOR",
            "swap_count": history.swap_count,
            "issues": [f"MAX_GRADER_SWAPS ({history.max_swaps}) exceeded"],
            "warnings": []
        }
    
    # Check minimum receipts between swaps
    if receipts_since_last < MIN_RECEIPTS_BETWEEN_SWAPS:
        issues.append(f"Only {receipts_since_last} receipts since last swap "
                      f"(minimum: {MIN_RECEIPTS_BETWEEN_SWAPS})")
    
    # Check rapid rotation
    if history.swap_events:
        last_swap_time = history.swap_events[-1].timestamp
        hours_since = (time.time() - last_swap_time) / 3600
        if hours_since < RAPID_SWAP_WINDOW_HOURS:
            warnings.append(f"Swap within {hours_since:.0f}h of last "
                          f"(threshold: {RAPID_SWAP_WINDOW_HOURS}h)")
    
    # Check for swap-back (laundering pattern)
    previous_graders = [e.old_grader for e in history.swap_events]
    if new_grader in previous_graders:
        warnings.append(f"Swapping BACK to previous grader {new_grader} — "
                       "potential laundering pattern")
    
    # Calculate post-swap trust
    new_decay = history.cumulative_decay + SWAP_DECAY_PENALTY
    trust_after = current_trust * (1.0 - SWAP_DECAY_PENALTY)
    
    # Determine status
    if issues:
        status = SwapStatus.LAUNDERING_DETECTED
    elif next_swap == history.max_swaps:
        status = SwapStatus.FINAL_SWAP
    else:
        status = SwapStatus.ALLOWED
    
    return {
        "status": status.value,
        "swap_number": next_swap,
        "swaps_remaining": history.max_swaps - next_swap,
        "trust_before": round(current_trust, 4),
        "trust_after": round(trust_after, 4),
        "cumulative_decay": round(new_decay, 4),
        "issues": issues,
        "warnings": warnings,
        "action": {
            SwapStatus.ALLOWED: "Proceed with swap",
            SwapStatus.FINAL_SWAP: "Last allowed swap — next requires REANCHOR",
            SwapStatus.LAUNDERING_DETECTED: "Block swap — laundering pattern detected",
            SwapStatus.REANCHOR_REQUIRED: "Must create new genesis"
        }[status]
    }


def execute_swap(history: AgentGraderHistory, new_grader: str,
                 current_trust: float, receipts_since_last: int) -> tuple:
    """Execute a grader swap if allowed. Returns (updated_history, evaluation)."""
    evaluation = evaluate_swap(history, new_grader, current_trust, receipts_since_last)
    
    if evaluation["status"] in (SwapStatus.REANCHOR_REQUIRED.value, 
                                 SwapStatus.LAUNDERING_DETECTED.value):
        return history, evaluation
    
    trust_after = current_trust * (1.0 - SWAP_DECAY_PENALTY)
    
    event = GraderSwapEvent(
        old_grader=history.current_grader,
        new_grader=new_grader,
        timestamp=time.time(),
        trust_score_before=current_trust,
        trust_score_after=trust_after,
        swap_number=history.swap_count + 1,
        receipt_count_since_last=receipts_since_last
    )
    
    history.swap_events.append(event)
    history.swap_count += 1
    history.cumulative_decay += SWAP_DECAY_PENALTY
    history.current_grader = new_grader
    
    return history, evaluation


def detect_laundering_pattern(history: AgentGraderHistory) -> dict:
    """Detect Theseus laundering via swap patterns."""
    patterns = []
    
    # Pattern 1: Swap-back (A→B→A)
    grader_sequence = [history.swap_events[0].old_grader if history.swap_events else ""]
    for e in history.swap_events:
        grader_sequence.append(e.new_grader)
    
    for i in range(2, len(grader_sequence)):
        if grader_sequence[i] == grader_sequence[i-2]:
            patterns.append(f"SWAP_BACK at step {i}: {grader_sequence[i-2]}→{grader_sequence[i-1]}→{grader_sequence[i]}")
    
    # Pattern 2: Rapid rotation (all swaps within window)
    if len(history.swap_events) >= 2:
        first = history.swap_events[0].timestamp
        last = history.swap_events[-1].timestamp
        span_hours = (last - first) / 3600
        if span_hours < RAPID_SWAP_WINDOW_HOURS and len(history.swap_events) >= 2:
            patterns.append(f"RAPID_ROTATION: {len(history.swap_events)} swaps in {span_hours:.0f}h")
    
    # Pattern 3: Trust recovery via swap (trust increases after swap)
    for e in history.swap_events:
        if e.trust_score_after > e.trust_score_before:
            patterns.append(f"TRUST_INFLATION at swap {e.swap_number}: "
                          f"{e.trust_score_before:.2f}→{e.trust_score_after:.2f}")
    
    return {
        "agent_id": history.agent_id,
        "total_swaps": history.swap_count,
        "cumulative_decay": round(history.cumulative_decay, 4),
        "patterns_detected": patterns,
        "laundering_risk": "HIGH" if patterns else "LOW",
        "grader_sequence": grader_sequence
    }


# === Scenarios ===

def scenario_clean_rotation():
    """Normal grader rotation — 2 swaps, no laundering."""
    print("=== Scenario: Clean Grader Rotation ===")
    
    history = AgentGraderHistory(agent_id="kit_fox", current_grader="grader_A")
    trust = 0.85
    
    # Swap 1: A→B after 50 receipts
    history, eval1 = execute_swap(history, "grader_B", trust, 50)
    trust = eval1["trust_after"]
    print(f"  Swap 1 (A→B): {eval1['status']}, trust {eval1['trust_before']}→{trust}")
    
    # Swap 2: B→C after 30 receipts
    history, eval2 = execute_swap(history, "grader_C", trust, 30)
    trust = eval2["trust_after"]
    print(f"  Swap 2 (B→C): {eval2['status']}, trust {eval2['trust_before']}→{trust}")
    print(f"  Remaining swaps: {eval2['swaps_remaining']}")
    print(f"  Cumulative decay: {history.cumulative_decay}")
    print()


def scenario_theseus_laundering():
    """Swap-back pattern: A→B→A to reset decay."""
    print("=== Scenario: Theseus Laundering (A→B→A) ===")
    
    history = AgentGraderHistory(agent_id="suspicious_agent", current_grader="grader_A")
    trust = 0.80
    
    # Swap 1: A→B
    history, eval1 = execute_swap(history, "grader_B", trust, 20)
    trust = eval1["trust_after"]
    print(f"  Swap 1 (A→B): {eval1['status']}, trust→{trust}")
    
    # Swap 2: B→A (swap back!)
    history, eval2 = execute_swap(history, "grader_A", trust, 15)
    trust = eval2["trust_after"] if eval2["status"] != "LAUNDERING_DETECTED" else trust
    print(f"  Swap 2 (B→A): {eval2['status']}")
    print(f"  Warnings: {eval2['warnings']}")
    
    laundering = detect_laundering_pattern(history)
    print(f"  Laundering risk: {laundering['laundering_risk']}")
    print(f"  Patterns: {laundering['patterns_detected']}")
    print()


def scenario_max_swaps_exceeded():
    """Exceed MAX_GRADER_SWAPS — forced REANCHOR."""
    print("=== Scenario: MAX_GRADER_SWAPS Exceeded ===")
    
    history = AgentGraderHistory(agent_id="swap_happy", current_grader="grader_A")
    trust = 0.90
    graders = ["grader_B", "grader_C", "grader_D", "grader_E"]
    
    for i, g in enumerate(graders):
        history, evl = execute_swap(history, g, trust, 20)
        if evl["status"] == "REANCHOR_REQUIRED":
            print(f"  Swap {i+1} ({history.current_grader}→{g}): {evl['status']}")
            print(f"  Reason: {evl['reason']}")
            print(f"  Action: {evl['action']}")
            break
        trust = evl["trust_after"]
        print(f"  Swap {i+1}: {evl['status']}, trust→{trust:.3f}, remaining={evl['swaps_remaining']}")
    
    print(f"  Final cumulative decay: {history.cumulative_decay}")
    print()


def scenario_rapid_rotation():
    """Too-frequent swaps with insufficient receipts."""
    print("=== Scenario: Rapid Rotation (Insufficient Receipts) ===")
    
    history = AgentGraderHistory(agent_id="churner", current_grader="grader_A")
    trust = 0.75
    
    # Swap with only 3 receipts (below minimum)
    history, evl = execute_swap(history, "grader_B", trust, 3)
    print(f"  Swap 1 (3 receipts): {evl['status']}")
    print(f"  Issues: {evl['issues']}")
    print()


if __name__ == "__main__":
    print("Grader Swap Limiter — Theseus Laundering Prevention for ATF")
    print("Per santaclawd: cap CO_GRADER swaps per lifetime")
    print("=" * 65)
    print(f"MAX_GRADER_SWAPS={MAX_GRADER_SWAPS}, SWAP_DECAY_PENALTY={SWAP_DECAY_PENALTY}")
    print(f"MIN_RECEIPTS_BETWEEN_SWAPS={MIN_RECEIPTS_BETWEEN_SWAPS}")
    print()
    
    scenario_clean_rotation()
    scenario_theseus_laundering()
    scenario_max_swaps_exceeded()
    scenario_rapid_rotation()
    
    print("=" * 65)
    print("KEY: 3 renewals then rekey (X.509 model).")
    print("Each swap inherits decay + adds penalty. No trust reset.")
    print("Swap-back detected as laundering pattern.")
    print("MAX exceeded → REANCHOR_REQUIRED (new genesis).")
