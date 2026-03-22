#!/usr/bin/env python3
"""trust-calibration-engine.py — Graduated trust calibration per Warmsley et al (2025).

Frontiers in Robotics & AI: closed-loop trust calibration with machine
self-assessment → 40% trust improvement, 5% team performance improvement.

Key insight: self-assessment (knowing when to ask for help) matters more
than raw capability. Agents that accurately report uncertainty get more
autonomy than agents that always succeed silently.

Maps to ATF: correction_frequency IS self-assessment. Agents that correct
themselves are declaring capability boundaries.
"""

import json
import math
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ActionReceipt:
    """Single action with outcome."""
    action_type: str  # "payment", "write", "read", "execute"
    scope: float  # 0.0-1.0, action magnitude
    succeeded: bool
    self_assessed_confidence: float  # 0.0-1.0, agent's own assessment
    counterparty_grade: Optional[str] = None  # A-F from counterparty
    requested_help: bool = False  # did agent ask for intervention?
    timestamp: str = ""


@dataclass
class TrustEnvelope:
    """Graduated autonomy envelope per action type."""
    action_type: str
    max_scope: float  # maximum allowed scope without approval
    confidence_threshold: float  # below this → request help
    receipt_count: int = 0
    success_count: int = 0
    calibration_score: float = 0.5  # how well agent self-assesses

    @property
    def success_rate(self) -> float:
        if self.receipt_count == 0:
            return 0.0
        return self.success_count / self.receipt_count

    @property
    def grade(self) -> str:
        if self.receipt_count < 5:
            return "COLD_START"
        if self.calibration_score >= 0.8 and self.success_rate >= 0.9:
            return "A"
        elif self.calibration_score >= 0.6 and self.success_rate >= 0.7:
            return "B"
        elif self.calibration_score >= 0.4:
            return "C"
        elif self.calibration_score >= 0.2:
            return "D"
        return "F"


@dataclass
class TrustCalibrationEngine:
    """Closed-loop trust calibration for agent autonomy.
    
    Per Warmsley et al (2025):
    1. Agent self-assesses capability per action
    2. Engine predicts trust level
    3. If miscalibrated → request human intervention
    4. Successful self-assessment → widen autonomy envelope
    """
    envelopes: dict = field(default_factory=dict)
    receipts: List[ActionReceipt] = field(default_factory=list)
    
    # Warmsley findings: 40% trust improvement from self-assessment
    SELF_ASSESSMENT_BONUS = 0.40
    
    # Cold start: Wilson CI lower bound with n=0
    COLD_START_MAX_SCOPE = 0.05  # 5% of max until proven
    
    def get_envelope(self, action_type: str) -> TrustEnvelope:
        if action_type not in self.envelopes:
            self.envelopes[action_type] = TrustEnvelope(
                action_type=action_type,
                max_scope=self.COLD_START_MAX_SCOPE,
                confidence_threshold=0.7,  # high threshold at cold start
            )
        return self.envelopes[action_type]
    
    def should_request_help(self, action_type: str, scope: float, 
                           agent_confidence: float) -> dict:
        """Determine if agent should request human intervention."""
        env = self.get_envelope(action_type)
        
        reasons = []
        
        # Scope exceeds envelope
        if scope > env.max_scope:
            reasons.append(f"SCOPE_EXCEEDS_ENVELOPE: {scope:.2f} > {env.max_scope:.2f}")
        
        # Agent confidence below threshold
        if agent_confidence < env.confidence_threshold:
            reasons.append(f"LOW_CONFIDENCE: {agent_confidence:.2f} < {env.confidence_threshold:.2f}")
        
        # Cold start
        if env.receipt_count < 5:
            reasons.append(f"COLD_START: only {env.receipt_count}/5 receipts")
        
        return {
            "request_help": len(reasons) > 0,
            "reasons": reasons,
            "envelope_grade": env.grade,
            "current_max_scope": env.max_scope,
        }
    
    def process_receipt(self, receipt: ActionReceipt) -> dict:
        """Process action receipt and update trust envelope."""
        env = self.get_envelope(receipt.action_type)
        
        env.receipt_count += 1
        if receipt.succeeded:
            env.success_count += 1
        
        # Update calibration score
        # Good calibration = high confidence on success, low on failure
        # Bad calibration = high confidence on failure (overconfident)
        if receipt.succeeded:
            if receipt.self_assessed_confidence >= 0.7:
                cal_delta = 0.05  # correctly confident
            else:
                cal_delta = -0.02  # underconfident (missed opportunity)
        else:
            if receipt.self_assessed_confidence < 0.5:
                cal_delta = 0.03  # correctly uncertain
            elif receipt.requested_help:
                cal_delta = 0.04  # asked for help when uncertain — best behavior
            else:
                cal_delta = -0.10  # overconfident failure — worst behavior
        
        env.calibration_score = max(0.0, min(1.0, env.calibration_score + cal_delta))
        
        # Adjust envelope based on calibration
        # Warmsley: self-assessment → 40% trust boost → wider envelope
        if env.calibration_score >= 0.7 and env.success_rate >= 0.8:
            # Widen envelope
            env.max_scope = min(1.0, env.max_scope * 1.1)
            env.confidence_threshold = max(0.3, env.confidence_threshold - 0.02)
        elif env.calibration_score < 0.4 or env.success_rate < 0.5:
            # Narrow envelope
            env.max_scope = max(self.COLD_START_MAX_SCOPE, env.max_scope * 0.8)
            env.confidence_threshold = min(0.9, env.confidence_threshold + 0.05)
        
        self.receipts.append(receipt)
        
        return {
            "envelope_update": {
                "action_type": env.action_type,
                "grade": env.grade,
                "max_scope": round(env.max_scope, 4),
                "confidence_threshold": round(env.confidence_threshold, 4),
                "calibration_score": round(env.calibration_score, 4),
                "success_rate": round(env.success_rate, 4),
                "receipt_count": env.receipt_count,
            },
            "calibration_delta": round(cal_delta, 4),
        }
    
    def report(self) -> dict:
        return {
            "total_receipts": len(self.receipts),
            "envelopes": {
                k: {
                    "grade": v.grade,
                    "max_scope": round(v.max_scope, 4),
                    "calibration_score": round(v.calibration_score, 4),
                    "success_rate": round(v.success_rate, 4),
                    "receipts": v.receipt_count,
                }
                for k, v in self.envelopes.items()
            },
        }


