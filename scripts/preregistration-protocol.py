#!/usr/bin/env python3
"""
preregistration-protocol.py — Commit-reveal for agent observations

Clinical trials solved publication bias with preregistration (ClinicalTrials.gov 2004).
Agents have the same problem: hiding null observations = hiding negative results.

Protocol:
1. COMMIT: hash(scope + queries + threshold) → publish commitment
2. OBSERVE: execute declared scope
3. REVEAL: publish scope + results + commitment proof
4. VERIFY: hash(revealed) == commitment

Prevents:
- Post-hoc scope narrowing ("I only checked clawk" when you declared 4 channels)
- Null suppression (hiding "nothing found" observations)
- Cherry-picking (only reporting positive findings)

Based on: Altman 1995, FDAAA 2007, AllTrials 2012
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Commitment:
    """Phase 1: Declare what you WILL check"""
    scope: list            # channels to check
    queries: list          # specific queries to run
    threshold: str         # what counts as "actionable"
    timestamp: float = 0.0
    commitment_hash: str = ""
    
    def __post_init__(self):
        self.timestamp = self.timestamp or time.time()
        payload = json.dumps({
            "scope": sorted(self.scope),
            "queries": sorted(self.queries),
            "threshold": self.threshold
        }, sort_keys=True)
        self.commitment_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class Revelation:
    """Phase 3: Publish what you found"""
    commitment: Commitment
    findings: dict          # channel → result
    timestamp: float = 0.0
    
    def verify(self) -> dict:
        """Check revelation matches commitment"""
        self.timestamp = self.timestamp or time.time()
        
        # Check scope coverage
        declared = set(self.commitment.scope)
        checked = set(self.findings.keys())
        missing = declared - checked
        extra = checked - declared
        coverage = len(declared & checked) / max(len(declared), 1)
        
        # Classify findings
        null_channels = [ch for ch, v in self.findings.items() 
                        if v in (None, 0, [], "null", "nothing", "no_activity")]
        active_channels = [ch for ch in self.findings if ch not in null_channels]
        
        result = {
            "commitment_hash": self.commitment.commitment_hash,
            "scope_coverage": round(coverage, 2),
            "missing_channels": list(missing),
            "extra_channels": list(extra),
            "null_channels": null_channels,
            "active_channels": active_channels,
            "is_complete_null": len(active_channels) == 0 and coverage >= 0.9,
            "elapsed_s": round(self.timestamp - self.commitment.timestamp, 1)
        }
        
        # Grade
        if coverage >= 0.9 and not missing:
            if active_channels:
                result["verdict"] = "VALID_ACK"
                result["grade"] = "A"
            else:
                result["verdict"] = "VALID_NACK"
                result["grade"] = "B"
        elif coverage >= 0.5:
            result["verdict"] = "PARTIAL_REVEAL"
            result["grade"] = "C"
        elif coverage > 0:
            result["verdict"] = "SCOPE_VIOLATION"
            result["grade"] = "D"
        else:
            result["verdict"] = "EMPTY_REVEAL"
            result["grade"] = "F"
        
        # Scope narrowing detection
        if missing:
            result["warning"] = f"Post-hoc scope narrowing: declared {list(missing)} but didn't check"
        
        return result


def demo():
    print("=" * 60)
    print("Preregistration Protocol for Agent Observations")
    print("Commit → Observe → Reveal → Verify")
    print("=" * 60)
    
    t = time.time()
    
    # 1. Full compliance
    c1 = Commitment(
        scope=["moltbook", "clawk", "email", "shellmates"],
        queries=["check_feed", "check_mentions", "check_inbox"],
        threshold="any_new_activity",
        timestamp=t
    )
    r1 = Revelation(c1, {
        "moltbook": "3 new posts",
        "clawk": "5 mentions",
        "email": "1 from gendolf",
        "shellmates": "2 matches"
    }, timestamp=t + 300)
    v1 = r1.verify()
    print(f"\n1. FULL COMPLIANCE: {v1['verdict']} (Grade {v1['grade']})")
    print(f"   Coverage: {v1['scope_coverage']}, Active: {v1['active_channels']}")
    
    # 2. Valid null (checked everything, found nothing)
    c2 = Commitment(
        scope=["moltbook", "clawk", "email", "shellmates"],
        queries=["check_feed", "check_mentions"],
        threshold="any_new_activity",
        timestamp=t
    )
    r2 = Revelation(c2, {
        "moltbook": "nothing",
        "clawk": "no_activity",
        "email": "null",
        "shellmates": "no_activity"
    }, timestamp=t + 300)
    v2 = r2.verify()
    print(f"\n2. VALID NULL: {v2['verdict']} (Grade {v2['grade']})")
    print(f"   Coverage: {v2['scope_coverage']}, Complete null: {v2['is_complete_null']}")
    
    # 3. Scope narrowing (declared 4, checked 1)
    c3 = Commitment(
        scope=["moltbook", "clawk", "email", "shellmates"],
        queries=["check_all"],
        threshold="any_new_activity",
        timestamp=t
    )
    r3 = Revelation(c3, {
        "clawk": "2 replies"
    }, timestamp=t + 300)
    v3 = r3.verify()
    print(f"\n3. SCOPE NARROWING: {v3['verdict']} (Grade {v3['grade']})")
    print(f"   Coverage: {v3['scope_coverage']}, Missing: {v3['missing_channels']}")
    if "warning" in v3:
        print(f"   ⚠️  {v3['warning']}")
    
    # 4. Empty reveal
    c4 = Commitment(
        scope=["moltbook", "clawk"],
        queries=["check_feed"],
        threshold="any_new_activity",
        timestamp=t
    )
    r4 = Revelation(c4, {}, timestamp=t + 300)
    v4 = r4.verify()
    print(f"\n4. EMPTY REVEAL: {v4['verdict']} (Grade {v4['grade']})")
    
    print(f"\n{'='*60}")
    print("Preregistration prevents:")
    print("  - Post-hoc scope narrowing (pharma hiding negative results)")
    print("  - Null suppression (agents hiding 'nothing found')")
    print("  - Cherry-picking (only reporting positive findings)")
    print(f"\nClinicalTrials.gov (2004) → FDAAA (2007) → AllTrials (2012)")
    print(f"Same fix for agents: declare scope, publish everything.")


if __name__ == "__main__":
    demo()
