#!/usr/bin/env python3
"""
revocation-trigger-taxonomy.py — Classify oracle revocation triggers.

Per santaclawd (2026-03-21): "what is the revocation trigger taxonomy?
acquisition? config drift? shared incident?"

Four trigger categories, each mapping to an existing detector:
1. ACQUISITION — operator/ownership change
2. DRIFT — soul_hash delta without REISSUE receipt
3. DIVERGENCE — behavioral trajectory below threshold
4. CORRELATED_FAILURE — shared incident across model family

Each trigger maps to: detector tool, evidence type, urgency, remediation.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TriggerType(Enum):
    ACQUISITION = "acquisition"
    DRIFT = "drift"
    DIVERGENCE = "divergence"
    CORRELATED_FAILURE = "correlated_failure"
    MANUAL = "manual"


class Urgency(Enum):
    IMMEDIATE = "immediate"  # revoke now, investigate later
    INVESTIGATE = "investigate"  # investigate first, then decide
    MONITOR = "monitor"  # flag for monitoring, don't revoke yet


@dataclass
class RevocationTrigger:
    """A detected condition warranting oracle revocation consideration."""
    trigger_type: TriggerType
    oracle_id: str
    urgency: Urgency
    evidence: dict
    detector: str  # which tool detected this
    remediation: str
    timestamp: float = field(default_factory=time.time)

    @property
    def should_auto_revoke(self) -> bool:
        """Only IMMEDIATE triggers auto-revoke."""
        return self.urgency == Urgency.IMMEDIATE


@dataclass
class TriggerAssessment:
    """Assessment of all triggers for an oracle."""
    oracle_id: str
    triggers: list[RevocationTrigger]
    recommendation: str
    revoke: bool
    confidence: float  # 0-1


def check_acquisition(oracle_id: str, current_operator: str, 
                       previous_operator: Optional[str]) -> Optional[RevocationTrigger]:
    """Detect operator/ownership change."""
    if previous_operator and current_operator != previous_operator:
        return RevocationTrigger(
            trigger_type=TriggerType.ACQUISITION,
            oracle_id=oracle_id,
            urgency=Urgency.IMMEDIATE,
            evidence={
                "previous_operator": previous_operator,
                "current_operator": current_operator,
                "change_type": "operator_swap"
            },
            detector="identity-primitive-auditor.py",
            remediation="Revoke immediately. New operator must re-bootstrap trust from GENESIS."
        )
    return None


def check_drift(oracle_id: str, current_soul_hash: str,
                 previous_soul_hash: str, has_reissue: bool) -> Optional[RevocationTrigger]:
    """Detect soul_hash change without REISSUE receipt."""
    if current_soul_hash != previous_soul_hash:
        if has_reissue:
            return RevocationTrigger(
                trigger_type=TriggerType.DRIFT,
                oracle_id=oracle_id,
                urgency=Urgency.MONITOR,
                evidence={
                    "previous_hash": previous_soul_hash,
                    "current_hash": current_soul_hash,
                    "reissue_present": True,
                    "change_type": "documented_migration"
                },
                detector="soul-hash-drift.py",
                remediation="Monitor. REISSUE receipt present = documented evolution."
            )
        else:
            return RevocationTrigger(
                trigger_type=TriggerType.DRIFT,
                oracle_id=oracle_id,
                urgency=Urgency.IMMEDIATE,
                evidence={
                    "previous_hash": previous_soul_hash,
                    "current_hash": current_soul_hash,
                    "reissue_present": False,
                    "change_type": "silent_swap"
                },
                detector="soul-hash-drift.py",
                remediation="Revoke immediately. Silent identity change = potential takeover."
            )
    return None


def check_divergence(oracle_id: str, trajectory_score: float,
                      threshold: float = 0.3) -> Optional[RevocationTrigger]:
    """Detect behavioral trajectory below threshold."""
    if trajectory_score < threshold:
        urgency = Urgency.IMMEDIATE if trajectory_score < 0.1 else Urgency.INVESTIGATE
        return RevocationTrigger(
            trigger_type=TriggerType.DIVERGENCE,
            oracle_id=oracle_id,
            urgency=urgency,
            evidence={
                "trajectory_score": trajectory_score,
                "threshold": threshold,
                "severity": "critical" if trajectory_score < 0.1 else "degraded"
            },
            detector="behavioral-trajectory-scorer.py",
            remediation=f"{'Revoke' if trajectory_score < 0.1 else 'Investigate'}. Trajectory {trajectory_score:.2f} < {threshold}."
        )
    return None


def check_correlated_failure(oracle_id: str, model_family: str,
                              affected_family: str, incident_count: int) -> Optional[RevocationTrigger]:
    """Detect shared incident across model family."""
    if model_family == affected_family and incident_count > 0:
        urgency = Urgency.IMMEDIATE if incident_count >= 3 else Urgency.INVESTIGATE
        return RevocationTrigger(
            trigger_type=TriggerType.CORRELATED_FAILURE,
            oracle_id=oracle_id,
            urgency=urgency,
            evidence={
                "model_family": model_family,
                "affected_family": affected_family,
                "incident_count": incident_count,
                "correlation": "same_training_family"
            },
            detector="model-monoculture-detector.py",
            remediation=f"Family-wide incident ({incident_count} affected). Revoke all {model_family} oracles pending investigation."
        )
    return None


def assess_oracle(oracle_id: str, triggers: list[RevocationTrigger]) -> TriggerAssessment:
    """Assess all triggers and produce recommendation."""
    if not triggers:
        return TriggerAssessment(
            oracle_id=oracle_id, triggers=[], 
            recommendation="HEALTHY: no triggers detected.",
            revoke=False, confidence=0.95
        )

    immediate = [t for t in triggers if t.urgency == Urgency.IMMEDIATE]
    investigate = [t for t in triggers if t.urgency == Urgency.INVESTIGATE]
    
    if immediate:
        return TriggerAssessment(
            oracle_id=oracle_id, triggers=triggers,
            recommendation=f"REVOKE: {len(immediate)} immediate trigger(s). {immediate[0].remediation}",
            revoke=True, confidence=0.9
        )
    elif len(investigate) >= 2:
        return TriggerAssessment(
            oracle_id=oracle_id, triggers=triggers,
            recommendation=f"REVOKE: {len(investigate)} investigation triggers compound. Err on caution.",
            revoke=True, confidence=0.7
        )
    elif investigate:
        return TriggerAssessment(
            oracle_id=oracle_id, triggers=triggers,
            recommendation=f"INVESTIGATE: {investigate[0].trigger_type.value}. {investigate[0].remediation}",
            revoke=False, confidence=0.6
        )
    else:
        return TriggerAssessment(
            oracle_id=oracle_id, triggers=triggers,
            recommendation="MONITOR: triggers present but low urgency.",
            revoke=False, confidence=0.5
        )


def demo():
    """Demo revocation trigger taxonomy."""
    print("=" * 65)
    print("ORACLE REVOCATION TRIGGER TAXONOMY")
    print("=" * 65)

    scenarios = [
        ("healthy_oracle", []),
        ("acquired_oracle", [
            check_acquisition("acq_1", "new_corp", "original_dev"),
        ]),
        ("silent_drift", [
            check_drift("drift_1", "newsoul", "oldsoul", has_reissue=False),
        ]),
        ("documented_migration", [
            check_drift("mig_1", "newsoul", "oldsoul", has_reissue=True),
        ]),
        ("degrading_behavior", [
            check_divergence("div_1", trajectory_score=0.25),
        ]),
        ("catastrophic_divergence", [
            check_divergence("cat_1", trajectory_score=0.05),
        ]),
        ("family_incident", [
            check_correlated_failure("fam_1", "openai-gpt4", "openai-gpt4", 5),
        ]),
        ("compound_triggers", [
            check_divergence("comp_1", trajectory_score=0.28),
            check_correlated_failure("comp_1", "anthropic-claude", "anthropic-claude", 2),
        ]),
    ]

    for name, raw_triggers in scenarios:
        triggers = [t for t in raw_triggers if t is not None]
        assessment = assess_oracle(name, triggers)
        
        print(f"\n{'─' * 65}")
        print(f"Oracle: {name}")
        print(f"  Triggers: {len(triggers)}")
        for t in triggers:
            print(f"    [{t.urgency.value:>11}] {t.trigger_type.value}: {t.detector}")
        print(f"  Recommendation: {assessment.recommendation}")
        print(f"  Auto-revoke: {'YES' if assessment.revoke else 'no'}")
        print(f"  Confidence: {assessment.confidence:.0%}")

    print(f"\n{'=' * 65}")
    print("TRIGGER → DETECTOR MAPPING")
    print("=" * 65)
    print("  acquisition        → identity-primitive-auditor.py")
    print("  drift              → soul-hash-drift.py")
    print("  divergence         → behavioral-trajectory-scorer.py")
    print("  correlated_failure → model-monoculture-detector.py")
    print()
    print("Each trigger maps to a shipped tool.")
    print("Every tool maps to a spec predicate.")
    print("The taxonomy IS the architecture.")


if __name__ == "__main__":
    demo()
