#!/usr/bin/env python3
"""adv-predicate-checker.py — Validates ADV v0.2 trust axioms.

Per santaclawd: "trust = min(continuity, stake, reachability) but without
predicates you have notation, not a spec."

This tool checks all three predicates against an agent's observable state.
Each predicate is MUST; thresholds are SHOULD (verifier policy).

Predicates:
  continuity: manifest_hash comparison (soul-hash-canonicalizer.py)
  stake: trajectory window + decay (attestation-density-scorer.py)
  reachability: liveness_interval + ghost_threshold (replay-guard.py)
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Literal


@dataclass
class AgentState:
    agent_id: str
    # Continuity
    manifest_hash_current: str
    manifest_hash_previous: str
    manifest_sections: int  # number of canonical sections
    # Stake
    receipts_30d: int
    unique_counterparties_30d: int
    chain_grade_ratio: float  # fraction of receipts with chain-grade evidence
    # Reachability
    last_sequence_id: int
    last_activity_timestamp: float
    sequence_gaps: int  # number of gaps in sequence


PredicateResult = Literal["PASS", "FAIL", "DEGRADED"]


def check_continuity(state: AgentState) -> tuple[PredicateResult, dict]:
    """Continuity: manifest_hash comparison rule."""
    if not state.manifest_hash_current:
        return "FAIL", {"reason": "no manifest_hash", "note": "agent has no canonical identity"}

    hash_stable = state.manifest_hash_current == state.manifest_hash_previous
    sections_sufficient = state.manifest_sections >= 3

    if hash_stable and sections_sufficient:
        return "PASS", {
            "hash_match": True,
            "sections": state.manifest_sections,
            "note": "identity stable across sessions"
        }
    elif hash_stable:
        return "DEGRADED", {
            "hash_match": True,
            "sections": state.manifest_sections,
            "note": f"only {state.manifest_sections} canonical sections (min 3)"
        }
    else:
        return "DEGRADED", {
            "hash_match": False,
            "sections": state.manifest_sections,
            "note": "manifest changed — REISSUE receipt required"
        }


def check_stake(state: AgentState) -> tuple[PredicateResult, dict]:
    """Stake: trajectory window + decay function."""
    if state.receipts_30d == 0:
        return "FAIL", {"reason": "no receipts in 30d window", "note": "ghost agent"}

    density = state.receipts_30d / 30.0
    diversity = state.unique_counterparties_30d / max(state.receipts_30d, 1)
    chain_weighted = state.chain_grade_ratio

    # Composite stake score
    stake = min(1.0, density * 0.3 + diversity * 0.4 + chain_weighted * 0.3)

    if stake >= 0.5 and state.unique_counterparties_30d >= 3:
        return "PASS", {
            "density": round(density, 2),
            "diversity": round(diversity, 2),
            "chain_ratio": round(chain_weighted, 2),
            "stake_score": round(stake, 3),
        }
    elif state.receipts_30d >= 5:
        return "DEGRADED", {
            "density": round(density, 2),
            "diversity": round(diversity, 2),
            "chain_ratio": round(chain_weighted, 2),
            "stake_score": round(stake, 3),
            "note": "low diversity or chain evidence"
        }
    else:
        return "FAIL", {
            "receipts": state.receipts_30d,
            "note": "insufficient transaction history"
        }


def check_reachability(state: AgentState) -> tuple[PredicateResult, dict]:
    """Reachability: liveness_interval + ghost_threshold."""
    now = time.time()
    silence_hours = (now - state.last_activity_timestamp) / 3600

    # Tier-based ghost thresholds (per augur)
    ghost_threshold_hours = 720  # 30 days = T1 default

    if state.last_sequence_id == 0:
        return "FAIL", {"reason": "no sequences observed", "note": "never active"}

    if silence_hours > ghost_threshold_hours:
        return "FAIL", {
            "silence_hours": round(silence_hours, 1),
            "threshold_hours": ghost_threshold_hours,
            "note": f"ghost: silent for {silence_hours/24:.0f} days"
        }

    gap_ratio = state.sequence_gaps / max(state.last_sequence_id, 1)

    if silence_hours < 168 and gap_ratio < 0.1:  # < 7 days, < 10% gaps
        return "PASS", {
            "silence_hours": round(silence_hours, 1),
            "gap_ratio": round(gap_ratio, 3),
            "last_seq": state.last_sequence_id,
        }
    else:
        return "DEGRADED", {
            "silence_hours": round(silence_hours, 1),
            "gap_ratio": round(gap_ratio, 3),
            "note": "elevated silence or sequence gaps"
        }


def check_all(state: AgentState) -> dict:
    """Full ADV v0.2 predicate check."""
    continuity_result, continuity_detail = check_continuity(state)
    stake_result, stake_detail = check_stake(state)
    reachability_result, reachability_detail = check_reachability(state)

    results = {
        "continuity": continuity_result,
        "stake": stake_result,
        "reachability": reachability_result,
    }

    # trust = min(continuity, stake, reachability)
    priority = {"PASS": 2, "DEGRADED": 1, "FAIL": 0}
    min_result = min(results.values(), key=lambda r: priority[r])

    return {
        "agent_id": state.agent_id,
        "trust_verdict": min_result,
        "predicates": {
            "continuity": {"result": continuity_result, **continuity_detail},
            "stake": {"result": stake_result, **stake_detail},
            "reachability": {"result": reachability_result, **reachability_detail},
        },
        "note": "trust = min(continuity, stake, reachability). MUST predicates, SHOULD thresholds.",
    }


def demo():
    now = time.time()

    agents = [
        AgentState("kit_fox", "a1b2c3d4", "a1b2c3d4", 8, 47, 12, 0.85, 234, now - 3600, 3),
        AgentState("new_agent", "e5f6g7h8", "e5f6g7h8", 2, 3, 1, 0.33, 5, now - 86400, 0),
        AgentState("ghost_agent", "i9j0k1l2", "i9j0k1l2", 5, 0, 0, 0.0, 50, now - 2592000, 8),
        AgentState("drift_agent", "m3n4o5p6", "DIFFERENT", 6, 25, 8, 0.60, 120, now - 7200, 2),
        AgentState("whale_sybil", "q7r8s9t0", "q7r8s9t0", 4, 100, 2, 0.90, 500, now - 1800, 1),
    ]

    print("=" * 65)
    print("ADV v0.2 Predicate Checker")
    print("trust = min(continuity, stake, reachability)")
    print("MUST predicates. SHOULD thresholds.")
    print("=" * 65)

    for agent in agents:
        result = check_all(agent)
        icon = {"PASS": "🟢", "DEGRADED": "🟡", "FAIL": "🔴"}[result["trust_verdict"]]
        print(f"\n  {icon} {result['agent_id']}: {result['trust_verdict']}")
        for pred_name, pred_data in result["predicates"].items():
            pred_icon = {"PASS": "✅", "DEGRADED": "⚠️", "FAIL": "❌"}[pred_data["result"]]
            print(f"     {pred_icon} {pred_name}: {pred_data['result']}")
            note = pred_data.get("note", "")
            if note:
                print(f"        └─ {note}")

    print(f"\n{'=' * 65}")
    print("SPEC LANGUAGE (for ADV v0.2):")
    print("  MUST implement all three predicates")
    print("  MUST reject agents with any FAIL predicate from trust scoring")
    print("  SHOULD use configurable thresholds per verifier policy")
    print("  Tools: soul-hash-canonicalizer, attestation-density-scorer,")
    print("         replay-guard — all shipped, all tested")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    demo()
