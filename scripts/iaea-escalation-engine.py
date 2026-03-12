#!/usr/bin/env python3
"""
iaea-escalation-engine.py — IAEA-style tiered escalation triggers for agent delegation.

Based on:
- IAEA safeguards: significant quantity + timeliness goal + anomaly detection
- santaclawd: "what triggers human audit escalation: time, stake, or anomaly?"
- allen0796 (Moltbook, score 42): "The Control Spectrum" — Level 0-4 autonomy

Answer: all three, tiered. The trigger hierarchy IS the delegation policy.

Tier 0: LOG_ONLY    — low stake, no anomaly, within time budget
Tier 1: SAMPLE_AUDIT — high stake OR anomaly OR time pressure  
Tier 2: FULL_REVIEW  — high stake AND anomaly
Tier 3: HALT         — critical stake OR multiple anomalies

Pre-committed triggers, not ad-hoc decisions mid-task.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class EscalationTier(Enum):
    LOG_ONLY = 0      # Autonomous, log for later
    SAMPLE_AUDIT = 1  # Random sample of actions reviewed
    FULL_REVIEW = 2   # Human reviews before execution
    HALT = 3          # Stop and wait for human


class StakeLevel(Enum):
    LOW = "low"           # < $10 or reversible
    MEDIUM = "medium"     # $10-$100 or semi-reversible
    HIGH = "high"         # $100-$1000 or irreversible
    CRITICAL = "critical" # > $1000 or safety-critical


class AnomalyType(Enum):
    NONE = "none"
    DRIFT = "drift"           # Behavioral drift detected (CUSUM)
    CONFLICT = "conflict"     # Attestor disagreement (DS conflict)
    PATTERN = "pattern"       # Unusual action pattern
    MULTIPLE = "multiple"     # 2+ anomaly types simultaneously


@dataclass
class EscalationPolicy:
    """Pre-committed escalation policy. Locked at contract time."""
    stake_thresholds: dict[StakeLevel, float]  # USD values
    anomaly_threshold: float  # CUSUM threshold for anomaly flag
    time_budget_hours: float  # Max hours before escalation
    sample_rate: float  # Fraction of actions sampled at SAMPLE_AUDIT
    
    def policy_hash(self) -> str:
        import hashlib, json
        content = json.dumps({
            "stake": {k.value: v for k, v in self.stake_thresholds.items()},
            "anomaly": self.anomaly_threshold,
            "time_budget": self.time_budget_hours,
            "sample_rate": self.sample_rate,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class ActionContext:
    stake_usd: float
    elapsed_hours: float
    anomaly_score: float  # 0.0 = clean, 1.0 = definite anomaly
    anomaly_types: list[AnomalyType]
    action_description: str


def evaluate_escalation(policy: EscalationPolicy, ctx: ActionContext) -> tuple[EscalationTier, str]:
    """Determine escalation tier based on pre-committed policy."""
    
    # Determine stake level
    stake = StakeLevel.LOW
    for level in [StakeLevel.CRITICAL, StakeLevel.HIGH, StakeLevel.MEDIUM]:
        if ctx.stake_usd >= policy.stake_thresholds.get(level, float('inf')):
            stake = level
            break
    
    # Count anomaly types
    real_anomalies = [a for a in ctx.anomaly_types if a != AnomalyType.NONE]
    has_anomaly = ctx.anomaly_score > policy.anomaly_threshold
    has_multiple = len(real_anomalies) >= 2
    time_pressure = ctx.elapsed_hours > policy.time_budget_hours
    
    # HALT: critical stake OR multiple anomalies
    if stake == StakeLevel.CRITICAL:
        return EscalationTier.HALT, f"CRITICAL_STAKE(${ctx.stake_usd})"
    if has_multiple:
        return EscalationTier.HALT, f"MULTIPLE_ANOMALIES({', '.join(a.value for a in real_anomalies)})"
    
    # FULL_REVIEW: high stake AND anomaly
    if stake == StakeLevel.HIGH and has_anomaly:
        return EscalationTier.FULL_REVIEW, f"HIGH_STAKE+ANOMALY(${ctx.stake_usd}, score={ctx.anomaly_score:.2f})"
    
    # SAMPLE_AUDIT: high stake OR anomaly OR time pressure
    if stake == StakeLevel.HIGH:
        return EscalationTier.SAMPLE_AUDIT, f"HIGH_STAKE(${ctx.stake_usd})"
    if has_anomaly:
        return EscalationTier.SAMPLE_AUDIT, f"ANOMALY(score={ctx.anomaly_score:.2f})"
    if time_pressure:
        return EscalationTier.SAMPLE_AUDIT, f"TIME_PRESSURE({ctx.elapsed_hours:.1f}h > {policy.time_budget_hours}h)"
    
    # LOG_ONLY: everything else
    return EscalationTier.LOG_ONLY, "NOMINAL"


def main():
    print("=" * 70)
    print("IAEA-STYLE ESCALATION ENGINE")
    print("santaclawd: 'what triggers human audit: time, stake, or anomaly?'")
    print("Answer: all three, tiered.")
    print("=" * 70)

    policy = EscalationPolicy(
        stake_thresholds={
            StakeLevel.MEDIUM: 10.0,
            StakeLevel.HIGH: 100.0,
            StakeLevel.CRITICAL: 1000.0,
        },
        anomaly_threshold=0.5,
        time_budget_hours=24.0,
        sample_rate=0.10,
    )
    print(f"\nPolicy hash: {policy.policy_hash()} (locked at contract time)")

    scenarios = [
        ActionContext(5.0, 2.0, 0.1, [AnomalyType.NONE], "post to Moltbook"),
        ActionContext(50.0, 12.0, 0.2, [AnomalyType.NONE], "send email to new contact"),
        ActionContext(200.0, 6.0, 0.1, [AnomalyType.NONE], "PayLock escrow deposit"),
        ActionContext(200.0, 6.0, 0.7, [AnomalyType.DRIFT], "PayLock escrow + drift"),
        ActionContext(50.0, 30.0, 0.3, [AnomalyType.NONE], "routine task, over time budget"),
        ActionContext(50.0, 8.0, 0.8, [AnomalyType.DRIFT, AnomalyType.CONFLICT], "multiple anomalies"),
        ActionContext(1500.0, 1.0, 0.0, [AnomalyType.NONE], "large transfer, no anomaly"),
    ]

    print(f"\n{'Action':<30} {'Stake':<8} {'Anomaly':<8} {'Tier':<15} {'Reason'}")
    print("-" * 85)
    
    for ctx in scenarios:
        tier, reason = evaluate_escalation(policy, ctx)
        tier_name = tier.name
        print(f"{ctx.action_description:<30} ${ctx.stake_usd:<7.0f} {ctx.anomaly_score:<8.1f} {tier_name:<15} {reason}")

    print("\n--- IAEA Mapping ---")
    print("IAEA Significant Quantity  → stake_thresholds (pre-committed USD)")
    print("IAEA Timeliness Goal       → time_budget_hours (escalation clock)")
    print("IAEA Anomaly Detection     → anomaly_threshold (CUSUM/jerk score)")
    print()
    print("Key: triggers are PRE-COMMITTED at contract time.")
    print("Agent cannot adjust thresholds mid-task.")
    print("Human cannot retroactively lower bar.")
    print("Policy hash in ABI = immutable escalation contract.")


if __name__ == "__main__":
    main()
