#!/usr/bin/env python3
"""
connector-accuracy-scorer.py — Score connector (introducer/matchmaker) accuracy.

Per santaclawd: "agent has isnad + correction-health. operator has SLA bond. 
connector has... nothing. who ships connector-accuracy-scorer?"

Three metrics:
1. intro_accuracy — Did the introduced agent match the connector's description?
2. match_quality — Did the counterparty confirm value from the introduction?
3. scope_adherence — Did the connector stay within declared scope?

Key principle: COUNTERPARTY generates ground truth, not the connector.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import hashlib
import json


@dataclass
class IntroductionReceipt:
    connector_id: str
    introduced_agent_id: str
    counterparty_id: str
    claimed_capabilities: list[str]  # what connector said agent could do
    actual_capabilities: list[str]   # what counterparty observed
    counterparty_satisfaction: float  # 0.0-1.0, from counterparty
    scope_declared: str              # what connector said the intro was for
    scope_actual: str                # what actually happened
    scope_match: bool                # did actual stay within declared?
    timestamp: datetime
    receipt_hash: Optional[str] = None
    
    def __post_init__(self):
        if not self.receipt_hash:
            payload = f"{self.connector_id}:{self.introduced_agent_id}:{self.counterparty_id}:{self.timestamp.isoformat()}"
            self.receipt_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass 
class ConnectorScore:
    connector_id: str
    intro_accuracy: float      # Jaccard similarity of claimed vs actual capabilities
    match_quality: float       # Mean counterparty satisfaction
    scope_adherence: float     # Fraction of intros that stayed in scope
    composite: float           # MIN(all three) — weakest axis names failure
    grade: str
    receipts_count: int
    confidence_width: float    # Wilson CI width
    issues: list[dict]
    principal_attribution: dict  # per-principal breakdown


def score_connector(receipts: list[IntroductionReceipt]) -> ConnectorScore:
    if not receipts:
        return ConnectorScore(
            connector_id="unknown", intro_accuracy=0, match_quality=0,
            scope_adherence=0, composite=0, grade="I", receipts_count=0,
            confidence_width=1.0, issues=[{"type": "NO_DATA"}],
            principal_attribution={}
        )
    
    connector_id = receipts[0].connector_id
    n = len(receipts)
    issues = []
    
    # 1. Intro accuracy: Jaccard similarity of claimed vs actual capabilities
    accuracies = []
    for r in receipts:
        claimed = set(r.claimed_capabilities)
        actual = set(r.actual_capabilities)
        if claimed or actual:
            jaccard = len(claimed & actual) / len(claimed | actual) if (claimed | actual) else 0
            accuracies.append(jaccard)
        else:
            accuracies.append(1.0)  # both empty = trivially accurate
    intro_accuracy = sum(accuracies) / len(accuracies)
    
    # 2. Match quality: counterparty satisfaction (COUNTERPARTY is ground truth)
    match_quality = sum(r.counterparty_satisfaction for r in receipts) / n
    
    # 3. Scope adherence
    scope_adherence = sum(1 for r in receipts if r.scope_match) / n
    
    # Composite = MIN (weakest axis names the failure)
    composite = min(intro_accuracy, match_quality, scope_adherence)
    
    # Wilson CI width (for confidence)
    import math
    z = 1.96
    p_hat = composite
    ci_width = 2 * z * math.sqrt(p_hat * (1 - p_hat) / n) if n > 0 else 1.0
    ci_width = min(ci_width, 1.0)
    
    # Grade
    if n < 5:
        grade = "I"  # insufficient data
    elif composite >= 0.85:
        grade = "A"
    elif composite >= 0.70:
        grade = "B"
    elif composite >= 0.50:
        grade = "C"
    elif composite >= 0.30:
        grade = "D"
    else:
        grade = "F"
    
    # Issues
    if intro_accuracy < 0.5:
        issues.append({
            "type": "LOW_INTRO_ACCURACY",
            "severity": "CRITICAL",
            "detail": f"Connector claims don't match reality ({intro_accuracy:.2f})"
        })
    if match_quality < 0.5:
        issues.append({
            "type": "LOW_MATCH_QUALITY",
            "severity": "CRITICAL",
            "detail": f"Counterparties unsatisfied ({match_quality:.2f})"
        })
    if scope_adherence < 0.7:
        issues.append({
            "type": "SCOPE_CREEP",
            "severity": "WARNING",
            "detail": f"Introductions exceed declared scope ({scope_adherence:.0%})"
        })
    
    # Overselling detection: claimed > actual consistently
    overselling = sum(1 for r in receipts 
                     if len(set(r.claimed_capabilities) - set(r.actual_capabilities)) > 
                        len(set(r.actual_capabilities) - set(r.claimed_capabilities)))
    if overselling / n > 0.5:
        issues.append({
            "type": "OVERSELLING",
            "severity": "WARNING", 
            "detail": f"{overselling}/{n} intros overclaimed capabilities"
        })
    
    # Principal attribution (split mode per santaclawd)
    principal_attribution = {
        "connector": {
            "intro_accuracy": round(intro_accuracy, 3),
            "scope_adherence": round(scope_adherence, 3),
            "liability": "CONNECTOR" if intro_accuracy < 0.5 or scope_adherence < 0.5 else "NONE"
        },
        "introduced_agent": {
            "match_quality": round(match_quality, 3),
            "liability": "AGENT" if match_quality < 0.5 and intro_accuracy >= 0.7 else "NONE"
        },
        "counterparty": {
            "role": "GROUND_TRUTH_SOURCE",
            "receipts_provided": n
        }
    }
    
    return ConnectorScore(
        connector_id=connector_id,
        intro_accuracy=round(intro_accuracy, 3),
        match_quality=round(match_quality, 3),
        scope_adherence=round(scope_adherence, 3),
        composite=round(composite, 3),
        grade=grade,
        receipts_count=n,
        confidence_width=round(ci_width, 3),
        issues=issues,
        principal_attribution=principal_attribution
    )


def demo():
    now = datetime(2026, 3, 21, 16, 0, 0)
    
    # Good connector
    good_receipts = [
        IntroductionReceipt("connector_A", f"agent_{i}", f"cp_{i}",
            claimed_capabilities=["search", "analysis", "writing"],
            actual_capabilities=["search", "analysis", "writing"],
            counterparty_satisfaction=0.85 + (i % 3) * 0.05,
            scope_declared="research assistance",
            scope_actual="research assistance",
            scope_match=True, timestamp=now)
        for i in range(8)
    ]
    
    # Overselling connector (claims more than delivered)
    overseller_receipts = [
        IntroductionReceipt("connector_B", f"agent_{i}", f"cp_{i}",
            claimed_capabilities=["search", "analysis", "code", "deploy", "monitor"],
            actual_capabilities=["search", "analysis"],
            counterparty_satisfaction=0.3 + (i % 3) * 0.1,
            scope_declared="full-stack development",
            scope_actual="basic research only",
            scope_match=False, timestamp=now)
        for i in range(6)
    ]
    
    # Scope creeper (good matches but expands beyond declared)
    creeper_receipts = [
        IntroductionReceipt("connector_C", f"agent_{i}", f"cp_{i}",
            claimed_capabilities=["search"],
            actual_capabilities=["search"],
            counterparty_satisfaction=0.9,
            scope_declared="web search",
            scope_actual="web search + data analysis + reporting" if i % 3 == 0 else "web search",
            scope_match=(i % 3 != 0), timestamp=now)
        for i in range(9)
    ]
    
    for name, receipts in [("good_connector", good_receipts), 
                           ("overseller", overseller_receipts),
                           ("scope_creeper", creeper_receipts)]:
        score = score_connector(receipts)
        print(f"\n{'='*50}")
        print(f"Connector: {name} | Grade: {score.grade} | Composite: {score.composite}")
        print(f"  intro_accuracy={score.intro_accuracy} match_quality={score.match_quality} scope_adherence={score.scope_adherence}")
        print(f"  CI width: {score.confidence_width} | Receipts: {score.receipts_count}")
        if score.issues:
            for issue in score.issues:
                print(f"  [{issue['severity']}] {issue['type']}: {issue['detail']}")
        print(f"  Attribution: {json.dumps(score.principal_attribution, indent=4)}")


if __name__ == "__main__":
    demo()
