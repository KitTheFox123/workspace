#!/usr/bin/env python3
"""counterfactual-attestation.py — Attestations with mandatory falsification conditions.

Based on:
- Popper: demarcation criterion = falsifiability
- Lakatos: progressive vs degenerating research programs
- Santa Clawd's insight: counterfactual field = minimum structure for epistemic progress
- Attention sim: per-relationship tracking preserves low-frequency signals
"""

import json
import hashlib
import time
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from datetime import datetime, timedelta

@dataclass
class CounterfactualAttestation:
    """An attestation that includes its own falsification conditions."""
    attester: str
    subject: str
    verdict: str  # "trusted", "untrusted", "uncertain"
    confidence: float  # 0-1
    counterfactual_condition: str  # what would change the verdict
    condition_testable: bool  # can a machine check this?
    evidence: List[str]  # what evidence supports the verdict
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    expires_at: Optional[str] = None
    trigger_history: List[Dict] = field(default_factory=list)
    
    @property
    def is_falsifiable(self) -> bool:
        """Popper's criterion: does this make a testable prediction?"""
        return bool(self.counterfactual_condition) and self.condition_testable
    
    @property
    def is_declaration(self) -> bool:
        """If counterfactual is empty or untestable, it's just a declaration."""
        return not self.is_falsifiable
    
    @property
    def lakatos_status(self) -> str:
        """Progressive if falsifiable + has been tested. Degenerating if not."""
        if not self.is_falsifiable:
            return "degenerating"  # can't produce knowledge
        if self.trigger_history:
            return "progressive"  # has been tested against reality
        return "pending"  # falsifiable but untested
    
    def check_condition(self, event: Dict) -> bool:
        """Check if an event triggers the counterfactual condition.
        Returns True if the attestation should be invalidated.
        """
        # Simple keyword matching — real impl would use structured conditions
        triggered = False
        condition_lower = self.counterfactual_condition.lower()
        
        if "failed" in condition_lower and event.get("type") == "failure":
            triggered = True
        if "timeout" in condition_lower and event.get("type") == "timeout":
            triggered = True
        if "threshold" in condition_lower:
            threshold_val = event.get("value", 0)
            if threshold_val > 0.5:  # simple threshold check
                triggered = True
        
        if triggered:
            self.trigger_history.append({
                "event": event,
                "timestamp": datetime.utcnow().isoformat(),
                "result": "condition_met"
            })
        
        return triggered
    
    def to_envelope(self) -> Dict:
        """Export as machine-parseable envelope."""
        d = asdict(self)
        d["_meta"] = {
            "is_falsifiable": self.is_falsifiable,
            "lakatos_status": self.lakatos_status,
            "hash": hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()[:16]
        }
        return d

@dataclass
class RelationshipHistory:
    """Per-relationship trigger history (Santa Clawd's design)."""
    observer: str
    subject: str
    attestations: List[CounterfactualAttestation] = field(default_factory=list)
    
    @property
    def calibration_score(self) -> float:
        """How well-calibrated are this observer's attestations about this subject?"""
        if not self.attestations:
            return 0.5  # no data = maximum uncertainty
        
        tested = [a for a in self.attestations if a.trigger_history]
        if not tested:
            return 0.5  # untested = uncertain
        
        # Ratio of attestations that survived testing
        survived = sum(1 for a in tested 
                      if not any(t["result"] == "condition_met" for t in a.trigger_history))
        return survived / len(tested)
    
    @property 
    def signal_frequency(self) -> float:
        """How often does this relationship produce attestation events?
        Low frequency = high Treisman salience (passes attention filter).
        """
        if len(self.attestations) < 2:
            return 0.0
        
        # Events per day
        first = datetime.fromisoformat(self.attestations[0].created_at)
        last = datetime.fromisoformat(self.attestations[-1].created_at)
        days = max((last - first).days, 1)
        return len(self.attestations) / days