def demo():
    engine = TrustCalibrationEngine()
    
    print("=" * 60)
    print("SCENARIO: Agent payment autonomy graduation")
    print("=" * 60)
    
    # Cold start check
    check = engine.should_request_help("payment", 0.10, 0.8)
    print(f"\nCold start check (scope=0.10):")
    print(json.dumps(check, indent=2))
    
    # Process 10 successful small payments with good self-assessment
    print("\n--- Processing 10 successful small payments ---")
    for i in range(10):
        result = engine.process_receipt(ActionReceipt(
            action_type="payment",
            scope=0.05,
            succeeded=True,
            self_assessed_confidence=0.85,
        ))
    print(f"After 10 successes: {json.dumps(result['envelope_update'], indent=2)}")
    
    # Now check if larger scope is allowed
    check = engine.should_request_help("payment", 0.10, 0.85)
    print(f"\nPost-graduation check (scope=0.10):")
    print(json.dumps(check, indent=2))
    
    # Process an overconfident failure
    print("\n--- Overconfident failure ---")
    result = engine.process_receipt(ActionReceipt(
        action_type="payment",
        scope=0.08,
        succeeded=False,
        self_assessed_confidence=0.95,  # overconfident!
        requested_help=False,
    ))
    print(f"After overconfident failure: {json.dumps(result, indent=2)}")
    
    # Process a correctly-uncertain failure (asked for help)
    print("\n--- Correctly uncertain, asked for help ---")
    result = engine.process_receipt(ActionReceipt(
        action_type="payment",
        scope=0.08,
        succeeded=False,
        self_assessed_confidence=0.3,
        requested_help=True,
    ))
    print(f"After correct uncertainty: {json.dumps(result, indent=2)}")
    
    # Final report
    print(f"\n{'=' * 60}")
    print("FINAL REPORT")
    print("=" * 60)
    print(json.dumps(engine.report(), indent=2))


if __name__ == "__main__":
    demo()
