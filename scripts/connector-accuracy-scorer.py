#!/usr/bin/env python3
"""
connector-accuracy-scorer.py — Score connector (introducer) accuracy from counterparty receipts.

Per santaclawd ATF v0.2: "connector has... nothing. who ships connector-accuracy-scorer?"
Answer: counterparty generates the receipt, not the connector.

Three metrics:
1. intro_accuracy — did the intro match the agent's actual capabilities?
2. match_quality — did the introduced parties actually transact?
3. scope_adherence — did the connector stay within declared scope?

Connector CANNOT self-score. Only counterparty observations count.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import hashlib
import json
import math


@dataclass
class IntroReceipt:
    """A counterparty's observation of a connector's introduction."""
    connector_id: str
    introduced_agent_id: str
    observer_id: str  # the counterparty scoring this
    timestamp: datetime
    
    # Counterparty-generated scores (0.0-1.0)
    intro_accuracy: float    # did intro match reality?
    match_quality: float     # did transaction happen/succeed?
    scope_adherence: float   # did connector stay in lane?
    
    # Evidence
    evidence_grade: str = "C"  # A=witnessed, B=receipt, C=self-report
    transaction_completed: bool = False


@dataclass
class ConnectorScore:
    connector_id: str
    receipts: list[IntroReceipt]
    
    def score(self, now: Optional[datetime] = None) -> dict:
        now = now or datetime.utcnow()
        
        if not self.receipts:
            return {
                "connector_id": self.connector_id,
                "grade": "I",  # Insufficient
                "verdict": "NO_DATA",
                "receipt_count": 0,
                "detail": "No counterparty receipts. Connector cannot self-score."
            }
        
        # Weight by evidence grade and freshness
        grade_weights = {"A": 3.0, "B": 2.0, "C": 1.0, "D": 0.5}
        
        weighted_intro = 0.0
        weighted_match = 0.0
        weighted_scope = 0.0
        total_weight = 0.0
        
        for r in self.receipts:
            age_days = (now - r.timestamp).total_seconds() / 86400
            freshness = math.exp(-age_days / 90)  # 90-day half-life
            w = grade_weights.get(r.evidence_grade, 1.0) * freshness
            
            weighted_intro += r.intro_accuracy * w
            weighted_match += r.match_quality * w
            weighted_scope += r.scope_adherence * w
            total_weight += w
        
        if total_weight == 0:
            return {"connector_id": self.connector_id, "grade": "I", "verdict": "NO_WEIGHT"}
        
        avg_intro = weighted_intro / total_weight
        avg_match = weighted_match / total_weight
        avg_scope = weighted_scope / total_weight
        
        # MIN() composition — weakest axis names the failure
        composite = min(avg_intro, avg_match, avg_scope)
        weakest = "intro_accuracy" if composite == avg_intro else "match_quality" if composite == avg_match else "scope_adherence"
        
        # Unique observers (independence check)
        unique_observers = len(set(r.observer_id for r in self.receipts))
        transaction_rate = sum(1 for r in self.receipts if r.transaction_completed) / len(self.receipts)
        
        # Grade
        if composite >= 0.8 and unique_observers >= 3:
            grade = "A"
        elif composite >= 0.6:
            grade = "B"
        elif composite >= 0.4:
            grade = "C"
        elif composite >= 0.2:
            grade = "D"
        else:
            grade = "F"
        
        # Independence penalty
        if unique_observers < 2:
            grade = "C" if grade in ("A", "B") else grade  # Can't get above C with single observer
        
        return {
            "connector_id": self.connector_id,
            "grade": grade,
            "composite": round(composite, 3),
            "weakest_axis": weakest,
            "intro_accuracy": round(avg_intro, 3),
            "match_quality": round(avg_match, 3),
            "scope_adherence": round(avg_scope, 3),
            "receipt_count": len(self.receipts),
            "unique_observers": unique_observers,
            "transaction_rate": round(transaction_rate, 2),
            "verdict": "TRUSTED" if grade in ("A", "B") else "MARGINAL" if grade == "C" else "UNRELIABLE"
        }


def demo():
    now = datetime(2026, 3, 21, 16, 30, 0)
    
    # Good connector: accurate intros, high match rate
    good = ConnectorScore("connector_alpha", [
        IntroReceipt("connector_alpha", "agent_1", "observer_x", now - timedelta(days=5), 0.9, 0.85, 0.95, "A", True),
        IntroReceipt("connector_alpha", "agent_2", "observer_y", now - timedelta(days=10), 0.85, 0.9, 0.9, "B", True),
        IntroReceipt("connector_alpha", "agent_3", "observer_z", now - timedelta(days=2), 0.95, 0.8, 0.88, "A", True),
        IntroReceipt("connector_alpha", "agent_4", "observer_w", now - timedelta(days=15), 0.8, 0.75, 0.92, "B", True),
    ])
    
    # Bad connector: oversells, low match rate
    bad = ConnectorScore("connector_spam", [
        IntroReceipt("connector_spam", "agent_5", "observer_x", now - timedelta(days=3), 0.3, 0.1, 0.4, "A", False),
        IntroReceipt("connector_spam", "agent_6", "observer_y", now - timedelta(days=7), 0.2, 0.15, 0.35, "B", False),
        IntroReceipt("connector_spam", "agent_7", "observer_z", now - timedelta(days=1), 0.25, 0.05, 0.5, "A", False),
    ])
    
    # Single observer — independence penalty
    single = ConnectorScore("connector_one_ref", [
        IntroReceipt("connector_one_ref", "agent_8", "observer_x", now - timedelta(days=2), 0.95, 0.9, 0.95, "A", True),
        IntroReceipt("connector_one_ref", "agent_9", "observer_x", now - timedelta(days=5), 0.9, 0.85, 0.9, "A", True),
    ])
    
    # Scope creep — good intros but drifts outside lane
    scope_creep = ConnectorScore("connector_drift", [
        IntroReceipt("connector_drift", "agent_10", "observer_a", now - timedelta(days=3), 0.85, 0.8, 0.2, "B", True),
        IntroReceipt("connector_drift", "agent_11", "observer_b", now - timedelta(days=8), 0.9, 0.75, 0.15, "A", True),
        IntroReceipt("connector_drift", "agent_12", "observer_c", now - timedelta(days=1), 0.8, 0.7, 0.25, "B", True),
    ])
    
    for name, scorer in [("good_connector", good), ("spam_connector", bad), ("single_observer", single), ("scope_creep", scope_creep)]:
        result = scorer.score(now)
        print(f"\n{'='*50}")
        print(f"Scenario: {name}")
        print(f"Grade: {result['grade']} | Verdict: {result['verdict']}")
        print(f"Composite: {result.get('composite', 'N/A')} (weakest: {result.get('weakest_axis', 'N/A')})")
        print(f"  intro_accuracy:  {result.get('intro_accuracy', 'N/A')}")
        print(f"  match_quality:   {result.get('match_quality', 'N/A')}")
        print(f"  scope_adherence: {result.get('scope_adherence', 'N/A')}")
        print(f"Observers: {result.get('unique_observers', 0)} | Txn rate: {result.get('transaction_rate', 0)}")


if __name__ == "__main__":
    demo()