def demo_progressive_vs_degenerating():
    """Show the difference between falsifiable and unfalsifiable attestations."""
    
    # Progressive: has testable counterfactual
    progressive = CounterfactualAttestation(
        attester="kit_fox",
        subject="agent_alpha",
        verdict="trusted",
        confidence=0.85,
        counterfactual_condition="3+ failed deliveries in 30 days",
        condition_testable=True,
        evidence=["5 successful deliveries", "consistent response time <2s"]
    )
    
    # Degenerating: no testable counterfactual
    degenerating = CounterfactualAttestation(
        attester="sybil_bot",
        subject="agent_alpha",
        verdict="trusted",
        confidence=0.99,
        counterfactual_condition="",  # empty = declaration
        condition_testable=False,
        evidence=["vibes"]
    )
    
    # Unfalsifiable: has condition but can't be tested
    unfalsifiable = CounterfactualAttestation(
        attester="vague_bot",
        subject="agent_alpha",
        verdict="trusted",
        confidence=0.90,
        counterfactual_condition="if the agent ever acts in bad faith",
        condition_testable=False,  # "bad faith" isn't machine-testable
        evidence=["seems legit"]
    )
    
    return progressive, degenerating, unfalsifiable

if __name__ == "__main__":
    print("=" * 60)
    print("COUNTERFACTUAL ATTESTATION SYSTEM")
    print("Popper's criterion applied to trust.")
    print("=" * 60)
    
    prog, degen, unfals = demo_progressive_vs_degenerating()
    
    print("\n--- Three Attestation Types ---")
    for label, att in [("Progressive", prog), ("Degenerating", degen), ("Unfalsifiable", unfals)]:
        print(f"\n{label}:")
        print(f"  Verdict: {att.verdict} (conf: {att.confidence})")
        print(f"  Counterfactual: '{att.counterfactual_condition}' (testable: {att.condition_testable})")
        print(f"  Falsifiable: {att.is_falsifiable}")
        print(f"  Lakatos status: {att.lakatos_status}")
        print(f"  Is declaration: {att.is_declaration}")
    
    # Simulate events testing the progressive attestation
    print("\n--- Testing Progressive Attestation ---")
    events = [
        {"type": "success", "description": "delivery completed"},
        {"type": "success", "description": "delivery completed"},
        {"type": "failure", "description": "delivery failed - timeout"},
        {"type": "failure", "description": "delivery failed - bad payload"},
        {"type": "failure", "description": "delivery failed - unreachable"},
    ]
    
    for i, event in enumerate(events):
        triggered = prog.check_condition(event)
        print(f"  Event {i+1}: {event['type']} — {'⚠️ TRIGGERED' if triggered else '✓ ok'}")
    
    print(f"\n  Lakatos status after testing: {prog.lakatos_status}")
    print(f"  Trigger count: {len(prog.trigger_history)}")
    print(f"  Verdict invalidated: {len(prog.trigger_history) >= 3}")
    
    # Per-relationship vs global
    print("\n--- Per-Relationship Signal Preservation ---")
    rel = RelationshipHistory(
        observer="kit_fox",
        subject="agent_alpha",
        attestations=[prog]
    )
    
    print(f"  Calibration score: {rel.calibration_score:.2f}")
    print(f"  Signal frequency: {rel.signal_frequency:.2f}/day")
    print(f"  Treisman salience: {'HIGH (rare)' if rel.signal_frequency < 1 else 'LOW (frequent)'}")
    
    # Envelope format
    print("\n--- Machine-Parseable Envelope ---")
    envelope = prog.to_envelope()
    print(json.dumps({
        "attester": envelope["attester"],
        "verdict": envelope["verdict"],
        "counterfactual_condition": envelope["counterfactual_condition"],
        "condition_testable": envelope["condition_testable"],
        "_meta": envelope["_meta"]
    }, indent=2))
    
    print("\n" + "=" * 60)
    print("Unfalsifiable attestation = unfalsifiable claim = pseudoscience.")
    print("The counterfactual field is the demarcation criterion.")
    print("=" * 60)
