#!/usr/bin/env python3
"""
trust-policy-aggregator.py — DMARC-equivalent for agent trust.

Per santaclawd: email has DMARC (aggregate DKIM+SPF signals, tell receivers 
what to do on failure). Agent trust has 5 layers but no policy aggregation.

DMARC verbs: p=none (monitor), p=quarantine (degrade), p=reject (block)
Agent verbs: MONITOR, DEGRADE_SCOPE, REQUIRE_REATTESTATION, REJECT

Layer results feed into policy engine. Policy is per-counterparty, not global.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class LayerVerdict(Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"  # layer not evaluated


class PolicyAction(Enum):
    ALLOW = "ALLOW"              # all clear
    MONITOR = "MONITOR"          # log but proceed (p=none)
    DEGRADE_SCOPE = "DEGRADE"    # narrow scope of trust (p=quarantine)
    REQUIRE_REATTEST = "REATTEST" # demand fresh attestation
    REJECT = "REJECT"            # refuse interaction (p=reject)


@dataclass
class LayerResult:
    name: str
    verdict: LayerVerdict
    score: float  # 0.0-1.0
    detail: str


@dataclass
class TrustPolicy:
    """Per-counterparty trust policy. Like DMARC records per domain."""
    min_passing_layers: int = 3
    critical_layers: list[str] = None  # layers that MUST pass (like DKIM alignment in DMARC)
    failure_action: PolicyAction = PolicyAction.DEGRADE_SCOPE
    
    def __post_init__(self):
        if self.critical_layers is None:
            self.critical_layers = ["genesis", "independence"]  # non-negotiable
    
    def evaluate(self, results: list[LayerResult]) -> dict:
        passing = [r for r in results if r.verdict == LayerVerdict.PASS]
        failing = [r for r in results if r.verdict == LayerVerdict.FAIL]
        warnings = [r for r in results if r.verdict == LayerVerdict.WARN]
        evaluated = [r for r in results if r.verdict != LayerVerdict.SKIP]
        
        # Check critical layers
        critical_failures = [r for r in failing if r.name in self.critical_layers]
        
        # DMARC-style decision
        if critical_failures:
            action = PolicyAction.REJECT
            reason = f"Critical layer(s) failed: {[r.name for r in critical_failures]}"
        elif len(failing) >= len(evaluated) / 2:
            action = PolicyAction.REJECT
            reason = f"Majority failure: {len(failing)}/{len(evaluated)} layers failed"
        elif len(passing) < self.min_passing_layers:
            action = PolicyAction.REQUIRE_REATTEST
            reason = f"Insufficient passing layers: {len(passing)}/{self.min_passing_layers} required"
        elif failing:
            action = self.failure_action
            reason = f"Non-critical failure(s): {[r.name for r in failing]}"
        elif warnings:
            action = PolicyAction.MONITOR
            reason = f"Warnings: {[r.name for r in warnings]}"
        else:
            action = PolicyAction.ALLOW
            reason = f"All {len(passing)} layers passed"
        
        # Aggregate score (MIN, not average — per trust-stack-compositor)
        scores = [r.score for r in evaluated]
        aggregate = min(scores) if scores else 0.0
        
        # DMARC-style report
        return {
            "action": action.value,
            "reason": reason,
            "aggregate_score": round(aggregate, 3),
            "layers_evaluated": len(evaluated),
            "layers_passing": len(passing),
            "layers_failing": len(failing),
            "layers_warning": len(warnings),
            "critical_ok": len(critical_failures) == 0,
            "details": {r.name: {"verdict": r.verdict.value, "score": round(r.score, 3)} for r in results},
            "recommended_response": _response_guidance(action)
        }


def _response_guidance(action: PolicyAction) -> str:
    return {
        PolicyAction.ALLOW: "Proceed with full scope",
        PolicyAction.MONITOR: "Proceed but log for review",
        PolicyAction.DEGRADE_SCOPE: "Narrow trust scope. Restrict to read-only or verified-only interactions",
        PolicyAction.REQUIRE_REATTEST: "Demand fresh attestation before proceeding. Stale credentials",
        PolicyAction.REJECT: "Refuse interaction. Critical trust failure"
    }[action]


def demo():
    policy = TrustPolicy(min_passing_layers=3, critical_layers=["genesis", "independence"])
    
    scenarios = {
        "healthy_agent": [
            LayerResult("genesis", LayerVerdict.PASS, 0.95, "Founded 90d ago, diverse"),
            LayerResult("independence", LayerVerdict.PASS, 0.88, "4/5 unique operators"),
            LayerResult("monoculture", LayerVerdict.PASS, 0.82, "3 model families"),
            LayerResult("witness", LayerVerdict.PASS, 0.91, "7/7 receipts verified"),
            LayerResult("revocation", LayerVerdict.PASS, 0.97, "No revocations"),
        ],
        "genesis_failure": [
            LayerResult("genesis", LayerVerdict.FAIL, 0.10, "Unknown operator"),
            LayerResult("independence", LayerVerdict.PASS, 0.80, "Diverse"),
            LayerResult("monoculture", LayerVerdict.PASS, 0.75, "OK"),
            LayerResult("witness", LayerVerdict.PASS, 0.85, "Verified"),
            LayerResult("revocation", LayerVerdict.PASS, 0.90, "Clean"),
        ],
        "degraded_trust": [
            LayerResult("genesis", LayerVerdict.PASS, 0.90, "Known operator"),
            LayerResult("independence", LayerVerdict.PASS, 0.70, "Marginal diversity"),
            LayerResult("monoculture", LayerVerdict.FAIL, 0.25, "4/5 same model family"),
            LayerResult("witness", LayerVerdict.WARN, 0.55, "2 stale witnesses"),
            LayerResult("revocation", LayerVerdict.PASS, 0.80, "Clean"),
        ],
        "sybil_farm": [
            LayerResult("genesis", LayerVerdict.FAIL, 0.05, "Burst registration"),
            LayerResult("independence", LayerVerdict.FAIL, 0.08, "All same operator"),
            LayerResult("monoculture", LayerVerdict.FAIL, 0.10, "Single model"),
            LayerResult("witness", LayerVerdict.FAIL, 0.12, "Self-attested only"),
            LayerResult("revocation", LayerVerdict.WARN, 0.40, "No history"),
        ],
    }
    
    for name, layers in scenarios.items():
        result = policy.evaluate(layers)
        print(f"\n{'='*50}")
        print(f"Scenario: {name}")
        print(f"Action: {result['action']} | Score: {result['aggregate_score']}")
        print(f"Layers: {result['layers_passing']}✓ {result['layers_failing']}✗ {result['layers_warning']}⚠")
        print(f"Reason: {result['reason']}")
        print(f"Response: {result['recommended_response']}")


if __name__ == "__main__":
    demo()
