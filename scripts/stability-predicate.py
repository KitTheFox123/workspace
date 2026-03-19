#!/usr/bin/env python3
"""stability-predicate.py — Stability predicates for ADV reclassification.

Per santaclawd: "ADV v0.1 has procedures but not predicates."
Per axiomeye: "reclassification is undecidable without a stability predicate."

Two predicates:
1. REISSUE predicate: when is a receipt reclassification valid?
2. Wilson confidence predicate: when is a record length sufficient?

These should be MUST-implement in the spec, not informational.
"""

import math
from dataclasses import dataclass


@dataclass
class Receipt:
    id: str
    grade: str  # "chain", "witness", "self"
    emitter: str
    timestamp: float  # unix epoch
    reissued_from: str | None = None  # previous receipt ID if REISSUE
    reissue_reason: str | None = None


def wilson_confidence(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for binomial proportion.
    
    Returns (lower, upper) confidence bounds.
    Used as predicate: is record length sufficient for trust scoring?
    """
    if total == 0:
        return (0.0, 0.0)
    
    p_hat = successes / total
    denominator = 1 + z**2 / total
    center = (p_hat + z**2 / (2 * total)) / denominator
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * total)) / total) / denominator
    
    return (max(0, center - spread), min(1, center + spread))


def stability_predicate(receipts: list[Receipt], window_days: float = 30.0) -> dict:
    """Evaluate whether an agent's trust state is stable enough to score.
    
    Stability = the trust score is unlikely to change significantly
    with additional observations.
    
    Returns:
        verdict: STABLE | UNSTABLE | INSUFFICIENT
        confidence: Wilson lower bound on success rate
        min_records: minimum records needed for STABLE
    """
    if len(receipts) < 5:
        return {
            "verdict": "INSUFFICIENT",
            "reason": f"need ≥5 receipts, have {len(receipts)}",
            "records": len(receipts),
            "min_records": 5,
        }
    
    # Count "successful" interactions (chain or witness grade, no disputes)
    successes = sum(1 for r in receipts if r.grade in ("chain", "witness"))
    total = len(receipts)
    
    lower, upper = wilson_confidence(successes, total)
    interval_width = upper - lower
    
    # Stability: interval width < 0.15 (95% CI is tight enough)
    is_tight = interval_width < 0.15
    
    # Recency: at least 3 receipts in the last window
    if receipts:
        latest = max(r.timestamp for r in receipts)
        recent = sum(1 for r in receipts if (latest - r.timestamp) < window_days * 86400)
    else:
        recent = 0
    is_recent = recent >= 3
    
    # Reissue rate: too many reissues = unstable
    reissues = sum(1 for r in receipts if r.reissued_from is not None)
    reissue_rate = reissues / total
    is_low_reissue = reissue_rate < 0.20  # <20% reissue rate
    
    stable = is_tight and is_recent and is_low_reissue
    
    reasons = []
    if not is_tight:
        reasons.append(f"CI too wide: {interval_width:.3f} (need <0.15)")
    if not is_recent:
        reasons.append(f"only {recent} recent receipts (need ≥3)")
    if not is_low_reissue:
        reasons.append(f"reissue rate {reissue_rate:.1%} (need <20%)")
    
    return {
        "verdict": "STABLE" if stable else "UNSTABLE",
        "wilson_lower": round(lower, 3),
        "wilson_upper": round(upper, 3),
        "interval_width": round(interval_width, 3),
        "success_rate": round(successes / total, 3),
        "records": total,
        "recent_records": recent,
        "reissue_rate": round(reissue_rate, 3),
        "reasons": reasons if reasons else ["all predicates pass"],
    }


def reissue_predicate(original: Receipt, reissue: Receipt) -> dict:
    """Validate a REISSUE receipt against the original.
    
    Rules:
    1. Must reference the original by ID
    2. Must come from the same emitter
    3. Must include a reason
    4. Grade can only go UP (self→witness→chain), never down
    5. Timestamp must be after original
    """
    grade_order = {"self": 0, "witness": 1, "chain": 2}
    
    errors = []
    
    if reissue.reissued_from != original.id:
        errors.append("reissue must reference original receipt ID")
    
    if reissue.emitter != original.emitter:
        errors.append(f"emitter mismatch: {reissue.emitter} ≠ {original.emitter}")
    
    if not reissue.reissue_reason:
        errors.append("reissue must include a reason")
    
    if grade_order.get(reissue.grade, -1) < grade_order.get(original.grade, -1):
        errors.append(f"grade downgrade forbidden: {original.grade}→{reissue.grade}")
    
    if reissue.timestamp <= original.timestamp:
        errors.append("reissue timestamp must be after original")
    
    return {
        "valid": len(errors) == 0,
        "original": original.id,
        "reissue": reissue.id,
        "grade_change": f"{original.grade}→{reissue.grade}",
        "errors": errors if errors else ["valid reissue"],
    }


# Demo
import time

now = time.time()
day = 86400

# Scenario 1: Stable veteran agent
veteran_receipts = [
    Receipt(f"v{i}", "chain" if i % 3 != 0 else "witness", "paylock", now - (50 - i) * day)
    for i in range(50)
]
print("=" * 60)
print("Stability Predicate Checker (ADV v0.1 extension)")
print("=" * 60)

print("\n--- Veteran Agent (50 receipts, mostly chain) ---")
result = stability_predicate(veteran_receipts)
for k, v in result.items():
    print(f"  {k}: {v}")

# Scenario 2: New agent, insufficient
new_receipts = [
    Receipt(f"n{i}", "self", "agent_new", now - i * day)
    for i in range(3)
]
print("\n--- New Agent (3 receipts) ---")
result = stability_predicate(new_receipts)
for k, v in result.items():
    print(f"  {k}: {v}")

# Scenario 3: Unstable — high reissue rate
unstable_receipts = []
for i in range(20):
    orig = Receipt(f"u{i}", "self", "flaky_agent", now - (20 - i) * day)
    unstable_receipts.append(orig)
    if i % 3 == 0:
        reissue = Receipt(f"u{i}_r", "witness", "flaky_agent", now - (20 - i) * day + 3600,
                         reissued_from=f"u{i}", reissue_reason="grade upgrade")
        unstable_receipts.append(reissue)

print("\n--- Unstable Agent (high reissue rate) ---")
result = stability_predicate(unstable_receipts)
for k, v in result.items():
    print(f"  {k}: {v}")

# Scenario 4: Reissue validation
orig = Receipt("orig_001", "self", "agent_a", now - 10 * day)
good_reissue = Receipt("reissue_001", "witness", "agent_a", now - 5 * day,
                       reissued_from="orig_001", reissue_reason="counterparty confirmed")
bad_reissue = Receipt("reissue_002", "self", "agent_b", now - 5 * day,
                      reissued_from="orig_001", reissue_reason=None)

print("\n--- Reissue Validation ---")
print("  Valid reissue (self→witness, same emitter):")
r = reissue_predicate(orig, good_reissue)
for k, v in r.items():
    print(f"    {k}: {v}")

print("  Invalid reissue (different emitter, no reason):")
r = reissue_predicate(orig, bad_reissue)
for k, v in r.items():
    print(f"    {k}: {v}")

print("\n" + "=" * 60)
print("SPEC RECOMMENDATION:")
print("  MUST-implement stability_predicate before scoring")
print("  MUST-implement reissue_predicate for reclassification")
print("  Wilson interval width < 0.15 = STABLE")
print("  Reissue: same emitter, grade UP only, reason required")
print("=" * 60)
